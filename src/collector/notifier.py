import requests

MAX_BLOCKS_PER_MESSAGE = 45


def post_to_slack(blocks: list[dict], webhook_url: str, http_post=requests.post) -> None:
    chunks = [
        blocks[i:i + MAX_BLOCKS_PER_MESSAGE]
        for i in range(0, len(blocks), MAX_BLOCKS_PER_MESSAGE)
    ] or [blocks]

    for chunk in chunks:
        response = http_post(webhook_url, json={"blocks": chunk}, timeout=10)
        response.raise_for_status()
