from .models import Article

_CATEGORY_LABELS = {
    "seo": "SEO",
    "ai": "AI",
    "ads": "広告",
    "event": "イベント",
    "other": "その他",
}
_CATEGORY_ORDER = ("seo", "ai", "ads", "event", "other")


def _escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_slack_blocks(articles: list[Article], today: str) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"BtoBマーケティング情報まとめ {today}"},
        }
    ]

    by_category: dict[str, list[Article]] = {c: [] for c in _CATEGORY_ORDER}
    for article in articles:
        category = article.category if article.category in _CATEGORY_ORDER else "other"
        by_category.setdefault(category, []).append(article)

    for category in _CATEGORY_ORDER:
        items = by_category.get(category, [])
        if not items:
            continue

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{_CATEGORY_LABELS[category]}*"},
        })
        for article in items:
            summary = _escape_mrkdwn(article.summary or "(要約なし)")
            title = _escape_mrkdwn(article.title)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{article.url}|{title}>\n{summary}",
                },
            })

    return blocks
