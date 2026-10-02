from html import escape

from .models import Article

_CATEGORY_LABELS = {
    "seo": "SEO",
    "ai": "AI",
    "ads": "広告",
    "event": "イベント",
    "other": "その他",
}
_CATEGORY_ORDER = ("seo", "ai", "ads", "event", "other")


def build_email_html(articles: list[Article], today: str) -> str:
    by_category: dict[str, list[Article]] = {c: [] for c in _CATEGORY_ORDER}
    for article in articles:
        category = article.category if article.category in _CATEGORY_ORDER else "other"
        by_category.setdefault(category, []).append(article)

    sections = []
    for category in _CATEGORY_ORDER:
        items = by_category.get(category, [])
        if not items:
            continue

        entries = "".join(
            "<li>"
            f'<a href="{escape(article.url, quote=True)}">{escape(article.title)}</a>'
            f"<br>{escape(article.summary or '(要約なし)')}"
            "</li>"
            for article in items
        )
        sections.append(f"<h2>{_CATEGORY_LABELS[category]}</h2><ul>{entries}</ul>")

    body = "".join(sections) if sections else "<p>該当する記事はありませんでした。</p>"
    return f"<html><body><h1>BtoBマーケティング情報まとめ {escape(today)}</h1>{body}</body></html>"
