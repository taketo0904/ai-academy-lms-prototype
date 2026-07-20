# データ基盤（アカウント化）— セットアップ手順

`schema.sql` は、今はブラウザのlocalStorageだけにある状態（成果物・マイライブラリ・承認キュー・
利用回数・プラン）を、**アカウント単位でクラウドに保存する**ためのテーブル定義です。
あわせて、利用者が自分のGitHub/Notion/Google Driveなどを接続できる `connected_accounts`
テーブルも含まれています（Yoomのような「接続」画面の土台）。

現状: **スキーマ設計のみ完了。フロント／バックエンドへの接続はまだ未実装**です
（Supabaseの実プロジェクトがないと接続コードの動作確認ができないため）。

---

## 用意するもの（中川さん）

1. **Supabaseアカウント** … <https://supabase.com> にサインアップ（無料枠あり）
2. **新規プロジェクト作成** → プロジェクト名は何でもOK（例: `task-agents`）
3. 作成後、**SQL Editor** を開き `backend/db/schema.sql` の中身を貼り付けて実行
4. **Settings → API** から以下の2つをコピーしてこちらに共有してください
   - `Project URL`（例: `https://xxxxx.supabase.co`）
   - `anon public` キー（フロントから使う公開キー。secretキーではない方）

---

## なぜSupabaseか

- 認証（メール/パスワードログイン）とPostgres DBが最初からセットで使え、自前でログイン機能を作る必要がない
- 「自分のデータは自分にしか見えない／組織のデータは組織のメンバーにしか見えない」という権限制御
  （Row Level Security）を`schema.sql`に含めてある
- 無料枠で今の規模には十分

## テーブル一覧（今回追加分）

- `library_notes` / `library_conversations` / `library_outputs` … マイライブラリ（本人専用）
- `connected_accounts` … 利用者が接続したGitHub/Notion/Google Driveのトークン（本人専用）

## この後こちらでやること（URLとキーをもらってから）

1. `taskdict.html` にSupabaseクライアントを組み込み、ログイン画面を追加
2. 今localStorageにある「マイライブラリ」「マイエージェント」「承認キュー」「利用回数」「プラン」をDB読み書きに置き換え
3. GitHub/Notion/Google Driveの「接続」画面を追加（OAuthの往復をバックエンドで受ける）
4. 3人チーム分の組織を1つ作成し、動作確認

## 接続機能（Yoom型）に追加で必要なもの

`connected_accounts` テーブルにトークンが入るには、サービスごとに **OAuthアプリの登録** が要ります。
これは中川さんご自身の作業です（私が代わりに作ることはできません）。

| サービス | 登録場所 | 必要なもの |
|---|---|---|
| GitHub | GitHub → Settings → Developer settings → OAuth Apps | Client ID・Client Secret・Callback URL |
| Notion | notion.so/my-integrations（Public integration） | Client ID・Client Secret・Redirect URI |
| Google (Drive/Sheets) | Google Cloud Console → OAuth同意画面 + 認証情報 | Client ID・Client Secret・承認済みリダイレクトURI |

Callback/Redirect URLはいずれも `https://task-agents-api.onrender.com/oauth/<service>/callback` の形になります
（バックエンド実装時に確定させます）。Supabaseのプロジェクトができ次第、まずログイン機能から着手し、
接続機能はその後に1サービスずつ追加していきます。

## 補足

- Anthropicの課金上限は組織（ワークスペース）単位でしかAPIから設定できず、顧客ごとのAPIキー自動発行もできないため、Anthropicキーは今まで通りバックエンド共有の1本のまま。利用回数・上限管理はこのSupabase DB側（`usage_records`）で行う設計にしてある。
- `connected_accounts` は現状トークンを平文で保存する設計。RLSで本人以外からは見えないが、将来的にはSupabase Vault（暗号化）への移行を検討する。
