import textwrap
from src.collector import config


def test_load_keywords(tmp_path):
    p = tmp_path / "keywords.yaml"
    p.write_text(textwrap.dedent("""\
        seo:
          - コンテンツSEO
          - 検索アルゴリズム
        ai:
          - 生成AI 活用
        ads:
          - リスティング広告
        event:
          - BtoB展示会
        """), encoding="utf-8")

    result = config.load_keywords(str(p))

    assert result["seo"] == ["コンテンツSEO", "検索アルゴリズム"]
    assert result["ai"] == ["生成AI 活用"]
    assert result["ads"] == ["リスティング広告"]
    assert result["event"] == ["BtoB展示会"]


def test_load_feeds(tmp_path):
    p = tmp_path / "feeds.yaml"
    p.write_text(textwrap.dedent("""\
        - name: Example Blog
          url: https://example.com/feed.xml
          category_hint: seo
        - name: No Hint Blog
          url: https://example.org/rss
        """), encoding="utf-8")

    result = config.load_feeds(str(p))

    assert result == [
        {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"},
        {"name": "No Hint Blog", "url": "https://example.org/rss", "category_hint": None},
    ]
