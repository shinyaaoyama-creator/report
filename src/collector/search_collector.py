import logging

import requests

from .models import Article

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def fetch_search_results(
    keyword: str,
    category: str,
    api_key: str,
    cse_id: str,
    http_get=requests.get,
) -> list[Article]:
    response = http_get(
        SEARCH_ENDPOINT,
        params={"key": api_key, "cx": cse_id, "q": keyword},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    return [
        Article(
            title=item["title"],
            url=item["link"],
            source="search",
            source_name=f"google_cse:{keyword}",
            category_hint=category,
        )
        for item in payload.get("items", [])
    ]


def collect_search_articles(
    keywords: dict[str, list[str]],
    api_key: str,
    cse_id: str,
    http_get=requests.get,
) -> list[Article]:
    articles: list[Article] = []
    for category, words in keywords.items():
        for keyword in words:
            try:
                articles.extend(
                    fetch_search_results(keyword, category, api_key, cse_id, http_get=http_get)
                )
            except Exception:
                logger.warning("search failed for keyword=%r category=%r", keyword, category, exc_info=True)
    return articles
