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


def test_filter_by_relevance_keeps_high_score_and_drops_low_score():
    payload = json.dumps([
        {"url": "https://example.com/a", "score": 5},
        {"url": "https://example.com/b", "score": 1},
    ])
    client = _FakeClient([_FakeResponse(payload)])
    article_a = _article(title="A", url="https://example.com/a")
    article_b = _article(title="B", url="https://example.com/b")

    result = filter_by_relevance([article_a, article_b], client, batch_size=10)

    assert result == [article_a]
    assert article_a.relevance_score == 5


def test_filter_by_relevance_retries_then_succeeds():
    payload = json.dumps([{"url": "https://example.com/a", "score": 4}])
    client = _FakeClient([ConnectionError("boom"), _FakeResponse(payload)])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10, max_retries=3)

    assert result == [article]
    assert article.relevance_score == 4


def test_filter_by_relevance_keeps_batch_unfiltered_after_exhausting_retries():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10, max_retries=3)

    assert result == [article]
    assert article.relevance_score == 3


def test_filter_by_relevance_keeps_batch_unfiltered_on_malformed_json():
    client = _FakeClient([_FakeResponse("not json")])
    article = _article()

    result = filter_by_relevance([article], client, batch_size=10)

    assert result == [article]
    assert article.relevance_score == 3


def test_filter_by_relevance_keeps_article_missing_from_response():
    payload = json.dumps([{"url": "https://example.com/other", "score": 1}])
    client = _FakeClient([_FakeResponse(payload)])
    article = _article(url="https://example.com/a")

    result = filter_by_relevance([article], client, batch_size=10)

    assert result == [article]
    assert article.relevance_score == 3


def test_filter_by_relevance_batches_large_lists():
    payload_batch1 = json.dumps([{"url": f"https://example.com/{i}", "score": 5} for i in range(3)])
    payload_batch2 = json.dumps([{"url": f"https://example.com/{i}", "score": 5} for i in range(3, 5)])
    client = _FakeClient([_FakeResponse(payload_batch1), _FakeResponse(payload_batch2)])
    articles = [_article(title=f"T{i}", url=f"https://example.com/{i}") for i in range(5)]

    result = filter_by_relevance(articles, client, batch_size=3)

    assert len(result) == 5
    assert client.calls == 2


def test_filter_by_relevance_sleeps_between_batches(monkeypatch):
    payload_batch1 = json.dumps([{"url": f"https://example.com/{i}", "score": 5} for i in range(3)])
    payload_batch2 = json.dumps([{"url": f"https://example.com/{i}", "score": 5} for i in range(3, 5)])
    client = _FakeClient([_FakeResponse(payload_batch1), _FakeResponse(payload_batch2)])
    articles = [_article(title=f"T{i}", url=f"https://example.com/{i}") for i in range(5)]

    sleeps = []
    monkeypatch.setattr("src.collector.relevance_filter_ai.time.sleep", lambda s: sleeps.append(s))

    filter_by_relevance(articles, client, batch_size=3, request_interval_seconds=4.5)

    assert sleeps == [4.5]


def test_filter_by_relevance_does_not_sleep_after_last_batch(monkeypatch):
    payload = json.dumps([{"url": "https://example.com/a", "score": 5}])
    client = _FakeClient([_FakeResponse(payload)])
    article = _article()

    sleeps = []
    monkeypatch.setattr("src.collector.relevance_filter_ai.time.sleep", lambda s: sleeps.append(s))

    filter_by_relevance([article], client, batch_size=10, request_interval_seconds=4.5)

    assert sleeps == []
