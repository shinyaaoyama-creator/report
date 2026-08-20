from src.collector.dedup import dedupe_articles
from src.collector.models import Article


def _article(title, url, source="search"):
    return Article(title=title, url=url, source=source, source_name="test")


def test_removes_articles_already_in_state():
    state = {"https://example.com/a": "2026-08-19T09:00:00+00:00"}
    articles = [_article("A", "https://example.com/a?utm_source=x")]

    result = dedupe_articles(articles, state)

    assert result == []


def test_removes_exact_url_duplicates_across_sources():
    articles = [
        _article("A", "https://example.com/a", source="search"),
        _article("A (via RSS)", "https://example.com/a?utm_source=feed", source="rss"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 1


def test_removes_near_duplicate_titles_different_urls():
    articles = [
        _article("生成AIがBtoBマーケティングを変える", "https://example.com/a"),
        _article("生成AIがBtoBマーケティングを変える！", "https://example.org/b"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 1


def test_keeps_distinct_articles():
    articles = [
        _article("SEOの新しい潮流", "https://example.com/a"),
        _article("広告オークションの変化", "https://example.org/b"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 2
