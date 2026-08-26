import json

from src.collector.models import Article
from src.collector.relevance_filter_ai import filter_by_relevance


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
    return Article(title=title, url=url, source="rss", source_name="test")


def test_filter_by_relevance_keeps_relevant_and_drops_irrelevant():
    payload = json.dumps([
        {"url": "https://example.com/a", "relevant": True},
        {"url": "https://example.com/b", "relevant": False},
    ])
    client = _FakeClient([_FakeResponse(payload)])
    article_a = _article(title="A", url="https://example.com/a")
    article_b = _article(title="B", url="https://example.com/b")

    result = filter_by_relevance([article_a, article_b], client, batch_size=10)

    assert result == [article_a]


def test_filter_by_relevance_retries_then_succeeds():
    payload = json.dumps([{"url": "https://example.com/a", "relevant": True}])
    client = _FakeClient([ConnectionError("boom"), _FakeResponse(payload)])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10, max_retries=3)

    assert result == [article]


def test_filter_by_relevance_keeps_batch_unfiltered_after_exhausting_retries():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10, max_retries=3)

    assert result == [article]


def test_filter_by_relevance_keeps_batch_unfiltered_on_malformed_json():
    client = _FakeClient([_FakeResponse("not json")])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10)

    assert result == [article]


def test_filter_by_relevance_keeps_article_missing_from_response():
    payload = json.dumps([{"url": "https://example.com/other", "relevant": False}])
    client = _FakeClient([_FakeResponse(payload)])
    article = _article(url="https://example.com/a")

    result = filter_by_relevance([article], client, batch_size=10)

    assert result == [article]


def test_filter_by_relevance_batches_large_lists():
    payload_batch1 = json.dumps([{"url": f"https://example.com/{i}", "relevant": True} for i in range(3)])
    payload_batch2 = json.dumps([{"url": f"https://example.com/{i}", "relevant": True} for i in range(3, 5)])
    client = _FakeClient([_FakeResponse(payload_batch1), _FakeResponse(payload_batch2)])
    articles = [_article(title=f"T{i}", url=f"https://example.com/{i}") for i in range(5)]

    result = filter_by_relevance(articles, client, batch_size=3)

    assert len(result) == 5
    assert client.calls == 2
