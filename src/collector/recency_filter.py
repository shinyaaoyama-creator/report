from datetime import datetime
from email.utils import parsedate_to_datetime

from .models import Article


def _parse_published_at(published_at: str) -> datetime | None:
    try:
        return parsedate_to_datetime(published_at)
    except (TypeError, ValueError):
        pass

    try:
        return datetime.fromisoformat(published_at)
    except ValueError:
        return None


def filter_by_recency(articles: list[Article], now_iso: str, max_age_days: int) -> list[Article]:
    now = datetime.fromisoformat(now_iso)
    kept: list[Article] = []

    for article in articles:
        if not article.published_at:
            kept.append(article)
            continue

        published_at = _parse_published_at(article.published_at)
        if published_at is None:
            kept.append(article)
            continue

        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=now.tzinfo)

        age_days = (now - published_at).total_seconds() / 86400
        if age_days <= max_age_days:
            kept.append(article)

    return kept
