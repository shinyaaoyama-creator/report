import logging

from src.collector.search_collector import collect_search_articles, fetch_search_results


def _fake_http_get(response_by_query):
    def _get(url, params, timeout=10):
        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self._payload

        return _Resp(response_by_query[params["q"]])

    return _get


def test_fetch_search_results_maps_items_to_articles():
    payload = {
        "items": [
            {"title": "記事A", "link": "https://example.com/a"},
            {"title": "記事B", "link": "https://example.com/b"},
        ]
    }
    http_get = _fake_http_get({"コンテンツSEO": payload})

    result = fetch_search_results("コンテンツSEO", "seo", "key", "cse", http_get=http_get)

    assert len(result) == 2
    assert result[0].title == "記事A"
    assert result[0].url == "https://example.com/a"
    assert result[0].source == "search"
    assert result[0].category_hint == "seo"


def test_fetch_search_results_handles_no_items():
    http_get = _fake_http_get({"存在しないキーワード": {}})

    result = fetch_search_results("存在しないキーワード", "seo", "key", "cse", http_get=http_get)

    assert result == []


def test_collect_search_articles_skips_failing_keyword(caplog):
    def _get(url, params, timeout=10):
        if params["q"] == "失敗するキーワード":
            raise ConnectionError("boom")

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"items": [{"title": "OK記事", "link": "https://example.com/ok"}]}

        return _Resp()

    keywords = {"seo": ["失敗するキーワード", "正常なキーワード"]}

    with caplog.at_level(logging.WARNING):
        result = collect_search_articles(keywords, "key", "cse", http_get=_get)

    assert len(result) == 1
    assert result[0].title == "OK記事"
    assert "失敗するキーワード" in caplog.text
