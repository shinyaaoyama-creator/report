import re

from .models import Article

_GOOGLE_NEWS_NAME_PATTERN = re.compile(r'^"(.+)" - Google ニュース$')


def extract_google_news_keyword(source_name: str) -> str | None:
    match = _GOOGLE_NEWS_NAME_PATTERN.match(source_name)
    return match.group(1) if match else None


def filter_by_source_keyword(articles: list[Article]) -> list[Article]:
    filtered = []
    for article in articles:
        keyword = extract_google_news_keyword(article.source_name)
        if keyword is None or keyword.lower() in article.title.lower():
            filtered.append(article)
    return filtered
