import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid")


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    kept_params = [
        (k, v) for k, v in parse_qsl(parts.query)
        if not any(k.startswith(p) or k == p for p in _TRACKING_PREFIXES)
    ]
    query = urlencode(kept_params)
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def load_state(path: str) -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def is_seen(state: dict[str, str], url: str) -> bool:
    return normalize_url(url) in state


def mark_seen(state: dict[str, str], url: str, seen_at: str) -> None:
    state[normalize_url(url)] = seen_at


def prune_old(state: dict[str, str], now: str, days: int = 30) -> dict[str, str]:
    threshold = datetime.fromisoformat(now) - timedelta(days=days)
    return {
        url: seen_at
        for url, seen_at in state.items()
        if datetime.fromisoformat(seen_at) >= threshold
    }
