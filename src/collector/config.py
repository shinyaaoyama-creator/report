import yaml


def load_keywords(path: str) -> dict[str, list[str]]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {category: list(words) for category, words in data.items()}


def load_feeds(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    feeds = []
    for entry in data:
        feeds.append({
            "name": entry["name"],
            "url": entry["url"],
            "category_hint": entry.get("category_hint"),
        })
    return feeds
