from difflib import SequenceMatcher

from .models import Article
from .state_store import is_seen, normalize_url


def _titles_similar(a: str, b: str, threshold: float) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def dedupe_articles(
    articles: list[Article],
    state: dict[str, str],
    title_similarity_threshold: float = 0.85,
) -> list[Article]:
    kept: list[Article] = []
    seen_urls: set[str] = set()

    for article in articles:
        norm_url = normalize_url(article.url)

        if is_seen(state, article.url):
            continue
        if norm_url in seen_urls:
            continue
        if any(_titles_similar(article.title, k.title, title_similarity_threshold) for k in kept):
            continue

        kept.append(article)
        seen_urls.add(norm_url)

    return kept
