# note_create_use — 1日1アプリ＋ショート動画＋note記事ラボ

毎日1本、遊べるブラウザゲームまたは便利なWebツールを作成し、以下をワンセットで生成するリポジトリです。

1. **Webゲーム／ツール本体**（`games/`）
2. **YouTube Shorts / TikTok / Reels 用 縦型ショート動画（1080×1920 MP4）**（`shorts/`）
3. **Zenn / Qiita 完全自動投稿用記事・画像**（`articles/`・`public/`・`images/`）
4. **note.com 投稿用記事原稿・見出し画像・1クリックコピペ画面**（`notes/`）

## 制作ログ（重複防止カタログ）
- 一覧表: [CATALOG.md](CATALOG.md) / 機械可読データ: [CATALOG.json](CATALOG.json)

## 自動投稿セットアップ
- **Zenn / Qiita 完全自動投稿（PRマージで即公開）**: [scripts/ZENN_QIITA_SETUP.md](scripts/ZENN_QIITA_SETUP.md)
- **YouTube Studio 自動下書きアップロード**: [scripts/YOUTUBE_SETUP.md](scripts/YOUTUBE_SETUP.md) / [scripts/YOUTUBE_MOBILE_SETUP.md](scripts/YOUTUBE_MOBILE_SETUP.md)

## Day 01: JUST SLASH 99（神速0.01秒ジャスト斬り）
- ゲーム本体: [games/day01-just-slash/index.html](games/day01-just-slash/index.html)
- Zenn 記事（自動同期）: [articles/kam2525-day01-just-slash.md](articles/kam2525-day01-just-slash.md)
- Qiita 記事（自動投稿）: [public/kam2525-day01-just-slash.md](public/kam2525-day01-just-slash.md)
- 1クリックコピペヘルパー（note / X用）: [notes/day01/copy_helper.html](notes/day01/copy_helper.html)
- note 記事原稿: [notes/day01/note_draft.md](notes/day01/note_draft.md)
- ショート動画生成スクリプト: [shorts/day01/generate_shorts.py](shorts/day01/generate_shorts.py)