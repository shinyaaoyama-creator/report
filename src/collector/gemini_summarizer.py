import json
import logging
import time

from .gemini_utils import MODEL, call_with_retries
from .models import Article, CATEGORIES
from .summarizer import apply_category_hint_fallback

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
次の記事それぞれについて、日本語で3行以内の要約と、カテゴリ（{categories}のいずれか1つ）を判定してください。
出力は必ず次のJSON配列形式のみで返してください（説明文は不要）：
[{{"url": "記事のURL", "summary": "3行要約", "category": "カテゴリ名"}}, ...]

記事一覧:
{articles_json}
"""


def _build_prompt(batch: list[Article]) -> str:
    articles_json = json.dumps(
        [{"url": a.url, "title": a.title} for a in batch],
        ensure_ascii=False,
    )
    return _PROMPT_TEMPLATE.format(categories="/".join(CATEGORIES), articles_json=articles_json)


def summarize_and_classify(
    articles: list[Article],
    client,
    batch_size: int = 10,
    max_retries: int = 3,
    request_interval_seconds: float = 0,
) -> list[Article]:
    apply_category_hint_fallback(articles)

    for i in range(0, len(articles), batch_size):
        if i > 0 and request_interval_seconds:
            time.sleep(request_interval_seconds)
        batch = articles[i:i + batch_size]
        raw = call_with_retries(client, MODEL, _build_prompt(batch), max_retries)
        if raw is None:
            continue

        try:
            results = {item["url"]: item for item in json.loads(raw)}
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("failed to parse summarizer response: %r", raw)
            continue

        for article in batch:
            result = results.get(article.url)
            if result is None:
                continue
            article.summary = result.get("summary")
            category = result.get("category")
            article.category = category if category in CATEGORIES else "other"

    return articles
