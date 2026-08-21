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
