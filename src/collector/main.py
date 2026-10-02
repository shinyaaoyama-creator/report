import argparse
import logging
import os
import socket

from .config import load_feeds, load_keywords
from .dedup import dedupe_articles
from .formatter import build_email_html
from .gemini_summarizer import summarize_and_classify as gemini_summarize_and_classify
from .notifier import send_email
from .recency_filter import filter_by_recency
from .relevance_filter import filter_by_source_keyword
from .relevance_filter_ai import filter_by_relevance
from .rss_collector import collect_rss_articles
from .search_collector import collect_search_articles
from .state_store import load_state, mark_seen, prune_old, save_state
from .summarizer import apply_category_hint_fallback, summarize_and_classify

logger = logging.getLogger(__name__)

# feedparser.parse() has no timeout of its own; without this a dead feed host
# can hang the whole job indefinitely.
socket.setdefaulttimeout(15)

MAX_ARTICLES_PER_RUN = 40
MAX_ARTICLE_AGE_DAYS = 3


def run(config_paths: dict, secrets: dict, now_iso: str, dry_run: bool = False) -> str:
    keywords = load_keywords(config_paths["keywords"])
    feeds = load_feeds(config_paths["feeds"])
    state = load_state(config_paths["state"])

    search_articles = collect_search_articles(keywords, secrets["google_api_key"], secrets["google_cse_id"])
    rss_articles = collect_rss_articles(feeds)
    combined_articles = filter_by_source_keyword(search_articles + rss_articles)
    combined_articles = filter_by_recency(combined_articles, now_iso, max_age_days=MAX_ARTICLE_AGE_DAYS)
    articles = dedupe_articles(combined_articles, state)

    gemini_client = secrets.get("gemini_client")
    if gemini_client is not None:
        # Free-tier Gemini rate limits are per-minute; pace batches so we
        # don't burst past them and fall back to fail-open unfiltered results.
        articles = filter_by_relevance(articles, gemini_client, request_interval_seconds=4.5)
        articles.sort(key=lambda a: a.relevance_score if a.relevance_score is not None else 0, reverse=True)

    if len(articles) > MAX_ARTICLES_PER_RUN:
        logger.warning(
            "capping articles for this run: %d -> %d", len(articles), MAX_ARTICLES_PER_RUN
        )
        articles = articles[:MAX_ARTICLES_PER_RUN]

    anthropic_client = secrets.get("anthropic_client")
    if gemini_client is not None:
        articles = gemini_summarize_and_classify(articles, gemini_client, request_interval_seconds=4.5)
    elif anthropic_client is not None:
        articles = summarize_and_classify(articles, anthropic_client)
    else:
        logger.info("no AI client provided; skipping AI summarization/classification")
        articles = apply_category_hint_fallback(articles)

    today = now_iso[:10]
    html_body = build_email_html(articles, today=today)

    if dry_run:
        return html_body

    send_email(
        subject=f"BtoBマーケティング情報まとめ {today}",
        html_body=html_body,
        from_addr=secrets["email_from"],
        to_addr=secrets["email_to"],
        smtp_host=secrets["smtp_host"],
        smtp_port=secrets["smtp_port"],
        smtp_username=secrets["smtp_username"],
        smtp_password=secrets["smtp_password"],
    )

    for article in articles:
        mark_seen(state, article.url, now_iso)
    state = prune_old(state, now=now_iso, days=30)
    save_state(config_paths["state"], state)

    return html_body


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from datetime import datetime, timezone

    # google-genai reads the GOOGLE_API_KEY env var itself and prefers it over
    # an explicitly passed api_key, so it must be removed before constructing
    # the Gemini client or Gemini calls silently use the Custom Search key.
    google_api_key = os.environ.pop("GOOGLE_API_KEY")
    google_cse_id = os.environ["GOOGLE_CSE_ID"]

    anthropic_client = None
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        import anthropic

        anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
    else:
        logger.info("ANTHROPIC_API_KEY not set; running without Claude-based summarization/classification")

    gemini_client = None
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        from google import genai

        gemini_client = genai.Client(api_key=gemini_api_key)
    else:
        logger.info("GEMINI_API_KEY not set; running without Gemini-based relevance filtering/summarization")

    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    email_to = os.environ.get("EMAIL_TO")
    if not args.dry_run and not (smtp_username and smtp_password and email_to):
        parser.error("SMTP_USERNAME, SMTP_PASSWORD and EMAIL_TO are required unless --dry-run is used")

    config_paths = {
        "keywords": "config/keywords.yaml",
        "feeds": "config/feeds.yaml",
        "state": "state/seen_articles.json",
    }
    secrets = {
        "google_api_key": google_api_key,
        "google_cse_id": google_cse_id,
        "anthropic_client": anthropic_client,
        "gemini_client": gemini_client,
        "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "email_from": os.environ.get("EMAIL_FROM", smtp_username),
        "email_to": email_to,
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    html_body = run(config_paths, secrets, now_iso, dry_run=args.dry_run)
    if args.dry_run:
        print(html_body)


if __name__ == "__main__":
    main()
