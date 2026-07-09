# バックエンド（リファレンス実装）

AIエージェント・サブスクの裏側。設計書（[workflow系のbackend設計]）の4項目を、実際に動かすための**リファレンス実装**です。

> ⚠️ **これはリファレンス（雛形）です。** サーバー・APIキー・デプロイが必要で、静的サイト（GitHub Pages のプロトタイプ）とは別物です。このリポジトリ上では**未実行**。`flowgen.py` と `score.py` の中核（純Python部分）のみローカル実行で確認済み。API・パイプラインは Claude/外部API 連携部を実装のうえデプロイして動かします。

## 構成

| ファイル | 対応する設計項目 | 内容 | 実行に必要なもの |
|---|---|---|---|
| `api/main.py` | ① サービス側API | FastAPI。`POST /v1/agents/{id}/run`（単体）、`POST /v1/workflows/{id}/run`（連携） | `ANTHROPIC_API_KEY`、`fastapi uvicorn anthropic` |
| `pipeline/ingest.py` | ② 取り込みパイプライン | 記事/PDF/PR TIMES 取得 → Claude要約 → **重複しない**もののみ保存 | `ANTHROPIC_API_KEY`、取得部の実装（Tavily/OCR/スクレイパ） |
| `obsidian/flowgen.py` | ③ Obsidian知識構造化 | ワークフロー定義 → **Mermaidフローチャート** → Vaultノート生成 | 標準ライブラリのみ |
| `scoring/score.py` | ④ スコアリング学習ループ | 表示/クリック/使用/DL を集計 → スコア → 改善対象特定 | 中核は標準ライブラリ、改善提案のみ `anthropic` |

## セットアップ

```bash
pip install fastapi uvicorn "anthropic>=0.40"
export ANTHROPIC_API_KEY=sk-ant-...

# ① API を起動
uvicorn backend.api.main:app --reload
#   例: curl -X POST localhost:8000/v1/agents/t1/run -H "x-api-key: demo" \
#         -H "content-type: application/json" -d '{"input":"IT業界の新規リード"}'

# ③ フローチャート生成（依存なしで動く）
python backend/obsidian/flowgen.py

# ④ スコアリング（依存なしで動く）
python backend/scoring/score.py
```

## 設計上のポイント

- **原価管理**: 定型エージェントは `claude-haiku-4-5`、企画/レビューは `claude-opus-4-8` に出し分け。1実行 $0.05〜0.30 で月額に十分収まる。
- **プラットフォーム内完結**: ユーザーは自分のClaude契約なしで、サービス側APIで実行して成果物を得る。認証は APIキー、本番は**電話番号認証**＋プラン判定を前段に。
- **重複しない**: パイプラインが既出コンテンツと指紋照合し、過去と重複しない項目だけを配信。
- **人間テスト必須**: スコアリングは自動でも、最終品質は**人間（直氏・小林氏）**が担保する（自動化困難）。

## 本番化の次の一手（段階導入）

1. `api/main.py` の `AGENTS`/`WORKFLOWS` を辞書DBから読み込む。認証・課金判定を前段に。
2. `pipeline/ingest.py` の取得部（Tavily/OCR/スクレイパ）を実装し、時事ニュースを実データ供給。
3. `scoring/score.py` をイベントDBに接続し、並び順・新着選定・改善対象へフィードバック。
