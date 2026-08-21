import logging

import feedparser

from .models import Article

logger = logging.getLogger(__name__)


def fetch_feed_articles(feed: dict, parse_fn=feedparser.parse) -> list[Article]:
    parsed = parse_fn(feed["url"])
    # feedparser sets bozo=1 for many non-fatal issues (encoding quirks, minor
    # XML defects) while still populating entries correctly; only treat it as a
    # failure when there is nothing usable to show.
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        raise ValueError(f"failed to parse feed: {feed['url']}")

    articles: list[Article] = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            logger.warning("skipping entry without link in feed=%r", feed.get("name"))
            continue
        articles.append(
            Article(
                title=entry.get("title", ""),
                url=link,
                source="rss",
                source_name=feed["name"],
                category_hint=feed.get("category_hint"),
                published_at=entry.get("published"),
            )
        )
    return articles


def collect_rss_articles(feeds: list[dict], parse_fn=feedparser.parse) -> list[Article]:
    articles: list[Article] = []
    for feed in feeds:
        try:
            articles.extend(fetch_feed_articles(feed, parse_fn=parse_fn))
        except Exception:
            logger.warning("rss fetch failed for feed=%r", feed.get("name"), exc_info=True)
    return articles
