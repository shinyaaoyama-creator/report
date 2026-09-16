import re

from .models import Article

_GOOGLE_NEWS_NAME_PATTERN = re.compile(r'^"(.+)" - Google ニュース$')

# The "人事" Google News search mostly surfaces corporate personnel-change
# announcements (異動, 就任/退任 etc.), which aren't the HR-topic articles
# this keyword is meant to collect, so drop them explicitly.
_PERSONNEL_ANNOUNCEMENT_TERMS = [
    "人事異動",
    "人事発令",
    "異動",
    "新体制",
    "社長交代",
    "代表取締役",
    "取締役",
    "就任",
    "退任",
    "昇格",
    "昇進",
]


def extract_google_news_keyword(source_name: str) -> str | None:
    match = _GOOGLE_NEWS_NAME_PATTERN.match(source_name)
    return match.group(1) if match else None


def _is_personnel_announcement(title: str) -> bool:
    return any(term in title for term in _PERSONNEL_ANNOUNCEMENT_TERMS)


def filter_by_source_keyword(articles: list[Article]) -> list[Article]:
    filtered = []
    for article in articles:
        keyword = extract_google_news_keyword(article.source_name)
        if keyword is None:
            filtered.append(article)
            continue
        if keyword.lower() not in article.title.lower():
            continue
        if keyword == "人事" and _is_personnel_announcement(article.title):
            continue
        filtered.append(article)
    return filtered
