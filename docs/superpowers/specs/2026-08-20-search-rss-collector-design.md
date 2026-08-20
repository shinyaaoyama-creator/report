# 情報収集アプリ：検索＋RSS収集 設計スペック

- Status: Approved (design)
- Date: 2026-08-20

## 1. 目的

BtoBマーケティング（SEO・AI・広告・イベント施策）に関する情報を、Web検索とRSSフィードから収集し、AIで要約・カテゴリ分類・重複除去した上で、毎朝Slackに配信する。

## 2. 全体アーキテクチャ

- **実行基盤**: GitHub Actions（cron、日次1回）
  - PCの起動状態に依存しない、追加コストが実質かからない、GitHub Secretsでキー管理できる、という理由で選定。
- **言語**: Python
- **状態管理**: リポジトリ内のJSONファイル（既配信記事のリスト）。実行後にActionsが自動コミットして更新。外部DBは使わない。
- **シークレット管理**: GitHub Secrets

```
[GitHub Actions cron 日次 JST 9:00]
   ↓
[収集: Google CSE検索 + RSS取得(Inoreader OPML由来の固定リスト)]
   ↓
[重複除去(過去の既配信リスト・検索/RSS間の重複)]
   ↓
[Claude APIで要約+カテゴリ分類(SEO/AI/広告/イベント)]
   ↓
[Slack Incoming Webhookへ整形して投稿]
   ↓
[既配信リストを更新してコミット]
```

## 3. コンポーネント構成

### a. Collector（収集）
- `search_collector`: `config/keywords.yaml` に定義したキーワード（カテゴリごとにグルーピング、合計数十語、運用中に追加・見直し）を、Google Custom Search JSON APIに1キーワード=1クエリで投げる。無料枠100クエリ/日に収まる規模。
- `rss_collector`: Inoreaderの無料/Basicプランでは開発者API利用不可（Proプラン以上が必須）のため、Inoreaderの「Export as OPML」機能で購読フィード一覧を書き出し、`config/feeds.yaml` に変換して固定リストとして保持。feedparserで直接RSS/Atomを巡回する。

### b. Deduplicator（重複除去）
- 記事URLの正規化（トラッキングクエリパラメータ除去等）とタイトル類似度により、以下2種の重複を除去する。
  1. 過去配信済み（state store）との重複
  2. 同日内で検索とRSSが同じ記事を拾った場合のクロスソース重複

### c. Summarizer/Classifier（Claude API）
- 重複除去後の記事ごとに、Claude API（Haiku等の軽量モデル）で「3行要約＋カテゴリ（SEO/AI/広告/イベント/その他）」をJSON形式で生成。
- API呼び出し回数を抑えるため、複数記事をまとめて1回のプロンプトに渡すバッチ処理とする。

### d. Formatter/Notifier（配信）
- カテゴリごとに見出しを分け、各記事「タイトル（リンク）＋要約」をSlack Block Kit形式で整形し、Incoming Webhookへ投稿。

### e. State Store
- `state/seen_articles.json`：記事の正規化URL（またはハッシュ）と配信日時を記録。30日超の古いエントリは定期的に間引く。

## 4. 設定・実行スケジュール

- `config/keywords.yaml`: カテゴリ（seo/ai/ads/event）ごとのキーワードリスト。YAML形式で運用中の追加・削除を容易にする。
- `config/feeds.yaml`: InoreaderのOPMLエクスポートを変換して生成。以後は直接追記も可能。
- cronスケジュール: `0 0 * * *`（UTC 0:00 = JST 9:00）
- `workflow_dispatch` を有効化し、手動実行でいつでも動作確認できるようにする。
- Secrets（GitHub Secretsに登録）:
  - `GOOGLE_API_KEY` / `GOOGLE_CSE_ID`
  - `ANTHROPIC_API_KEY`
  - `SLACK_WEBHOOK_URL`

## 5. エラー処理

- 収集の部分失敗（個々のフィード取得・キーワード検索の失敗）はスキップしてログに記録し、全体の処理は継続する。
- AI呼び出し失敗はリトライ（指数バックオフ、最大2〜3回）。それでも失敗した記事はタイトル＋リンクのみで配信に含める。
- Slack投稿失敗はGitHub Actionsのジョブを失敗扱いにし、Actionsの実行履歴で気づける状態にする（専用の追加通知は当面設けない）。

## 6. テスト方針

- 各コレクター・重複除去・フォーマッターは外部APIをモックしたユニットテストを用意する。
- dry-runモード（Slack投稿を行わず、生成結果を標準出力/ファイルに出力するだけのモード）を用意し、本番配信前に確認できるようにする。

## 7. スコープ外（将来検討）

- メール配信への対応拡張
- Inoreader ProへのアップグレードによるAPI連携（フィード管理の一元化）
- キーワード・フィードの自動提案・自動追加

## 8. 未解決事項

- なし（本スペック内の設計項目はすべて承認済み）
