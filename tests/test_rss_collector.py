import logging

from src.collector.rss_collector import collect_rss_articles, fetch_feed_articles


class _FakeEntry(dict):
    def __getattr__(self, name):
        return self[name]


class _FakeParsed:
    def __init__(self, entries, bozo=False):
        self.entries = entries
        self.bozo = bozo


def test_fetch_feed_articles_maps_entries_to_articles():
    parsed = _FakeParsed([
        _FakeEntry(title="記事A", link="https://example.com/a", published="2026-08-19"),
    ])
    feed = {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"}

    result = fetch_feed_articles(feed, parse_fn=lambda url: parsed)

    assert len(result) == 1
    assert result[0].title == "記事A"
    assert result[0].url == "https://example.com/a"
    assert result[0].source == "rss"
    assert result[0].source_name == "Example Blog"
    assert result[0].category_hint == "seo"
    assert result[0].published_at == "2026-08-19"


def test_fetch_feed_articles_bozo_raises():
    parsed = _FakeParsed([], bozo=True)
    feed = {"name": "Broken Feed", "url": "https://example.com/broken.xml", "category_hint": None}

    try:
        fetch_feed_articles(feed, parse_fn=lambda url: parsed)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_fetch_feed_articles_bozo_with_entries_returns_articles():
    parsed = _FakeParsed(
        [_FakeEntry(title="記事A", link="https://example.com/a", published=None)],
        bozo=True,
    )
    feed = {"name": "Quirky Feed", "url": "https://example.com/quirky.xml", "category_hint": "ai"}

    result = fetch_feed_articles(feed, parse_fn=lambda url: parsed)

    assert len(result) == 1
    assert result[0].url == "https://example.com/a"


def test_fetch_feed_articles_skips_entries_without_link():
    parsed = _FakeParsed([
        _FakeEntry(title="リンクなし", link="", published=None),
        _FakeEntry(title="linkキーなし", published=None),
        _FakeEntry(title="リンクあり", link="https://example.com/ok", published=None),
    ])
    feed = {"name": "Mixed Feed", "url": "https://example.com/mixed.xml", "category_hint": None}

    result = fetch_feed_articles(feed, parse_fn=lambda url: parsed)

    assert [a.url for a in result] == ["https://example.com/ok"]
    assert all(a.url for a in result)


def test_collect_rss_articles_skips_failing_feed(caplog):
    good_parsed = _FakeParsed([_FakeEntry(title="OK記事", link="https://example.com/ok", published=None)])

    def _parse(url):
        if url == "https://example.com/broken.xml":
            return _FakeParsed([], bozo=True)
        return good_parsed

    feeds = [
        {"name": "Broken Feed", "url": "https://example.com/broken.xml", "category_hint": None},
        {"name": "Good Feed", "url": "https://example.com/good.xml", "category_hint": "ai"},
    ]

    with caplog.at_level(logging.WARNING):
        result = collect_rss_articles(feeds, parse_fn=_parse)

    assert len(result) == 1
    assert result[0].title == "OK記事"
    assert "Broken Feed" in caplog.text
