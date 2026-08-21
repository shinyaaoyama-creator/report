import pytest

from src.collector.notifier import post_to_slack


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_post_to_slack_sends_blocks_payload():
    captured = {}

    def _post(url, json, timeout=10):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(200)

    post_to_slack([{"type": "header"}], "https://hooks.slack.com/services/x", http_post=_post)

    assert captured["url"] == "https://hooks.slack.com/services/x"
    assert captured["json"] == {"blocks": [{"type": "header"}]}


def test_post_to_slack_raises_on_failure():
    def _post(url, json, timeout=10):
        return _FakeResponse(500)

    with pytest.raises(RuntimeError):
        post_to_slack([{"type": "header"}], "https://hooks.slack.com/services/x", http_post=_post)


def test_post_to_slack_chunks_blocks_over_limit():
    blocks = [{"type": "section", "id": i} for i in range(60)]
    calls = []

    def _post(url, json, timeout=10):
        calls.append(json["blocks"])
        return _FakeResponse(200)

    post_to_slack(blocks, "https://hooks.slack.com/services/x", http_post=_post)

    assert len(calls) > 1
    assert all(len(chunk) <= 45 for chunk in calls)
    flattened = [block for chunk in calls for block in chunk]
    assert flattened == blocks


def test_post_to_slack_sends_single_post_under_limit():
    blocks = [{"type": "section", "id": i} for i in range(10)]
    calls = []

    def _post(url, json, timeout=10):
        calls.append(json["blocks"])
        return _FakeResponse(200)

    post_to_slack(blocks, "https://hooks.slack.com/services/x", http_post=_post)

    assert len(calls) == 1
    assert calls[0] == blocks


def test_post_to_slack_propagates_failure_on_later_chunk():
    blocks = [{"type": "section", "id": i} for i in range(60)]
    calls = []

    def _post(url, json, timeout=10):
        calls.append(json["blocks"])
        return _FakeResponse(200 if len(calls) == 1 else 500)

    with pytest.raises(RuntimeError):
        post_to_slack(blocks, "https://hooks.slack.com/services/x", http_post=_post)

    assert len(calls) == 2
