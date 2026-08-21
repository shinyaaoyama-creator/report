import requests


def post_to_slack(blocks: list[dict], webhook_url: str, http_post=requests.post) -> None:
    response = http_post(webhook_url, json={"blocks": blocks}, timeout=10)
    response.raise_for_status()
