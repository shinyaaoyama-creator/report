from src.collector.models import Article
from src.collector.recency_filter import filter_by_recency

NOW = "2026-09-11T09:00:00+00:00"


def _article(published_at, url="https://example.com/a"):
    return Article(title="記事", url=url, source="rss", source_name="Example Blog", published_at=published_at)


def test_filter_by_recency_keeps_article_published_today_rfc822():
    article = _article("Fri, 11 Sep 2026 08:00:00 +0000")

    result = filter_by_recency([article], now_iso=NOW, max_age_days=3)

    assert result == [article]


def test_filter_by_recency_drops_article_older_than_max_age_rfc822():
    article = _article("Sun, 06 Sep 2026 08:00:00 +0000")

    result = filter_by_recency([article], now_iso=NOW, max_age_days=3)

    assert result == []


def test_filter_by_recency_keeps_article_within_max_age_iso8601():
    article = _article("2026-09-09T10:00:00+09:00")

    result = filter_by_recency([article], now_iso=NOW, max_age_days=3)

    assert result == [article]


def test_filter_by_recency_keeps_article_with_unparseable_date():
    article = _article("not a real date")

    result = filter_by_recency([article], now_iso=NOW, max_age_days=3)

    assert result == [article]


def test_filter_by_recency_keeps_article_with_no_date():
    article = _article(None)

    result = filter_by_recency([article], now_iso=NOW, max_age_days=3)

    assert result == [article]


def test_filter_by_recency_handles_mixed_batch():
    fresh = _article("Fri, 11 Sep 2026 08:00:00 +0000", url="https://example.com/fresh")
    stale = _article("Sun, 06 Sep 2026 08:00:00 +0000", url="https://example.com/stale")
    undated = _article(None, url="https://example.com/undated")

    result = filter_by_recency([fresh, stale, undated], now_iso=NOW, max_age_days=3)

    assert result == [fresh, undated]
