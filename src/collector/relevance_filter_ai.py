import json
import logging
import time

from .gemini_utils import MODEL, call_with_retries
from .models import Article, CATEGORIES

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
次の記事それぞれについて、BtoBマーケティング関連トピック（{categories}）に実際に関連する内容かどうかを判定してください。
タイトルにキーワードが含まれていても、内容が無関係と推測される場合は relevant を false にしてください。
出力は必ず次のJSON配列形式のみで返してください（説明文は不要）：
[{{"url": "記事のURL", "relevant": true または false}}, ...]

記事一覧:
{articles_json}
"""


def _build_prompt(batch: list[Article]) -> str:
    articles_json = json.dumps(
        [{"url": a.url, "title": a.title} for a in batch],
        ensure_ascii=False,
    )
    return _PROMPT_TEMPLATE.format(categories="/".join(CATEGORIES), articles_json=articles_json)


def filter_by_relevance(
    articles: list[Article],
    client,
    batch_size: int = 50,
    max_retries: int = 3,
    request_interval_seconds: float = 0,
) -> list[Article]:
    kept: list[Article] = []

    for i in range(0, len(articles), batch_size):
        if i > 0 and request_interval_seconds:
            time.sleep(request_interval_seconds)
        batch = articles[i:i + batch_size]
        raw = call_with_retries(client, MODEL, _build_prompt(batch), max_retries)
        if raw is None:
            logger.warning("relevance check failed for batch; keeping %d articles unfiltered", len(batch))
            kept.extend(batch)
            continue

        try:
            results = {item["url"]: item.get("relevant", True) for item in json.loads(raw)}
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("failed to parse relevance response: %r; keeping batch unfiltered", raw)
            kept.extend(batch)
            continue

        for article in batch:
            if results.get(article.url, True):
                kept.append(article)

    return kept
