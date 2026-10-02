from src.collector.formatter import build_email_html
from src.collector.models import Article


def _article(title, url, category, summary="要約テキスト"):
    return Article(title=title, url=url, source="search", source_name="t", category=category, summary=summary)


def test_build_email_html_groups_by_category_in_fixed_order():
    articles = [
        _article("広告記事", "https://example.com/ads", "ads"),
        _article("SEO記事", "https://example.com/seo", "seo"),
    ]

    html = build_email_html(articles, today="2026-08-20")

    assert "2026-08-20" in html
    seo_index = html.find("SEO記事")
    ads_index = html.find("広告記事")
    assert 0 <= seo_index < ads_index


def test_build_email_html_includes_link_and_summary():
    articles = [_article("記事タイトル", "https://example.com/a", "seo", summary="これは要約です")]

    html = build_email_html(articles, today="2026-08-20")

    assert '<a href="https://example.com/a">記事タイトル</a>' in html
    assert "これは要約です" in html


def test_build_email_html_escapes_html_in_title_and_summary():
    articles = [
        _article("<script>alert(1)</script>", "https://example.com/a", "seo", summary="<b>bold</b> & stuff")
    ]

    html = build_email_html(articles, today="2026-08-20")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; stuff" in html


def test_build_email_html_puts_unknown_category_under_other():
    articles = [_article("未知カテゴリ記事", "https://example.com/x", "マーケティング")]

    html = build_email_html(articles, today="2026-08-20")

    other_index = html.find("その他")
    article_index = html.find("未知カテゴリ記事")
    assert 0 <= other_index < article_index


def test_build_email_html_empty_articles_shows_placeholder():
    html = build_email_html([], today="2026-08-20")

    assert "該当する記事はありませんでした" in html
    assert "http" not in html
