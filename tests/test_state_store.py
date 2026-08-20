import json

from src.collector import state_store


def test_normalize_url_strips_tracking_params():
    url = "https://example.com/article?id=1&utm_source=twitter&utm_medium=social"
    assert state_store.normalize_url(url) == "https://example.com/article?id=1"


def test_normalize_url_strips_trailing_slash():
    assert state_store.normalize_url("https://example.com/a/") == "https://example.com/a"


def test_load_state_missing_file_returns_empty(tmp_path):
    path = tmp_path / "seen.json"
    assert state_store.load_state(str(path)) == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    state = {"https://example.com/a": "2026-08-20T09:00:00+09:00"}
    state_store.save_state(str(path), state)

    loaded = state_store.load_state(str(path))

    assert loaded == state
    assert json.loads(path.read_text(encoding="utf-8")) == state


def test_is_seen_and_mark_seen():
    state = {}
    url = "https://example.com/a?utm_source=x"
    assert state_store.is_seen(state, url) is False

    state_store.mark_seen(state, url, "2026-08-20T09:00:00+09:00")

    assert state_store.is_seen(state, url) is True
    assert state_store.is_seen(state, "https://example.com/a") is True


def test_prune_old_removes_entries_past_threshold():
    state = {
        "https://example.com/old": "2026-07-01T00:00:00+00:00",
        "https://example.com/new": "2026-08-19T00:00:00+00:00",
    }

    pruned = state_store.prune_old(state, now="2026-08-20T00:00:00+00:00", days=30)

    assert "https://example.com/old" not in pruned
    assert "https://example.com/new" in pruned
