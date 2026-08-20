from dataclasses import dataclass

CATEGORIES = ("seo", "ai", "ads", "event", "other")


@dataclass
class Article:
    title: str
    url: str
    source: str
    source_name: str
    category_hint: str | None = None
    published_at: str | None = None
    summary: str | None = None
    category: str | None = None
