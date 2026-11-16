# Zenn ＆ Qiita 完全自動投稿セットアップ（スマホだけでOK）

このリポジトリは **PR をマージして `main` に反映するだけ** で、以下が自動公開される構成になっています。

- **Zenn**：`articles/*.md` ＋ `images/*` を GitHub 連携で自動同期
- **Qiita**：`public/*.md` を公式 GitHub Action（`increments/qiita-cli/actions/publish@v1`）で自動投稿・更新

初回だけ以下の連携設定を行ってください（各1分）。

---

## 1. Zenn の GitHub 連携（トークン不要・30秒）

1. スマホで https://zenn.dev にログイン
2. 右上のアイコン → **「GitHubからのデプロイ」**（`https://zenn.dev/dashboard/deploys`）を開く
3. **「リポジトリを連携する」** をタップ（初回のみ GitHub App `Zenn Connect` のインストール画面が開くので `kam2525-hub/note_create_use` を許可）
4. 対象リポジトリに `kam2525-hub/note_create_use`、ブランチに `main` を選択して連携完了

> **ヒント**：連携した直後に過去の `articles/` が自動で同期・公開されます（`published: true` のもの）。

---

## 2. Qiita のトークン登録（1分）

1. スマホで https://qiita.com にログイン
2. **設定 → アプリケーション → 個人用アクセストークン**（`https://qiita.com/settings/tokens/new`）を開く
3. 以下を入力して **「発行する」**：
   - Token description：`note_create_use`
   - Scopes：**`read_qiita`** と **`write_qiita`** にチェック
4. 表示されたトークンをコピー（※再表示できないためその場でコピー）
5. GitHub リポジトリの **Settings → Secrets and variables → Actions** を開く
   - `https://github.com/kam2525-hub/note_create_use/settings/secrets/actions`
6. **「New repository secret」** をタップ：
   - Name：`QIITA_TOKEN`
   - Secret：コピーしたトークンを貼り付けて保存

### 初回の手動実行（PRマージ後に `QIITA_TOKEN` を登録した場合）
GitHub リポジトリの **Actions** タブ → **「Publish Qiita Articles」** → **「Run workflow」** を押すと、`public/` 内の記事が即座に Qiita に投稿されます（次回以降は PR マージ時に全自動実行）。

---

## 公開前レビューについて

- **公開前確認**：PR がオープンの間は **Zenn も Qiita も公開されません**。GitHub PR の画面で記事プレビューを確認できます。
- **完全自動公開**：GitHub で **「Merge pull request」** を押した瞬間に Zenn・Qiita・GitHub Pages が自動で公開されます。
- **限定共有（下書きプレビュー）にしたい日**：Qiita 記事の frontmatter を `private: true` にしておけば、URLを知っている自分だけが見られる限定共有状態で自動アップロードされます。
