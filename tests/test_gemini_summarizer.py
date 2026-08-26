import json

from src.collector.gemini_summarizer import summarize_and_classify
from src.collector.models import Article


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, outer):
        self._outer = outer

    def generate_content(self, model, contents):
        response = self._outer._responses[self._outer.calls]
        self._outer.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    @property
    def models(self):
        return _FakeModels(self)


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


def test_summarize_and_classify_uses_valid_category_hint_as_fallback():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])
    article = _article()
    article.category_hint = "seo"

    result = summarize_and_classify([article], client, batch_size=10, max_retries=3)

    assert result[0].category == "seo"


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


def test_summarize_and_classify_sleeps_between_batches(monkeypatch):
    payload_a = json.dumps([{"url": "https://example.com/a", "summary": "要約A", "category": "seo"}])
    payload_b = json.dumps([{"url": "https://example.com/b", "summary": "要約B", "category": "ai"}])
    client = _FakeClient([_FakeResponse(payload_a), _FakeResponse(payload_b)])

    article_a = _article(title="A", url="https://example.com/a")
    article_b = _article(title="B", url="https://example.com/b")

    sleeps = []
    monkeypatch.setattr("src.collector.gemini_summarizer.time.sleep", lambda s: sleeps.append(s))

    summarize_and_classify([article_a, article_b], client, batch_size=1, request_interval_seconds=4.5)

    assert sleeps == [4.5]
