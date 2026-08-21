import json

from src.collector.models import Article
from src.collector.summarizer import summarize_and_classify


class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, model, max_tokens, messages):
            response = self._outer._responses[self._outer.calls]
            self._outer.calls += 1
            if isinstance(response, Exception):
                raise response
            return response

    @property
    def messages(self):
        return _FakeClient._Messages(self)


def _article(title="A", url="https://example.com/a"):
    return Article(title=title, url=url, source="search", source_name="test")


def test_summarize_and_classify_fills_summary_and_category():
    payload = json.dumps([
        {"url": "https://example.com/a", "summary": "3行要約テキスト", "category": "seo"},
    ])
    client = _FakeClient([_FakeResponse(payload)])

    result = summarize_and_classify([_article()], client, batch_size=10)

    assert result[0].summary == "3行要約テキスト"
    assert result[0].category == "seo"


def test_summarize_and_classify_retries_then_succeeds():
    payload = json.dumps([
        {"url": "https://example.com/a", "summary": "要約", "category": "ai"},
    ])
    client = _FakeClient([ConnectionError("boom"), _FakeResponse(payload)])

    result = summarize_and_classify([_article()], client, batch_size=10, max_retries=3)

    assert result[0].summary == "要約"
    assert result[0].category == "ai"


def test_summarize_and_classify_falls_back_after_exhausting_retries():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])

    result = summarize_and_classify([_article()], client, batch_size=10, max_retries=3)

    assert result[0].summary is None
    assert result[0].category == "other"


def test_summarize_and_classify_handles_malformed_json():
    client = _FakeClient([_FakeResponse("not json")])

    result = summarize_and_classify([_article()], client, batch_size=10)

    assert result[0].summary is None
    assert result[0].category == "other"


def test_summarize_and_classify_handles_partial_batch_response():
    payload = json.dumps([
        {"url": "https://example.com/a", "summary": "要約A", "category": "seo"},
    ])
    client = _FakeClient([_FakeResponse(payload)])

    article_a = _article(title="A", url="https://example.com/a")
    article_b = _article(title="B", url="https://example.com/b")

    result = summarize_and_classify([article_a, article_b], client, batch_size=10)

    assert result[0].summary == "要約A"
    assert result[0].category == "seo"
    assert result[1].summary is None
    assert result[1].category == "other"
