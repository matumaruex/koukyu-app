---
description: 公休表アプリ（koukyu-app）を編集してGitHubにプッシュする手順
---

# 公休表アプリの変更ワークフロー

このワークフローは、公休表アプリ（介護施設向けシフト管理）の変更時に使います。
変更後は必ずGitHubにプッシュして、Vercelで自動デプロイされるようにします。

## プロジェクト情報

- **フォルダ**: `C:\Users\ureim\.gemini\antigravity\scratch\koukyu-app`
- **GitHub**: `https://github.com/matumaruex/koukyu-app.git`
- **ホスティング**: Vercel（GitHubのmainブランチを自動デプロイ）
- **用途**: お母さんの介護施設のシフト表作成アプリ
- **技術**: HTML + CSS + JavaScript（フレームワークなし）

## ファイル構成

- `index.html` - 画面の構造（HTML）
- `style.css` - 見た目のデザイン
- `app.js` - メインの動作（スタッフ管理、シフト表表示など）
- `scheduler.js` - シフトの自動生成アルゴリズム
- `print.css` - 印刷用のスタイル

## 手順

1. ユーザーの要望を聞いて、対象ファイルを編集する

// turbo
2. 変更したファイルをGitのステージングに追加する
```
git add -A
```
実行場所: `C:\Users\ureim\.gemini\antigravity\scratch\koukyu-app`

3. 変更内容をコミット（記録）する
```
git commit -m "変更内容の要約を日本語で書く"
```
実行場所: `C:\Users\ureim\.gemini\antigravity\scratch\koukyu-app`

4. GitHubにプッシュ（アップロード）する
```
git push origin main
```
実行場所: `C:\Users\ureim\.gemini\antigravity\scratch\koukyu-app`

5. ユーザーに「プッシュ完了、Vercelで数分以内に反映される」と伝える

## 注意事項

- コード内のコメントは日本語で書くこと
- スタッフデータはブラウザのlocalStorageに保存されるため、コード変更でデータは消えない
- 古いデータ形式（canNightShiftなど）は `migrateStaffData()` で自動変換される
- PowerShellでは `&&` が使えないので、コマンドは1つずつ実行すること
