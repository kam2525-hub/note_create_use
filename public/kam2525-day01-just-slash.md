---
title: 99%が3回目でミスる!? 0.01秒タイミングゲーム『JUST SLASH 99』をHTML1枚＋Web Audio APIで作った話
tags:
  - JavaScript
  - HTML5
  - WebAudioAPI
  - ゲーム制作
  - 個人開発
private: false
updated_at: ''
id: null
organization_url_name: null
slide: false
ignorePublish: false
---

![JUST SLASH 99](https://kam2525-hub.github.io/note_create_use/images/day01-just-slash.png)

**「あと1ミリだったのに…！」**

そう言いながら、気づいたら10回連続でリトライしてしまう。  
外部ライブラリ・ビルド手順ゼロ・**HTML 1ファイル完結**の脳汁特化型タイミングゲーム『**JUST SLASH 99**』を作りました！

GitHub Pages 上にホストしているので、スマホ・PCどちらからでもインストール不要でそのまま遊べます。

**▶ ブラウザで今すぐ遊ぶ**  
https://kam2525-hub.github.io/note_create_use/games/day01-just-slash/

（ソースコード全体は [kam2525-hub/note_create_use](https://github.com/kam2525-hub/note_create_use) で公開中）

---

## ルールは「2つだけ」

1. 左右に爆速で走る光のバーが、**中心の GOLD ゾーン** に重なった瞬間にタップ（PCは `Space` キー）
2. 5連続成功で **「FEVER TIME」** に突入し、スコア2倍＆BGMがギアアップ

ただし、ときどき **「赤い TRAP ゾーン」** が出現します。  
赤いときにうっかり押してしまうと即ミス！見送ってスルーできればボーナス得点になります。

---

## 技術的な実装ポイント（HTML 1ファイル × バニラ JS）

短いプレイ時間でも中毒性が出るよう、3つのゲームフィール演出を依存ゼロで実装しています。

### 1. 音声ファイルゼロのシンセBGM＆音階ヒット音（Web Audio API）
`.mp3` や `.wav` を読み込まず、`Web Audio API`（`OscillatorNode` / `GainNode`）だけで BGM・斬撃 SE をリアルタイム合成しています。コンボが増えるごとにヒット音の音階が駆け上がるため、視覚だけでなく耳からも快感が返ってきます。

### 2. 0.03秒のヒットストップ ＋ 画面シェイク（Canvas 2D）
ど真ん中の `GOD` 判定が決まった瞬間だけゲーム時間の更新を0.03秒止め（ヒットストップ）、画面シェイク・斬撃エフェクト・パーティクルを重ねて手応えを強調しています。

### 3. 0.1秒でリスタートできるストレスゼロ設計
ゲームオーバー画面からボタン1回（または `Space` キー）で即座に次のプレイに入れるため、「あと1回だけ…」が止まりません。

---

## スコアランク目安

- **2,200点以上**：Aランク（超反応スナイパー）
- **4,500点以上**：Sランク（脳汁ドバドバの覇者）
- **8,000点以上**：S++ランク（人間卒業・0.01秒の神）

まずは **Sランク（4,500点）** を目指してみてください！
