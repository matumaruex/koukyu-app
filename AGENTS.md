# AI共通の作業方針（AGENTS.md）

介護施設の公休表を作るスマホ向けアプリです。Codex・Claude Codeなど、使用するAIにかかわらず、この文書を作業の入口にします。

## 作業開始

1. 対象ブランチと最新の `main`、既存の未コミット変更を照合する。ユーザーの作業を上書きしない。最新の状態を取得できない場合は、その制約を明示する。
2. 依頼の範囲と反映先を把握し、下の表から該当する仕様・実装・テストを読む。関係のない資料を一括で読む必要はない。
3. 現行仕様と実装を照合し、変更による影響を調べてから着手する。

- 起動方法・リポジトリの案内：[ルートREADME](README.md)
- 通常作成の勤務条件・優先順位・保存互換・検証コマンド：[現行仕様](solver/README.md)
- 過去の設計理由・実測：[履歴目次](docs/history/README.md)。履歴は現在の要件ではない。必要な版・項目だけ参照する。

## 作業別の入口

| 依頼内容 | 最初に調べる実装 | 代表的なテスト |
| --- | --- | --- |
| 画面・デザイン・操作 | [mobile.css](public/mobile.css) · [mobile.js](public/mobile.js) · [index.html](public/index.html) | [表の配置](solver/tests/test_mobile_table_layout.cjs) · [横表示](solver/tests/test_mobile_landscape.cjs) |
| 勤務条件・希望・人数 | [mobile.js](public/mobile.js) · [input_data.py](solver/input_data.py) · [engine.py](solver/engine.py) · [validator.py](solver/validator.py) | [engine](solver/tests/test_engine.py) · [必要人数](solver/tests/test_staffing_requirements.py) |
| 計算速度・評価・配置品質 | [quality_search.py](solver/quality_search.py) · [allocation.py](solver/allocation.py) · [engine.py](solver/engine.py) | [探索](solver/tests/test_quality_search.py) · [時間](solver/tests/test_timing_accounting.py) |
| 作成・改善・候補採用 | [service.py](solver/service.py) · [background_normal.py](solver/background_normal.py) · [creation-workflow.js](public/creation-workflow.js) | [公開・ローカル一致](solver/tests/test_background_parity.py) · [画面の採否と時間](solver/tests/test_mobile_timing.cjs) |
| 保存・復元・データ移行 | [roster-storage.js](public/roster-storage.js) · [mobile.js](public/mobile.js) | [保存表](solver/tests/test_mobile_saved_tables.cjs) · [作業表の保持](solver/tests/test_mobile_work_retention.cjs) |
| 公開版の計算・途中復帰 | [api/background.py](api/background.py) · [background.py](solver/background.py) · [background-job.js](public/background-job.js) | [API](solver/tests/test_background_api.py) · [途中復帰](solver/tests/test_mobile_background.cjs) |

表は入口であり、変更範囲を限定するものではない。現行仕様にある個別の勤務条件・関連テストも参照する。

## 判断基準と作業方針

- ユーザーの明示的な依頼と承認済みの仕様変更を優先し、依頼されていない機能・勤務条件・画面を勝手に変更しない。
- 現行仕様、実装、テストが食い違う場合は、該当箇所と実際の挙動を示す。どれかを無条件に正しいとみなさず、仕様の判断が必要な部分はオーナーと決める。無関係な作業は続けてよい。
- コメントと画面の文言は日本語。設計や計算時間を変更するときは、先に測定・比較を示してオーナーと判断する。作成後の大幅な見直しを減らすことを重視する。
- タスク専用の一時作業環境では、必要なツールの導入や検証スクリプトの作成を自律的に判断してよい。既存の環境・テストを優先し、準備の手間も含めて最短で確かめられる方法を選ぶ。
- 職員の実名・個別の勤務データ・バックアップ・検証結果の生データはGitに含めない。再現には架空データを使う。

## 変更時に守ること

- 画面の配信ファイルを変えたら `public/index.html` のアセットの `?v=` をそろえて更新する。
- 勤務ルールの変更では通常入力の署名を更新する。方式名は画面とソルバーでそろえ、以前の条件で得た勤務や証明を新規作成へ流用しない。作業表と保存表は作成時の条件で復元できるようにする。[入力と署名](public/mobile.js) · [評価方式](solver/allocation.py)
- 計算条件を変えるときは独立検査・結果の表示も照合する。候補の比較や終了条件を変えるときは公開版とローカル版の両経路を確認する。[通常作成の仕様](solver/README.md)
- **「公休おまかせ」は3.53で終了。** 通常作成の変更に旧機能の復活・動作確認・保守を含めない。旧コードが残っていても、明示的な依頼がある場合にだけ再開を扱う。通常の保存表を維持し、おまかせの保存表は読み込み対象から外す。

## 作業完了と反映

- 実装を変えたら、対象のテストを追加・更新し、関連テストから実行する。反映前にPythonと画面の全テストを通す。探索時間に依存するため、Python全テストと重いベンチマークは別々に実行する。[テスト手順](solver/README.md#開発とテスト)
- 仕様・起動手順・保存互換などを変更した場合は、対応する現行文書を同時に更新する。重要な設計判断・測定は必要に応じて履歴へ残す。同じ仕様を複数の文書に重複して書かない。
- 文書だけの変更では、変更内容・参照先・既存ルールとの整合性を検証する。実装や配信ファイルを変えていない場合、アプリのテストは省略できるが、省略したことを報告する。
- 公開版は `main` と連動する。勤務条件・計算品質や時間・保存互換・API契約・配信設定に影響しない小さな修正は、検証後に `main` へ直接反映できる。これらに影響する変更、影響範囲が不明な変更、AIの作業方針や反映ルール自体の変更は作業ブランチとPRを使う。個別の依頼で指定された反映範囲を優先する。
- 必須の検証に失敗した場合や実行できない場合は、成功として扱わず、理由と残るリスクを報告する。必要な検証が終わるまで本番反映しない。
- 最後に差分を見直し、変更内容・変更したファイル・検証結果（実行できなかったものを含む）・残る課題・反映先を報告する。コミット、PR、main反映、公開版での動作確認は区別する。
