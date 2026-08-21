from src.collector.models import Article
from src.collector.relevance_filter import extract_google_news_keyword, filter_by_source_keyword


def _article(title, source_name, url="https://example.com/a"):
    return Article(title=title, url=url, source="rss", source_name=source_name)


def test_extract_google_news_keyword_parses_quoted_name():
    assert extract_google_news_keyword('"claude code" - Google ニュース') == "claude code"


def test_extract_google_news_keyword_returns_none_for_non_matching_name():
    assert extract_google_news_keyword("Example Blog") is None


def test_filter_by_source_keyword_keeps_article_with_keyword_in_title():
    article = _article(
        title="Claude Codeを導入した事例",
        source_name='"Claude Code" - Google ニュース',
    )

    result = filter_by_source_keyword([article])

    assert result == [article]


def test_filter_by_source_keyword_is_case_insensitive():
    article = _article(
        title="claude codeの使い方",
        source_name='"Claude Code" - Google ニュース',
    )

    result = filter_by_source_keyword([article])

    assert result == [article]


def test_filter_by_source_keyword_drops_article_without_keyword_in_title():
    article = _article(
        title="人事評価制度を刷新した企業の事例",
        source_name='"BDR" - Google ニュース',
    )

    result = filter_by_source_keyword([article])

    assert result == []


def test_filter_by_source_keyword_keeps_non_google_news_articles_untouched():
    article = _article(
        title="全く関係のないタイトル",
        source_name="Example Blog",
    )

    result = filter_by_source_keyword([article])

    assert result == [article]


def test_filter_by_source_keyword_handles_mixed_batch():
    matching = _article(title="人事制度の話題", source_name='"人事" - Google ニュース')
    non_matching = _article(title="全く別の話題", source_name='"人事" - Google ニュース', url="https://example.com/b")
    other_source = _article(title="他ソースの記事", source_name="Example Blog", url="https://example.com/c")

    result = filter_by_source_keyword([matching, non_matching, other_source])

    assert result == [matching, other_source]
