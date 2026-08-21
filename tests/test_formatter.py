from src.collector.formatter import build_slack_blocks
from src.collector.models import Article


def _article(title, url, category, summary="要約テキスト"):
    return Article(title=title, url=url, source="search", source_name="t", category=category, summary=summary)


def test_build_slack_blocks_groups_by_category_in_fixed_order():
    articles = [
        _article("広告記事", "https://example.com/ads", "ads"),
        _article("SEO記事", "https://example.com/seo", "seo"),
    ]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    header_texts = [
        b["text"]["text"] for b in blocks
        if b["type"] == "header"
    ]
    assert any("2026-08-20" in t for t in header_texts)

    section_texts = "\n".join(
        b["text"]["text"] for b in blocks if b["type"] == "section"
    )
    seo_index = section_texts.find("SEO記事")
    ads_index = section_texts.find("広告記事")
    assert 0 <= seo_index < ads_index


def test_build_slack_blocks_includes_link_and_summary():
    articles = [_article("記事タイトル", "https://example.com/a", "seo", summary="これは要約です")]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    section_texts = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "<https://example.com/a|記事タイトル>" in section_texts
    assert "これは要約です" in section_texts


def test_build_slack_blocks_escapes_mrkdwn_in_title_and_summary():
    articles = [
        _article("<!channel> urgent", "https://example.com/a", "seo", summary="<!here> & <https://evil|link>")
    ]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    section_texts = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "&lt;!channel&gt; urgent" in section_texts
    assert "<!channel>" not in section_texts
    assert "&lt;!here&gt; &amp; &lt;https://evil|link&gt;" in section_texts
    assert "<!here>" not in section_texts
    assert "<https://example.com/a|" in section_texts


def test_build_slack_blocks_puts_unknown_category_under_other():
    articles = [_article("未知カテゴリ記事", "https://example.com/x", "マーケティング")]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    section_texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert "*その他*" in section_texts
    other_index = section_texts.index("*その他*")
    assert any("未知カテゴリ記事" in t for t in section_texts[other_index + 1:])


def test_build_slack_blocks_empty_articles_returns_header_only():
    blocks = build_slack_blocks([], today="2026-08-20")

    assert any(b["type"] == "header" for b in blocks)
    assert not any(b["type"] == "section" and "http" in b["text"]["text"] for b in blocks)
