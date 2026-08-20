# 検索＋RSS収集 Slack日次配信 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BtoBマーケティング関連情報をGoogle Custom Search APIとRSSフィードから日次収集し、Claude APIで要約・カテゴリ分類・重複除去した上でSlackに配信するGitHub Actionsパイプラインを構築する。

**Architecture:** Pythonスクリプト群（collector → dedup → summarizer → formatter → notifier）をGitHub Actionsのcronジョブから実行し、状態（既配信記事リスト）はリポジトリ内のJSONファイルとして永続化する。外部DBは使わない。

**Tech Stack:** Python 3.11+, requests, feedparser, PyYAML, anthropic (Claude API), pytest

**Spec:** `docs/superpowers/specs/2026-08-20-search-rss-collector-design.md`

## Global Constraints

- 実行スケジュール: 日次1回、UTC `0 0 * * *`（JST 9:00）
- Google Custom Search APIは無料枠100クエリ/日の範囲で運用する（キーワード数はこの制約内に収める）
- 配信先はSlack Incoming Webhookのみ（メールは対象外）
- 要約・カテゴリ分類はClaude API（モデル: `claude-haiku-4-5-20251001`）を使う
- カテゴリは `seo` / `ai` / `ads`（広告） / `event`（イベント） / `other`（その他）の5種で固定
- 状態管理はリポジトリ内JSONファイル（`state/seen_articles.json`）で行い、外部DBは使わない
- RSSフィードリストはInoreaderのOPMLエクスポートから生成した固定リストを使う（Inoreader APIは無料プランでは利用不可のため使用しない）
- 収集の部分失敗（個別のキーワード検索・フィード取得の失敗）は全体を止めずスキップする
- Slack投稿の失敗はGitHub Actionsのジョブを失敗させる（追加通知は設けない）

---

## File Structure

```
情報収集アプリ/
├── config/
│   ├── keywords.yaml
│   └── feeds.yaml
├── state/
│   └── seen_articles.json
├── scripts/
│   └── opml_to_feeds.py
├── src/
│   └── collector/
│       ├── __init__.py
│       ├── models.py
│       ├── config.py
│       ├── state_store.py
│       ├── dedup.py
│       ├── search_collector.py
│       ├── rss_collector.py
│       ├── summarizer.py
│       ├── formatter.py
│       ├── notifier.py
│       └── main.py
├── tests/
│   ├── test_config.py
│   ├── test_state_store.py
│   ├── test_dedup.py
│   ├── test_search_collector.py
│   ├── test_rss_collector.py
│   ├── test_summarizer.py
│   ├── test_formatter.py
│   ├── test_notifier.py
│   └── test_main.py
├── .github/workflows/daily_digest.yml
├── requirements.txt
└── .env.example
```

---

### Task 1: データモデル・設定ローダー

**Files:**
- Create: `src/collector/models.py`
- Create: `src/collector/config.py`
- Create: `config/keywords.yaml`
- Create: `config/feeds.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `models.Article` dataclass: `title: str`, `url: str`, `source: str`（`"search"` or `"rss"`）, `source_name: str`, `category_hint: str | None`, `published_at: str | None`, `summary: str | None = None`, `category: str | None = None`
  - `models.CATEGORIES = ("seo", "ai", "ads", "event", "other")`
  - `config.load_keywords(path: str) -> dict[str, list[str]]`（キー: category, 値: キーワードリスト）
  - `config.load_feeds(path: str) -> list[dict]`（各要素: `{"url": str, "category_hint": str | None, "name": str}`）

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import textwrap
from src.collector import config


def test_load_keywords(tmp_path):
    p = tmp_path / "keywords.yaml"
    p.write_text(textwrap.dedent("""\
        seo:
          - コンテンツSEO
          - 検索アルゴリズム
        ai:
          - 生成AI 活用
        ads:
          - リスティング広告
        event:
          - BtoB展示会
        """), encoding="utf-8")

    result = config.load_keywords(str(p))

    assert result["seo"] == ["コンテンツSEO", "検索アルゴリズム"]
    assert result["ai"] == ["生成AI 活用"]
    assert result["ads"] == ["リスティング広告"]
    assert result["event"] == ["BtoB展示会"]


def test_load_feeds(tmp_path):
    p = tmp_path / "feeds.yaml"
    p.write_text(textwrap.dedent("""\
        - name: Example Blog
          url: https://example.com/feed.xml
          category_hint: seo
        - name: No Hint Blog
          url: https://example.org/rss
        """), encoding="utf-8")

    result = config.load_feeds(str(p))

    assert result == [
        {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"},
        {"name": "No Hint Blog", "url": "https://example.org/rss", "category_hint": None},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.config'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/models.py`:
```python
from dataclasses import dataclass

CATEGORIES = ("seo", "ai", "ads", "event", "other")


@dataclass
class Article:
    title: str
    url: str
    source: str
    source_name: str
    category_hint: str | None = None
    published_at: str | None = None
    summary: str | None = None
    category: str | None = None
```

`src/collector/config.py`:
```python
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
```

`src/collector/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Create initial config files**

`config/keywords.yaml`:
```yaml
seo:
  - コンテンツSEO
  - 検索アルゴリズム アップデート
ai:
  - 生成AI マーケティング
  - AI エージェント BtoB
ads:
  - リスティング広告 BtoB
  - LinkedIn広告
event:
  - BtoB展示会
  - マーケティング カンファレンス
```

`config/feeds.yaml`:
```yaml
[]
```

(Task 11でInoreaderのOPMLから実データを流し込む。ここでは空リストで動作確認できる状態にする。)

- [ ] **Step 6: Commit**

```bash
git add src/collector/__init__.py src/collector/models.py src/collector/config.py config/keywords.yaml config/feeds.yaml tests/test_config.py
git commit -m "feat: add Article model and config loaders for keywords/feeds"
```

---

### Task 2: State Store（既配信リスト管理）

**Files:**
- Create: `src/collector/state_store.py`
- Create: `state/seen_articles.json`
- Test: `tests/test_state_store.py`

**Interfaces:**
- Consumes: なし（独立モジュール）
- Produces:
  - `state_store.normalize_url(url: str) -> str`
  - `state_store.load_state(path: str) -> dict[str, str]`（キー: normalized url, 値: ISO8601配信日時）
  - `state_store.save_state(path: str, state: dict[str, str]) -> None`
  - `state_store.is_seen(state: dict[str, str], url: str) -> bool`
  - `state_store.mark_seen(state: dict[str, str], url: str, seen_at: str) -> None`
  - `state_store.prune_old(state: dict[str, str], now: str, days: int = 30) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

`tests/test_state_store.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.state_store'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/state_store.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_state_store.py -v`
Expected: PASS

- [ ] **Step 5: Create initial state file**

`state/seen_articles.json`:
```json
{}
```

- [ ] **Step 6: Commit**

```bash
git add src/collector/state_store.py state/seen_articles.json tests/test_state_store.py
git commit -m "feat: add state store for tracking previously delivered articles"
```

---

### Task 3: 重複除去（Dedup）

**Files:**
- Create: `src/collector/dedup.py`
- Test: `tests/test_dedup.py`

**Interfaces:**
- Consumes: `models.Article`（Task 1）, `state_store.normalize_url`, `state_store.is_seen`（Task 2）
- Produces: `dedup.dedupe_articles(articles: list[Article], state: dict[str, str], title_similarity_threshold: float = 0.85) -> list[Article]`

- [ ] **Step 1: Write the failing test**

`tests/test_dedup.py`:
```python
from src.collector.dedup import dedupe_articles
from src.collector.models import Article


def _article(title, url, source="search"):
    return Article(title=title, url=url, source=source, source_name="test")


def test_removes_articles_already_in_state():
    state = {"https://example.com/a": "2026-08-19T09:00:00+00:00"}
    articles = [_article("A", "https://example.com/a?utm_source=x")]

    result = dedupe_articles(articles, state)

    assert result == []


def test_removes_exact_url_duplicates_across_sources():
    articles = [
        _article("A", "https://example.com/a", source="search"),
        _article("A (via RSS)", "https://example.com/a?utm_source=feed", source="rss"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 1


def test_removes_near_duplicate_titles_different_urls():
    articles = [
        _article("生成AIがBtoBマーケティングを変える", "https://example.com/a"),
        _article("生成AIがBtoBマーケティングを変える！", "https://example.org/b"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 1


def test_keeps_distinct_articles():
    articles = [
        _article("SEOの新しい潮流", "https://example.com/a"),
        _article("広告オークションの変化", "https://example.org/b"),
    ]

    result = dedupe_articles(articles, state={})

    assert len(result) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.dedup'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/dedup.py`:
```python
from difflib import SequenceMatcher

from .models import Article
from .state_store import is_seen, normalize_url


def _titles_similar(a: str, b: str, threshold: float) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= threshold


def dedupe_articles(
    articles: list[Article],
    state: dict[str, str],
    title_similarity_threshold: float = 0.85,
) -> list[Article]:
    kept: list[Article] = []
    seen_urls: set[str] = set()

    for article in articles:
        norm_url = normalize_url(article.url)

        if is_seen(state, article.url):
            continue
        if norm_url in seen_urls:
            continue
        if any(_titles_similar(article.title, k.title, title_similarity_threshold) for k in kept):
            continue

        kept.append(article)
        seen_urls.add(norm_url)

    return kept
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dedup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/dedup.py tests/test_dedup.py
git commit -m "feat: add dedup logic for state, cross-source, and near-duplicate titles"
```

---

### Task 4: Search Collector（Google Custom Search API）

**Files:**
- Create: `src/collector/search_collector.py`
- Test: `tests/test_search_collector.py`

**Interfaces:**
- Consumes: `models.Article`（Task 1）
- Produces:
  - `search_collector.fetch_search_results(keyword: str, category: str, api_key: str, cse_id: str, http_get=requests.get) -> list[Article]`
  - `search_collector.collect_search_articles(keywords: dict[str, list[str]], api_key: str, cse_id: str, http_get=requests.get) -> list[Article]`（個別キーワードの失敗はログに残しスキップ）

- [ ] **Step 1: Write the failing test**

`tests/test_search_collector.py`:
```python
import logging

from src.collector.search_collector import collect_search_articles, fetch_search_results


def _fake_http_get(response_by_query):
    def _get(url, params, timeout=10):
        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self._payload

        return _Resp(response_by_query[params["q"]])

    return _get


def test_fetch_search_results_maps_items_to_articles():
    payload = {
        "items": [
            {"title": "記事A", "link": "https://example.com/a"},
            {"title": "記事B", "link": "https://example.com/b"},
        ]
    }
    http_get = _fake_http_get({"コンテンツSEO": payload})

    result = fetch_search_results("コンテンツSEO", "seo", "key", "cse", http_get=http_get)

    assert len(result) == 2
    assert result[0].title == "記事A"
    assert result[0].url == "https://example.com/a"
    assert result[0].source == "search"
    assert result[0].category_hint == "seo"


def test_fetch_search_results_handles_no_items():
    http_get = _fake_http_get({"存在しないキーワード": {}})

    result = fetch_search_results("存在しないキーワード", "seo", "key", "cse", http_get=http_get)

    assert result == []


def test_collect_search_articles_skips_failing_keyword(caplog):
    def _get(url, params, timeout=10):
        if params["q"] == "失敗するキーワード":
            raise ConnectionError("boom")

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"items": [{"title": "OK記事", "link": "https://example.com/ok"}]}

        return _Resp()

    keywords = {"seo": ["失敗するキーワード", "正常なキーワード"]}

    with caplog.at_level(logging.WARNING):
        result = collect_search_articles(keywords, "key", "cse", http_get=_get)

    assert len(result) == 1
    assert result[0].title == "OK記事"
    assert "失敗するキーワード" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.search_collector'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/search_collector.py`:
```python
import logging

import requests

from .models import Article

logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


def fetch_search_results(
    keyword: str,
    category: str,
    api_key: str,
    cse_id: str,
    http_get=requests.get,
) -> list[Article]:
    response = http_get(
        SEARCH_ENDPOINT,
        params={"key": api_key, "cx": cse_id, "q": keyword},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    return [
        Article(
            title=item["title"],
            url=item["link"],
            source="search",
            source_name=f"google_cse:{keyword}",
            category_hint=category,
        )
        for item in payload.get("items", [])
    ]


def collect_search_articles(
    keywords: dict[str, list[str]],
    api_key: str,
    cse_id: str,
    http_get=requests.get,
) -> list[Article]:
    articles: list[Article] = []
    for category, words in keywords.items():
        for keyword in words:
            try:
                articles.extend(
                    fetch_search_results(keyword, category, api_key, cse_id, http_get=http_get)
                )
            except Exception:
                logger.warning("search failed for keyword=%r category=%r", keyword, category, exc_info=True)
    return articles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_collector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/search_collector.py tests/test_search_collector.py
git commit -m "feat: add Google Custom Search collector with per-keyword failure isolation"
```

---

### Task 5: RSS Collector（feedparser）

**Files:**
- Create: `src/collector/rss_collector.py`
- Test: `tests/test_rss_collector.py`

**Interfaces:**
- Consumes: `models.Article`（Task 1）
- Produces:
  - `rss_collector.fetch_feed_articles(feed: dict, parse_fn=feedparser.parse) -> list[Article]`（`feed` は `{"name", "url", "category_hint"}`）
  - `rss_collector.collect_rss_articles(feeds: list[dict], parse_fn=feedparser.parse) -> list[Article]`（個別フィードの失敗はログに残しスキップ）

- [ ] **Step 1: Write the failing test**

`tests/test_rss_collector.py`:
```python
import logging

from src.collector.rss_collector import collect_rss_articles, fetch_feed_articles


class _FakeEntry(dict):
    def __getattr__(self, name):
        return self[name]


class _FakeParsed:
    def __init__(self, entries, bozo=False):
        self.entries = entries
        self.bozo = bozo


def test_fetch_feed_articles_maps_entries_to_articles():
    parsed = _FakeParsed([
        _FakeEntry(title="記事A", link="https://example.com/a", published="2026-08-19"),
    ])
    feed = {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"}

    result = fetch_feed_articles(feed, parse_fn=lambda url: parsed)

    assert len(result) == 1
    assert result[0].title == "記事A"
    assert result[0].url == "https://example.com/a"
    assert result[0].source == "rss"
    assert result[0].source_name == "Example Blog"
    assert result[0].category_hint == "seo"
    assert result[0].published_at == "2026-08-19"


def test_fetch_feed_articles_bozo_raises():
    parsed = _FakeParsed([], bozo=True)
    feed = {"name": "Broken Feed", "url": "https://example.com/broken.xml", "category_hint": None}

    try:
        fetch_feed_articles(feed, parse_fn=lambda url: parsed)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_collect_rss_articles_skips_failing_feed(caplog):
    good_parsed = _FakeParsed([_FakeEntry(title="OK記事", link="https://example.com/ok", published=None)])

    def _parse(url):
        if url == "https://example.com/broken.xml":
            return _FakeParsed([], bozo=True)
        return good_parsed

    feeds = [
        {"name": "Broken Feed", "url": "https://example.com/broken.xml", "category_hint": None},
        {"name": "Good Feed", "url": "https://example.com/good.xml", "category_hint": "ai"},
    ]

    with caplog.at_level(logging.WARNING):
        result = collect_rss_articles(feeds, parse_fn=_parse)

    assert len(result) == 1
    assert result[0].title == "OK記事"
    assert "Broken Feed" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rss_collector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.rss_collector'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/rss_collector.py`:
```python
import logging

import feedparser

from .models import Article

logger = logging.getLogger(__name__)


def fetch_feed_articles(feed: dict, parse_fn=feedparser.parse) -> list[Article]:
    parsed = parse_fn(feed["url"])
    if getattr(parsed, "bozo", False):
        raise ValueError(f"failed to parse feed: {feed['url']}")

    return [
        Article(
            title=entry.get("title", ""),
            url=entry.get("link", ""),
            source="rss",
            source_name=feed["name"],
            category_hint=feed.get("category_hint"),
            published_at=entry.get("published"),
        )
        for entry in parsed.entries
    ]


def collect_rss_articles(feeds: list[dict], parse_fn=feedparser.parse) -> list[Article]:
    articles: list[Article] = []
    for feed in feeds:
        try:
            articles.extend(fetch_feed_articles(feed, parse_fn=parse_fn))
        except Exception:
            logger.warning("rss fetch failed for feed=%r", feed.get("name"), exc_info=True)
    return articles
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rss_collector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/rss_collector.py tests/test_rss_collector.py
git commit -m "feat: add RSS collector with per-feed failure isolation"
```

---

### Task 6: Summarizer/Classifier（Claude API）

**Files:**
- Create: `src/collector/summarizer.py`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Consumes: `models.Article`, `models.CATEGORIES`（Task 1）
- Produces:
  - `summarizer.summarize_and_classify(articles: list[Article], client, batch_size: int = 10, max_retries: int = 3) -> list[Article]`（`client` は `.messages.create(model, max_tokens, messages) -> response` を持つAnthropicクライアント互換オブジェクト。返り値の `Article` は `summary` と `category` が埋まる。失敗した記事は `summary=None`, `category="other"` のまま保持）

- [ ] **Step 1: Write the failing test**

`tests/test_summarizer.py`:
```python
import json

from src.collector.models import Article
from src.collector.summarizer import summarize_and_classify


class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, model, max_tokens, messages):
            response = self._outer._responses[self._outer.calls]
            self._outer.calls += 1
            if isinstance(response, Exception):
                raise response
            return response

    @property
    def messages(self):
        return _FakeClient._Messages(self)


def _article(title="A", url="https://example.com/a"):
    return Article(title=title, url=url, source="search", source_name="test")


def test_summarize_and_classify_fills_summary_and_category():
    payload = json.dumps([
        {"url": "https://example.com/a", "summary": "3行要約テキスト", "category": "seo"},
    ])
    client = _FakeClient([_FakeResponse(payload)])

    result = summarize_and_classify([_article()], client, batch_size=10)

    assert result[0].summary == "3行要約テキスト"
    assert result[0].category == "seo"


def test_summarize_and_classify_retries_then_succeeds():
    payload = json.dumps([
        {"url": "https://example.com/a", "summary": "要約", "category": "ai"},
    ])
    client = _FakeClient([ConnectionError("boom"), _FakeResponse(payload)])

    result = summarize_and_classify([_article()], client, batch_size=10, max_retries=3)

    assert result[0].summary == "要約"
    assert result[0].category == "ai"


def test_summarize_and_classify_falls_back_after_exhausting_retries():
    client = _FakeClient([ConnectionError("boom"), ConnectionError("boom"), ConnectionError("boom")])

    result = summarize_and_classify([_article()], client, batch_size=10, max_retries=3)

    assert result[0].summary is None
    assert result[0].category == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.summarizer'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/summarizer.py`:
```python
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
                max_tokens=2000,
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
        article.category = article.category or "other"

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/summarizer.py tests/test_summarizer.py
git commit -m "feat: add Claude-based summarizer/classifier with retry and fallback"
```

---

### Task 7: Formatter（Slack Block Kit整形）

**Files:**
- Create: `src/collector/formatter.py`
- Test: `tests/test_formatter.py`

**Interfaces:**
- Consumes: `models.Article`, `models.CATEGORIES`（Task 1）
- Produces: `formatter.build_slack_blocks(articles: list[Article], today: str) -> list[dict]`

- [ ] **Step 1: Write the failing test**

`tests/test_formatter.py`:
```python
from src.collector.formatter import build_slack_blocks
from src.collector.models import Article


def _article(title, url, category, summary="要約テキスト"):
    return Article(title=title, url=url, source="search", source_name="t", category=category, summary=summary)


def test_build_slack_blocks_groups_by_category_in_fixed_order():
    articles = [
        _article("広告記事", "https://example.com/ads", "ads"),
        _article("SEO記事", "https://example.com/seo", "seo"),
    ]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    header_texts = [
        b["text"]["text"] for b in blocks
        if b["type"] == "header"
    ]
    assert any("2026-08-20" in t for t in header_texts)

    section_texts = "\n".join(
        b["text"]["text"] for b in blocks if b["type"] == "section"
    )
    seo_index = section_texts.find("SEO記事")
    ads_index = section_texts.find("広告記事")
    assert 0 <= seo_index < ads_index


def test_build_slack_blocks_includes_link_and_summary():
    articles = [_article("記事タイトル", "https://example.com/a", "seo", summary="これは要約です")]

    blocks = build_slack_blocks(articles, today="2026-08-20")

    section_texts = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "<https://example.com/a|記事タイトル>" in section_texts
    assert "これは要約です" in section_texts


def test_build_slack_blocks_empty_articles_returns_header_only():
    blocks = build_slack_blocks([], today="2026-08-20")

    assert any(b["type"] == "header" for b in blocks)
    assert not any(b["type"] == "section" and "http" in b["text"]["text"] for b in blocks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_formatter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.formatter'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/formatter.py`:
```python
from .models import Article

_CATEGORY_LABELS = {
    "seo": "SEO",
    "ai": "AI",
    "ads": "広告",
    "event": "イベント",
    "other": "その他",
}
_CATEGORY_ORDER = ("seo", "ai", "ads", "event", "other")


def build_slack_blocks(articles: list[Article], today: str) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"BtoBマーケティング情報まとめ {today}"},
        }
    ]

    by_category: dict[str, list[Article]] = {c: [] for c in _CATEGORY_ORDER}
    for article in articles:
        by_category.setdefault(article.category or "other", []).append(article)

    for category in _CATEGORY_ORDER:
        items = by_category.get(category, [])
        if not items:
            continue

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{_CATEGORY_LABELS[category]}*"},
        })
        for article in items:
            summary = article.summary or "(要約なし)"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{article.url}|{article.title}>\n{summary}",
                },
            })

    return blocks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_formatter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/formatter.py tests/test_formatter.py
git commit -m "feat: add Slack Block Kit formatter grouped by category"
```

---

### Task 8: Notifier（Slack Incoming Webhook投稿）

**Files:**
- Create: `src/collector/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: なし（`build_slack_blocks` の出力である `list[dict]` を受け取る）
- Produces: `notifier.post_to_slack(blocks: list[dict], webhook_url: str, http_post=requests.post) -> None`（失敗時は例外を再送出する）

- [ ] **Step 1: Write the failing test**

`tests/test_notifier.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.notifier'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/notifier.py`:
```python
import requests


def post_to_slack(blocks: list[dict], webhook_url: str, http_post=requests.post) -> None:
    response = http_post(webhook_url, json={"blocks": blocks}, timeout=10)
    response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_notifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/collector/notifier.py tests/test_notifier.py
git commit -m "feat: add Slack notifier that raises on delivery failure"
```

---

### Task 9: Main Orchestration（dry-run対応パイプライン）

**Files:**
- Create: `src/collector/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes:
  - `config.load_keywords`, `config.load_feeds`（Task 1）
  - `state_store.load_state`, `state_store.save_state`, `state_store.mark_seen`, `state_store.prune_old`（Task 2）
  - `dedup.dedupe_articles`（Task 3）
  - `search_collector.collect_search_articles`（Task 4）
  - `rss_collector.collect_rss_articles`（Task 5）
  - `summarizer.summarize_and_classify`（Task 6）
  - `formatter.build_slack_blocks`（Task 7）
  - `notifier.post_to_slack`（Task 8）
- Produces: `main.run(config_paths: dict, secrets: dict, now_iso: str, dry_run: bool = False) -> list[dict]`（返り値は生成したSlack blocks。テスト・dry-run結果の検証に使う）

`config_paths` は `{"keywords": str, "feeds": str, "state": str}`、`secrets` は `{"google_api_key": str, "google_cse_id": str, "anthropic_client": object, "slack_webhook_url": str}`。

- [ ] **Step 1: Write the failing test**

`tests/test_main.py`:
```python
import json

from src.collector import main as main_module
from src.collector.models import Article


def _setup_configs(tmp_path):
    keywords_path = tmp_path / "keywords.yaml"
    keywords_path.write_text("seo:\n  - test\n", encoding="utf-8")
    feeds_path = tmp_path / "feeds.yaml"
    feeds_path.write_text("[]\n", encoding="utf-8")
    state_path = tmp_path / "seen_articles.json"
    state_path.write_text("{}\n", encoding="utf-8")
    return {
        "keywords": str(keywords_path),
        "feeds": str(feeds_path),
        "state": str(state_path),
    }


def test_run_dry_run_does_not_post_or_save_state(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [Article(title="A", url="https://example.com/a", source="search", source_name="s")],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(title=a.title, url=a.url, source=a.source, source_name=a.source_name, summary="要約", category="seo")
            for a in articles
        ],
    )

    posted = {"called": False}
    monkeypatch.setattr(main_module, "post_to_slack", lambda blocks, url: posted.update(called=True))

    blocks = main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), "slack_webhook_url": "https://hooks.slack.com/x"},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=True,
    )

    assert posted["called"] is False
    assert any("要約" in b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section")

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert state_after == {}


def test_run_live_posts_and_updates_state(tmp_path, monkeypatch):
    config_paths = _setup_configs(tmp_path)

    monkeypatch.setattr(
        main_module,
        "collect_search_articles",
        lambda keywords, api_key, cse_id: [Article(title="A", url="https://example.com/a", source="search", source_name="s")],
    )
    monkeypatch.setattr(main_module, "collect_rss_articles", lambda feeds: [])
    monkeypatch.setattr(
        main_module,
        "summarize_and_classify",
        lambda articles, client: [
            Article(title=a.title, url=a.url, source=a.source, source_name=a.source_name, summary="要約", category="seo")
            for a in articles
        ],
    )

    posted = {"called": False}
    monkeypatch.setattr(main_module, "post_to_slack", lambda blocks, url: posted.update(called=True))

    main_module.run(
        config_paths,
        secrets={"google_api_key": "k", "google_cse_id": "c", "anthropic_client": object(), "slack_webhook_url": "https://hooks.slack.com/x"},
        now_iso="2026-08-20T00:00:00+00:00",
        dry_run=False,
    )

    assert posted["called"] is True

    state_after = json.loads((tmp_path / "seen_articles.json").read_text(encoding="utf-8"))
    assert "https://example.com/a" in state_after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.collector.main'`

- [ ] **Step 3: Write minimal implementation**

`src/collector/main.py`:
```python
import argparse
import logging
import os

from .config import load_feeds, load_keywords
from .dedup import dedupe_articles
from .formatter import build_slack_blocks
from .notifier import post_to_slack
from .rss_collector import collect_rss_articles
from .search_collector import collect_search_articles
from .state_store import load_state, mark_seen, prune_old, save_state
from .summarizer import summarize_and_classify

logger = logging.getLogger(__name__)


def run(config_paths: dict, secrets: dict, now_iso: str, dry_run: bool = False) -> list[dict]:
    keywords = load_keywords(config_paths["keywords"])
    feeds = load_feeds(config_paths["feeds"])
    state = load_state(config_paths["state"])

    search_articles = collect_search_articles(keywords, secrets["google_api_key"], secrets["google_cse_id"])
    rss_articles = collect_rss_articles(feeds)
    articles = dedupe_articles(search_articles + rss_articles, state)
    articles = summarize_and_classify(articles, secrets["anthropic_client"])

    today = now_iso[:10]
    blocks = build_slack_blocks(articles, today=today)

    if dry_run:
        return blocks

    post_to_slack(blocks, secrets["slack_webhook_url"])

    for article in articles:
        mark_seen(state, article.url, now_iso)
    state = prune_old(state, now=now_iso, days=30)
    save_state(config_paths["state"], state)

    return blocks


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import anthropic
    from datetime import datetime, timezone

    config_paths = {
        "keywords": "config/keywords.yaml",
        "feeds": "config/feeds.yaml",
        "state": "state/seen_articles.json",
    }
    secrets = {
        "google_api_key": os.environ["GOOGLE_API_KEY"],
        "google_cse_id": os.environ["GOOGLE_CSE_ID"],
        "anthropic_client": anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
        "slack_webhook_url": os.environ["SLACK_WEBHOOK_URL"],
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    run(config_paths, secrets, now_iso, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: すべてのテストがPASS

- [ ] **Step 6: Commit**

```bash
git add src/collector/main.py tests/test_main.py
git commit -m "feat: wire pipeline stages into main entrypoint with dry-run support"
```

---

### Task 10: 依存関係定義・GitHub Actions ワークフロー

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.github/workflows/daily_digest.yml`

**Interfaces:**
- Consumes: `src/collector/main.py` の `main()` エントリポイント（Task 9）
- Produces: CIから `python -m src.collector.main` を実行する日次ワークフロー

- [ ] **Step 1: Create requirements.txt**

`requirements.txt`:
```
requests>=2.31
feedparser>=6.0
PyYAML>=6.0
anthropic>=0.40
pytest>=8.0
```

- [ ] **Step 2: Create .env.example**

`.env.example`:
```
GOOGLE_API_KEY=
GOOGLE_CSE_ID=
ANTHROPIC_API_KEY=
SLACK_WEBHOOK_URL=
```

- [ ] **Step 3: Create GitHub Actions workflow**

`.github/workflows/daily_digest.yml`:
```yaml
name: Daily Digest

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run digest
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
          GOOGLE_CSE_ID: ${{ secrets.GOOGLE_CSE_ID }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: python -m src.collector.main

      - name: Commit updated state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state/seen_articles.json
          git diff --staged --quiet || git commit -m "chore: update seen articles state"
          git push
```

- [ ] **Step 4: Verify workflow YAML is well-formed**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_digest.yml', encoding='utf-8'))"`
Expected: エラーなく終了（構文チェックのみ、実際の起動はGitHub Actions上で確認）

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example .github/workflows/daily_digest.yml
git commit -m "chore: add dependencies and daily GitHub Actions workflow"
```

---

### Task 11: Inoreader OPML → feeds.yaml 変換スクリプト

**Files:**
- Create: `scripts/opml_to_feeds.py`
- Test: `tests/test_opml_to_feeds.py`

**Interfaces:**
- Consumes: なし（独立CLIスクリプト）
- Produces: `opml_to_feeds.parse_opml(opml_text: str) -> list[dict]`（各要素 `{"name": str, "url": str, "category_hint": str | None}`。OPMLのフォルダ（outlineの入れ子）名を `category_hint` の元値として使う）

- [ ] **Step 1: Write the failing test**

`tests/test_opml_to_feeds.py`:
```python
import textwrap

from scripts.opml_to_feeds import parse_opml


def test_parse_opml_extracts_feeds_with_folder_as_category_hint():
    opml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <opml version="1.0">
          <body>
            <outline text="seo">
              <outline text="Example Blog" type="rss" xmlUrl="https://example.com/feed.xml"/>
            </outline>
            <outline text="Uncategorized Feed" type="rss" xmlUrl="https://example.org/rss"/>
          </body>
        </opml>
        """)

    result = parse_opml(opml)

    assert {"name": "Example Blog", "url": "https://example.com/feed.xml", "category_hint": "seo"} in result
    assert {"name": "Uncategorized Feed", "url": "https://example.org/rss", "category_hint": None} in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_opml_to_feeds.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.opml_to_feeds'`

- [ ] **Step 3: Write minimal implementation**

`scripts/opml_to_feeds.py`:
```python
import sys
import xml.etree.ElementTree as ET

import yaml


def parse_opml(opml_text: str) -> list[dict]:
    root = ET.fromstring(opml_text)
    body = root.find("body")
    feeds: list[dict] = []

    def _walk(outline, category_hint):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feeds.append({
                "name": outline.get("text", xml_url),
                "url": xml_url,
                "category_hint": category_hint,
            })
            return

        folder_name = outline.get("text")
        for child in outline.findall("outline"):
            _walk(child, folder_name)

    for outline in body.findall("outline"):
        _walk(outline, None)

    return feeds


def main() -> None:
    opml_path, out_path = sys.argv[1], sys.argv[2]
    with open(opml_path, encoding="utf-8") as f:
        feeds = parse_opml(f.read())
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(feeds, f, allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    main()
```

`scripts/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_opml_to_feeds.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/opml_to_feeds.py tests/test_opml_to_feeds.py
git commit -m "feat: add OPML to feeds.yaml conversion script for Inoreader exports"
```

**利用手順（ユーザー向け、コード外の作業）:**
1. Inoreaderの Preferences → Import/Export → Export as OPML でファイルをダウンロード
2. `python scripts/opml_to_feeds.py path/to/export.opml config/feeds.yaml` を実行
3. 生成された `config/feeds.yaml` の `category_hint` を必要に応じて `seo`/`ai`/`ads`/`event`/`null` に手直しする

---

## Self-Review Notes

- **Spec coverage:** 7章「テスト方針」の dry-run モードは Task 9 の `dry_run` フラグで実装。5章の部分失敗はTask 4/5でtry-except+ログでカバー。6章のClaude API失敗時フォールバックはTask 6の `max_retries` 到達時に `summary=None, category="other"` を保持する挙動で実装。cron時刻・Secrets名・カテゴリ一覧はGlobal Constraintsに転記済み。
- **Placeholder scan:** 各タスクのコードは実装済みで「TODO」等のプレースホルダーなし。
- **Type consistency:** `Article` のフィールド名・`collect_search_articles`/`collect_rss_articles`/`summarize_and_classify`/`build_slack_blocks`/`post_to_slack` の関数名・引数は全タスクで一致するよう統一済み。
