# YouTube Studio へ「非公開（下書き）」自動アップロードを繋ぐ手順

この環境（Antigravity）自体には YouTube 用の公式プラグインが未搭載のため、現在は生成した動画（`.mp4`）を **Google ドライブへ自動保存** する運用になっています。

もし手元の PC から **「YouTube Studio の非公開下書きへワンコマンドで自動アップロード → あとは公開ボタンを押すだけ」** にしたい場合は、以下の初回設定（約5分）を行うと `scripts/upload_youtube.py` がそのまま使えます。

## 初回セットアップ（1回のみ）
1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成し、**YouTube Data API v3** を有効化する。
2. 「OAuth 同意画面」でテストユーザーに自分の Google アカウントを追加する。
3. 「認証情報」→「OAuth クライアント ID」→ アプリケーションの種類「デスクトップ アプリ」を作成し、JSON をダウンロードする。
4. ダウンロードしたファイルを `scripts/client_secret.json` として保存する。
5. 必要なライブラリをインストールして実行する：
   ```bash
   pip install google-api-python-client google-auth-oauthlib
   python3 scripts/upload_youtube.py \
     --video shorts/day01/output/day01_short.mp4 \
     --title "99%が3回目でミスる鬼ゲー作ったｗ【無料ブラウザゲーム】 #Shorts" \
     --description-file notes/day01/youtube_metadata.txt
   ```
6. 初回だけブラウザが開くので YouTube チャンネルのあるアカウントで許可すると、`private`（非公開）状態で YouTube Studio にアップロードされます。
7. あなたは **YouTube Studio を開いて中身を確認し、「公開」を押すだけ** です。
