import logging

import feedparser

from .models import Article

logger = logging.getLogger(__name__)


def fetch_feed_articles(feed: dict, parse_fn=feedparser.parse) -> list[Article]:
    parsed = parse_fn(feed["url"])
    if getattr(parsed, "bozo", False):
        raise ValueError(f"failed to parse feed: {feed['url']}")

    return [
        Article(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            source="rss",
            source_name=feed["name"],
            category_hint=feed.get("category_hint"),
            published_at=entry.get("published"),
        )
        for entry in parsed.entries
    ]


def collect_rss_articles(feeds: list[dict], parse_fn=feedparser.parse) -> list[Article]:
    articles: list[Article] = []
    for feed in feeds:
        try:
            articles.extend(fetch_feed_articles(feed, parse_fn=parse_fn))
        except Exception:
            logger.warning("rss fetch failed for feed=%r", feed.get("name"), exc_info=True)
    return articles
