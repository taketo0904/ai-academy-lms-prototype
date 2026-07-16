# デプロイ手順 — 「この画面まで」持っていく

プロトタイプ（フロント）は**API接続対応済み**です。以下をやると、設定にURLを貼るだけで
「使う」「ワークフロー実行」が**本物のClaude**で動きます。所要 約10分。

---

## 用意するもの（中川さん）
1. **Anthropic APIキー** … <https://console.anthropic.com> → API Keys → Create Key（`sk-ant-...`）
2. GitHub アカウント（このリポジトリ。デプロイ連携に使う）

---

## 手順A: Render で1クリックデプロイ（推奨・無料枠あり）

1. <https://render.com> にサインイン（GitHubでログイン）
2. **New → Blueprint** を選択
3. このリポジトリ `taketo0904/ai-academy-lms-prototype` を接続 → ルートの **`render.yaml` が自動検出**される
4. `render.yaml` には **Webサービス**（`task-agents-api`）と、毎日ニュースを自動収集する**Cronジョブ**（`task-agents-news-cron`）の2つが定義されている。両方に以下を入力:
   - **`ANTHROPIC_API_KEY`**（両サービス共通・同じキー）
   - **`CRON_KEY`**（任意の文字列。両サービスで**同じ値**にする。ニュース投稿の認証に使う）
   → **Apply / Deploy**
5. 数分でデプロイ完了。**URL**（例: `https://task-agents-api.onrender.com`）をコピー
6. 疎通確認: ブラウザで `https://<そのURL>/healthz` を開き `{"ok": true, ...}` が出ればOK
7. ニュースは毎日 日本時間07:00に自動収集されます（Cronジョブが `/v1/news/ingest` へ投稿）。初回だけ手動で試したい場合は、Renderの `task-agents-news-cron` 画面で **Trigger Run** を押すと即実行されます。
8. **課金メモ**: RenderのCron Jobには無料プランがなく、`plan: starter`（実行時間課金）を使用。1日1回・数十秒の実行なので実質月数十円程度の見込み（Webサービス本体は引き続き無料枠）。

## 手順B: プロダクトに繋ぐ
1. 公開中のプロトタイプを開く → **設定（⚙）** → **「APIのURL」** に上のURLを貼る → **保存**
2. 未整備でないエージェントを開いて **「使う」** → 入力を入れて実行 → **本物の成果物**が返る
3. 連携ワークフローを開いて **「ワークフローを実行」** → 各ステップが本物のClaudeで連鎖

これで「実働」状態です。

---

## 任意（本番で推奨）
- **CORSを絞る**: Render の環境変数 `ALLOW_ORIGINS` を `https://taketo0904.github.io` に変更（既定は `*`）
- **APIを保護**: `API_ACCESS_KEY` を設定 → プロダクトの設定「APIキー」に同じ値を入れる（未設定なら誰でも叩けます）
- Renderの無料枠はスリープします。常時起動は有料プラン or Railway/Fly.io等へ

## 他のホスティング（Railway / Fly.io 等）
- ルートディレクトリを **`backend`** に設定 → `requirements.txt` と `Procfile` を自動検出
- 環境変数 `ANTHROPIC_API_KEY` を設定 → デプロイ

---

## 補足
- 実装は `backend/api/`（`main.py` = API、`agents.py` = 30エージェント＋ワークフロー定義）。
- 承認公開でユーザーが増やしたエージェント（`p...`）は、本番ではDB保存＋API側の動的読込が必要（現状はフロント内のみ）。まずは定義済み30体＋ワークフローが本物で動きます。
- ニュース自動収集は `backend/pipeline/`（`ingest.py` = RSS取得＋Claude要約＋重複除去、`cron_ingest.py` = 毎日実行してAPIへ投稿）。現状はAPI側でインメモリ保存のため、無料インスタンスのスリープ復帰時にリセットされる（次回のcronで再度たまる）。長期保存が要る場合はDB化が必要。
