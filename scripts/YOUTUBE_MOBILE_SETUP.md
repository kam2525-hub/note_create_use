# スマホだけで YouTube Studio 自動下書き連携を作る手順（PC不要・約5〜10分）

手元に PC がなくても、スマホのブラウザだけで **Google 公式 OAuth 2.0 Playground** と **GitHub Secrets** を使って連携できます。  
一度連携すれば、以降は **スマホから GitHub の「Run workflow」ボタンを押すだけで YouTube Studio に「非公開（下書き）」で動画が上がります**。

---

## ステップ 1：Google Cloud で YouTube API を有効化（スマホブラウザ）
1. スマホのブラウザで [Google Cloud Console](https://console.cloud.google.com/) を開く（PC版サイト表示にすると見やすいです）。
2. 上部のプロジェクト選択から「新しいプロジェクト」を作成（例：`note-shorts-bot`）。
3. 左メニュー「API とサービス」→「ライブラリ」から **`YouTube Data API v3`** を検索して **有効にする**。
4. 「OAuth 同意画面」を設定：
   - User Type：**外部**
   - アプリ名・メールアドレスを入力して保存
   - **テストユーザー** に、YouTube チャンネルを持っている自分の Google メールアドレスを必ず追加する
5. 「認証情報」→「認証情報を作成」→「**OAuth クライアント ID**」を選択：
   - アプリケーションの種類：**ウェブ アプリケーション**
   - 承認済みのリダイレクト URI に以下をそのまま追加：
     `https://developers.google.com/oauthplayground`
   - 作成後に表示される **クライアント ID** と **クライアント シークレット** をメモする。

---

## ステップ 2：OAuth 2.0 Playground で Refresh Token を取得（スマホブラウザ）
1. [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/) を開く。
2. 右上の **歯車アイコン（⚙）** をタップし、**`Use your own OAuth credentials`** にチェックを入れて、ステップ1の **OAuth Client ID** と **OAuth Client secret** を貼り付ける。
3. 左側の「Step 1 Select & authorize APIs」の入力欄に以下を貼り付けて **Authorize APIs** をタップ：
   `https://www.googleapis.com/auth/youtube.upload`
4. Google ログイン＆アクセス許可画面が出たら自分のチャンネルのアカウントで許可する（「このアプリは Google で確認されていません」が出たら「詳細」→「安全ではないページに移動」をタップ。自分で作ったテスト用アプリのため問題ありません）。
5. 「Step 2 Exchange authorization code for tokens」に戻ったら **Exchange authorization code for tokens** をタップ。
6. 表示された **`Refresh token`** をコピーする。

---

## ステップ 3：GitHub Secrets に登録（スマホの GitHub アプリ / ブラウザ）
1. GitHub で `kam2525-hub/note_create_use` を開く。
2. **`Settings`** → **`Secrets and variables`** → **`Actions`** → **`New repository secret`** から以下3つを登録：
   - Name: `YOUTUBE_CLIENT_ID` ／ Secret: ステップ1のクライアントID
   - Name: `YOUTUBE_CLIENT_SECRET` ／ Secret: ステップ1のクライアントシークレット
   - Name: `YOUTUBE_REFRESH_TOKEN` ／ Secret: ステップ2の Refresh token

---

## ステップ 4：スマホから「YouTube 下書き自動アップ」を実行！
1. GitHub リポジトリの **`Actions`** タブを開く。
2. **`Generate Short & Upload Private Draft to YouTube`** を選択。
3. **`Run workflow`** をタップして Day 番号（例：`01`）を選んで実行！
4. 数分であなたの **YouTube Studio アプリに「非公開」動画として自動追加** されるので、確認して「公開」を押すだけです。
