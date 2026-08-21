import json

import pytest

from src.collector import main as main_module
from src.collector.models import Article


def _setup_configs(tmp_path):
    keywords_path = tmp_path / "keywords.yaml"
    keywords_path.write_text("seo:\n  - test\n", encoding="utf-8")
    feeds_path = tmp_path / "feeds.yaml"
    feeds_path.write_text("[]\n", encoding="utf-8")
    state_path = tmp_path / "seen_articles.json"
    state_path.write_text("{}\n", encoding="utf-8")
    return {
        "keywords": str(keywords_path),
        "feeds": str(feeds_path),
        "state": str(state_path),
    }


def test_run_dry_run_does_not_post_or_save_state(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [Article(title="A", url="https://example.com/a", source="search", source_name="s")],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(title=a.title, url=a.url, source=a.source, source_name=a.source_name, summary="要約", category="seo")
            for a in articles
        ],
    )

    posted = {"called": False}
    monkeypatch.setattr(main_module, "post_to_slack", lambda blocks, url: posted.update(called=True))

    blocks = main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), "slack_webhook_url": "https://hooks.slack.com/x"},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert posted["called"] is False
    assert any("要約" in b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section")

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert state_after == {}


def test_run_caps_articles_per_run(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    many = [
        Article(title=f"A{i}", url=f"https://example.com/{i}", source="search", source_name="s")
        for i in range(60)
    ]

    monkeypatch.setattr(main_module, "collect_search_articles", lambda keywords, api_key, cse_id: many)
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(
                title=a.title,
                url=a.url,
                source=a.source,
                source_name=a.source_name,
                summary="要約",
                category="seo",
            )
            for a in articles
        ],
    )

    captured = {}
    monkeypatch.setattr(
        main_module, "post_to_slack", lambda blocks, url: captured.update(blocks=blocks)
    )

    blocks = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": object(),
            "slack_webhook_url": "https://hooks.slack.com/x",
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=False,
    )

    article_sections = [
        b for b in captured["blocks"]
        if b["type"] == "section" and "https://example.com/" in b["text"]["text"]
    ]
    assert len(article_sections) == main_module.MAX_ARTICLES_PER_RUN == 40
    assert blocks == captured["blocks"]

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert len(state_after) == 40


def test_run_live_posts_and_updates_state(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [Article(title="A", url="https://example.com/a", source="search", source_name="s")],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(title=a.title, url=a.url, source=a.source, source_name=a.source_name, summary="要約", category="seo")
            for a in articles
        ],
    )

    posted = {"called": False}
    monkeypatch.setattr(main_module, "post_to_slack", lambda blocks, url: posted.update(called=True))

    main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), "slack_webhook_url": "https://hooks.slack.com/x"},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=False,
    )

    assert posted["called"] is True

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert "https://example.com/a" in state_after


def test_run_skips_summarizer_when_anthropic_client_is_none(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [
            Article(
                title="A",
                url="https://example.com/a",
                source="search",
                source_name="s",
                category_hint="seo",
            )
        ],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])

    def _fail_if_called(articles, client):
        raise AssertionError("summarize_and_classify must not be called when anthropic_client is None")

    monkeypatch.setattr(main_module, "summarize_and_classify", _fail_if_called)

    blocks = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            "slack_webhook_url": "https://hooks.slack.com/x",
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    section_texts = "\n".join(
        b["text"]["text"] for b in blocks if b["type"] == "section"
    )
    assert "https://example.com/a" in section_texts
    assert "(要約なし)" in section_texts


def test_run_filters_out_articles_not_matching_their_feed_keyword(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [],
    )
    monkeypatch.setattr(
        main_module,
        "collect_rss_articles",
        lambda feeds: [
            Article(
                title="人事評価制度の話題",
                url="https://example.com/a",
                source="rss",
                source_name='"人事" - Google ニュース',
            ),
            Article(
                title="全く関係のない話題",
                url="https://example.com/b",
                source="rss",
                source_name='"人事" - Google ニュース',
            ),
        ],
    )

    blocks = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            "slack_webhook_url": "https://hooks.slack.com/x",
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    section_texts = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "https://example.com/a" in section_texts
    assert "https://example.com/b" not in section_texts


def test_run_propagates_post_failure_and_leaves_state_unsaved(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)
    state_before = (tmp_path / "seen_articles.json").read_text(encoding="utf-8")

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [
            Article(title="A", url="https://example.com/a", source="search", source_name="s")
        ],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(
                title=a.title,
                url=a.url,
                source=a.source,
                source_name=a.source_name,
                summary="要約",
                category="seo",
            )
            for a in articles
        ],
    )

    def _failing_post(blocks, url):
        raise RuntimeError("HTTP 400")

    monkeypatch.setattr(main_module, "post_to_slack", _failing_post)

    with pytest.raises(RuntimeError):
        main_module.run(
            config_paths,
            secrets={
                "google_api_key": "k",
                "google_cse_id": "c",
                "anthropic_client": object(),
                "slack_webhook_url": "https://hooks.slack.com/x",
            },
            now_iso="2026-08-20T00:00:00+00:00",
            dry_run=False,
        )

    state_after_text = (tmp_path / "seen_articles.json").read_text(encoding="utf-8")
    assert state_after_text == state_before
    assert json.loads(state_after_text) == {}
