import json
import logging
import time

from .models import Article, CATEGORIES

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

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


def _call_with_retries(client, prompt: str, max_retries: int) -> str | None:
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception:
            logger.warning("summarize call failed (attempt %d/%d)", attempt + 1, max_retries, exc_info=True)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return None


def summarize_and_classify(
    articles: list[Article],
    client,
    batch_size: int = 10,
    max_retries: int = 3,
) -> list[Article]:
    for article in articles:
        if article.category is None:
            if article.category_hint in CATEGORIES:
                article.category = article.category_hint
            else:
                article.category = "other"

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        raw = _call_with_retries(client, _build_prompt(batch), max_retries)
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
