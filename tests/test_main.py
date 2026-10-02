import json

import pytest

from src.collector import main as main_module
from src.collector.models import Article

_EMAIL_SECRETS = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "user@example.com",
    "smtp_password": "app-password",
    "email_from": "from@example.com",
    "email_to": "to@example.com",
}


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


def test_run_dry_run_does_not_send_email_or_save_state(tmp_path, monkeypatch):
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

    sent = {"called": False}
    monkeypatch.setattr(main_module, "send_email", lambda **kwargs: sent.update(called=True))

    html_body = main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), **_EMAIL_SECRETS},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert sent["called"] is False
    assert "要約" in html_body

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
        main_module, "send_email", lambda **kwargs: captured.update(html_body=kwargs["html_body"])
    )

    html_body = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": object(),
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=False,
    )

    assert captured["html_body"].count("https://example.com/") == main_module.MAX_ARTICLES_PER_RUN == 40
    assert html_body == captured["html_body"]

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert len(state_after) == 40


def test_run_live_sends_email_and_updates_state(tmp_path, monkeypatch):
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

    sent = {"called": False}
    monkeypatch.setattr(main_module, "send_email", lambda **kwargs: sent.update(called=True))

    main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), **_EMAIL_SECRETS},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=False,
    )

    assert sent["called"] is True

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

    html_body = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert "https://example.com/a" in html_body
    assert "(要約なし)" in html_body


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

    html_body = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert "https://example.com/a" in html_body
    assert "https://example.com/b" not in html_body


def test_run_drops_stale_rss_articles(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(main_module, "collect_search_articles", lambda keywords, api_key, cse_id: [])
    monkeypatch.setattr(
        main_module,
        "collect_rss_articles",
        lambda feeds: [
            Article(
                title="新しい記事",
                url="https://example.com/fresh",
                source="rss",
                source_name="s",
                published_at="Thu, 20 Aug 2026 00:00:00 +0000",
            ),
            Article(
                title="古い記事",
                url="https://example.com/stale",
                source="rss",
                source_name="s",
                published_at="Mon, 01 Jun 2026 00:00:00 +0000",
            ),
        ],
    )

    html_body = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert "https://example.com/fresh" in html_body
    assert "https://example.com/stale" not in html_body


def test_run_uses_gemini_for_relevance_filter_and_summarization_when_provided(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [
            Article(title="A", url="https://example.com/a", source="search", source_name="s")
        ],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])

    relevance_calls = {"called": False}

    def _fake_filter_by_relevance(articles, client, **kwargs):
        relevance_calls["called"] = True
        return articles

    monkeypatch.setattr(main_module, "filter_by_relevance", _fake_filter_by_relevance)

    def _fail_if_claude_called(articles, client):
        raise AssertionError("claude summarize_and_classify must not be called when gemini_client is provided")

    monkeypatch.setattr(main_module, "summarize_and_classify", _fail_if_claude_called)

    def _fake_gemini_summarize(articles, client, **kwargs):
        for article in articles:
            article.summary = "Gemini要約"
            article.category = "seo"
        return articles

    monkeypatch.setattr(main_module, "gemini_summarize_and_classify", _fake_gemini_summarize)

    html_body = main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            "gemini_client": object(),
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert relevance_calls["called"] is True
    assert "Gemini要約" in html_body


def test_run_applies_relevance_filter_before_capping(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    many = [
        Article(title=f"A{i}", url=f"https://example.com/{i}", source="search", source_name="s")
        for i in range(60)
    ]
    monkeypatch.setattr(main_module, "collect_search_articles", lambda keywords, api_key, cse_id: many)
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])

    received_counts = {}

    def _fake_filter_by_relevance(articles, client, **kwargs):
        received_counts["count"] = len(articles)
        return articles

    monkeypatch.setattr(main_module, "filter_by_relevance", _fake_filter_by_relevance)
    monkeypatch.setattr(main_module, "gemini_summarize_and_classify", lambda articles, client, **kwargs: articles)

    main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            "gemini_client": object(),
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert received_counts["count"] == 60


def test_run_keeps_highest_relevance_score_articles_when_capping(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    many = [
        Article(title=f"A{i}", url=f"https://example.com/{i}", source="search", source_name="s")
        for i in range(60)
    ]
    monkeypatch.setattr(main_module, "collect_search_articles", lambda keywords, api_key, cse_id: many)
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])

    def _fake_filter_by_relevance(articles, client, **kwargs):
        # Collection order is the reverse of relevance: the last article
        # collected is the most relevant one.
        for idx, article in enumerate(articles):
            article.relevance_score = idx
        return articles

    monkeypatch.setattr(main_module, "filter_by_relevance", _fake_filter_by_relevance)

    captured = {}

    def _fake_gemini_summarize(articles, client, **kwargs):
        captured["urls"] = [a.url for a in articles]
        for article in articles:
            article.summary = "要約"
            article.category = "seo"
        return articles

    monkeypatch.setattr(main_module, "gemini_summarize_and_classify", _fake_gemini_summarize)

    main_module.run(
        config_paths,
        secrets={
            "google_api_key": "k",
            "google_cse_id": "c",
            "anthropic_client": None,
            "gemini_client": object(),
            **_EMAIL_SECRETS,
        },
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    kept_indices = {int(url.rsplit("/", 1)[-1]) for url in captured["urls"]}
    assert kept_indices == set(range(20, 60))


def test_run_propagates_send_failure_and_leaves_state_unsaved(tmp_path, monkeypatch):
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

    def _failing_send(**kwargs):
        raise RuntimeError("SMTP error")

    monkeypatch.setattr(main_module, "send_email", _failing_send)

    with pytest.raises(RuntimeError):
        main_module.run(
            config_paths,
            secrets={
                "google_api_key": "k",
                "google_cse_id": "c",
                "anthropic_client": object(),
                **_EMAIL_SECRETS,
            },
            now_iso="2026-08-20T00:00:00+00:00",
            dry_run=False,
        )

    state_after_text = (tmp_path / "seen_articles.json").read_text(encoding="utf-8")
    assert state_after_text == state_before
    assert json.loads(state_after_text) == {}
