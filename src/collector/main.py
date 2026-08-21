import argparse
import logging
import os

from .config import load_feeds, load_keywords
from .dedup import dedupe_articles
from .formatter import build_slack_blocks
from .notifier import post_to_slack
from .rss_collector import collect_rss_articles
from .search_collector import collect_search_articles
from .state_store import load_state, mark_seen, prune_old, save_state
from .summarizer import summarize_and_classify

logger = logging.getLogger(__name__)

MAX_ARTICLES_PER_RUN = 40


def run(config_paths: dict, secrets: dict, now_iso: str, dry_run: bool = False) -> list[dict]:
    keywords = load_keywords(config_paths["keywords"])
    feeds = load_feeds(config_paths["feeds"])
    state = load_state(config_paths["state"])

    search_articles = collect_search_articles(keywords, secrets["google_api_key"], secrets["google_cse_id"])
    rss_articles = collect_rss_articles(feeds)
    articles = dedupe_articles(search_articles + rss_articles, state)
    if len(articles) > MAX_ARTICLES_PER_RUN:
        logger.warning(
            "capping articles for this run: %d -> %d", len(articles), MAX_ARTICLES_PER_RUN
        )
        articles = articles[:MAX_ARTICLES_PER_RUN]
    articles = summarize_and_classify(articles, secrets["anthropic_client"])

    today = now_iso[:10]
    blocks = build_slack_blocks(articles, today=today)

    if dry_run:
        return blocks

    post_to_slack(blocks, secrets["slack_webhook_url"])

    for article in articles:
        mark_seen(state, article.url, now_iso)
    state = prune_old(state, now=now_iso, days=30)
    save_state(config_paths["state"], state)

    return blocks


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import anthropic
    from datetime import datetime, timezone

    config_paths = {
        "keywords": "config/keywords.yaml",
        "feeds": "config/feeds.yaml",
        "state": "state/seen_articles.json",
    }
    secrets = {
        "google_api_key": os.environ["GOOGLE_API_KEY"],
        "google_cse_id": os.environ["GOOGLE_CSE_ID"],
        "anthropic_client": anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
        "slack_webhook_url": os.environ["SLACK_WEBHOOK_URL"],
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    run(config_paths, secrets, now_iso, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
