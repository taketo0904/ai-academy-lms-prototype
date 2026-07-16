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
4. 環境変数 **`ANTHROPIC_API_KEY`** に、用意したキーを貼る → **Apply / Deploy**
5. 数分でデプロイ完了。**URL**（例: `https://task-agents-api.onrender.com`）をコピー
6. 疎通確認: ブラウザで `https://<そのURL>/healthz` を開き `{"ok": true, ...}` が出ればOK

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
