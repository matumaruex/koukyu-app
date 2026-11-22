# 通常作成の仕様と検証

3.93の通常画面から送る入力と、利用者に返す表を対象とします。依頼に合わせて該当する項目を読んでください。[開発とテスト](#開発とテスト) · [入力と勤務条件](#入力と勤務条件) · [計算と候補の採用](#計算と候補の採用) · [保存と復元](#保存と復元) · [版別の記録](../docs/history/README.md)

## 開発とテスト

リポジトリのルートで実行します。推奨のPythonは3.12。依存関係は `pyproject.toml` と `uv.lock` にあり、全テストにはOR-Toolsに加えてバックグラウンドAPI用の `vercel-workflow` と、画面テスト用のNode.jsが必要です。[依存定義](../pyproject.toml) · [固定した依存バージョン](../uv.lock)

```sh
uv sync --frozen
uv run --frozen python -m solver.app_server
```

ブラウザで `http://127.0.0.1:8766/` を開きます。Windowsで画面だけ試す場合は [アプリ起動.ps1](../アプリ起動.ps1) がローカル計算に必要な依存を準備します。[起動.ps1](../起動.ps1) は旧検証室（8765番）を開く別の入口です。uvを使わない場合はPython仮想環境にルートの [requirements.txt](../requirements.txt) をインストールすると全テストのPython依存がそろいます。

```sh
uv run --frozen python -m unittest discover -s solver/tests
```

JavaScriptテストは1ファイルずつ実行します。次はsh系シェル用です。PowerShellでは下のコマンドを使います。

```sh
for f in solver/tests/test_*.cjs; do node "$f" || exit 1; done
```

```powershell
Get-ChildItem solver/tests/test_*.cjs | ForEach-Object {
    node $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "テスト失敗: $($_.Name)" }
}
```

## 入力と勤務条件

| 項目 | 通常画面から作る表の扱い | 実装・代表テスト |
| --- | --- | --- |
| 期間と対象者 | 指定月16日〜翌月15日。職員設定で外した人は、手動で戻すまで対象外。計算には対象者の氏名を除き、職員IDを対応付けて送る。 | [画面の入力生成](../public/mobile.js) · [対象外の継続](tests/test_mobile_staff_persistent.cjs) |
| 公休と有給 | 新規職員は9日固定。登録済みの「以上」は最低日数として扱う。固定の人を余分な公休日数の比較から外す。有給は希望休として守り、公休の内数として「有」を表示する。 | [公休固定](tests/test_fixed_days_off.py) · [新規・旧設定](tests/test_mobile_fixed_days_off.cjs) · [有給](tests/test_mobile_paid_leave.cjs) |
| 希望・固定・勤務資格 | 1人1日1勤務。希望休・希望勤務・固定マスを守る。夜勤は毎日1人、翌日は明け、その翌日は公休。パートの勤務はPで、登録の勤務時間を人数集計に使う。 | [勤務モデル](engine.py) · [独立検査](validator.py) · [希望勤務](tests/test_shift_requests.py) |
| 前期と連勤 | 「希望・前期」から職員ごとに直前5日を入力する。旧データや前期表から得た7日分も保持し、手入力を優先する。全員の連勤上限から夜勤を除き、パートの週上限は通常作成に適用しない。実績不足で境界を確認しきれない場合は画面に示す。 | [5日・7日の互換](tests/test_mobile_history_five.cjs) · [境界の検査](tests/test_history_five.py) · [夜勤と連勤](tests/test_night_consecutive_exclusion.py) |
| 連休と勤務の並び | 職員別に指定した連休の必須回数は、今期内の連続した公休2日以上を1回と数える。「連休なし」と「公→出勤→公を避ける」は職員別。自動配置による4連休以上の回避は全員共通で、希望休と入力済みの前期実績だけでできた並びは対象外。 | [連休の数え方](rest_blocks.py) · [単独出勤](tests/test_isolated_work.py) · [公休の連続](tests/test_rest_streak.py) |
| 必要人数 | 朝7:00・昼10:00・夕17:45を検査する。日別指定と日曜の緩和条件がある。日中の人数不足は件数と日付を示した表として返せる。通常作成は夜勤未配置を許可しない。 | [必要人数の検査](tests/test_staffing_requirements.py) · [通常作成のリクエスト](background_normal.py) |
| 夜勤・残業の配置 | 希望休の初日は「夜勤→明け→希望休」と、間に公休を1日挟む並びを同等に評価する。残業は可能な職員を対象とし、月上限と連日不可を守る。月内の夜勤・残業の集中は7・14・15日間の窓で評価し、仕上げで減らす。 | [希望休の判定](night_preferences.py) · [残業上限と比率](tests/test_proportional_overtime.py) · [夜勤分散](night_distribution.py) · [残業分散](overtime_distribution.py) |

画面の通常入力は `partWeeklyLimit: false` や `excludeNightFromConsecutive: true` を明示します。旧API入力で項目を省略したときの既定値とは区別してください。3.93の通常入力署名は `rules-3.73`、評価方式は `quality-first-19` です。[通常入力](../public/mobile.js) · [入力の正規化と互換処理](input_data.py)

**画面で確認する場所**　職員の変更は「職員」、希望休・有給・希望勤務と前期実績は「希望・前期」、必要人数は設定から入力します。公休表は名前→日付→公休・残業・夜勤・A・Bの集計の順です。通常文字は黒、希望は赤、土曜・日曜は列全体を水色・ピンクにします。職員名の背景色でA・B・C・パートを区別し、表本体から横表示を開けます。[職員別入力](tests/test_mobile_combined_input.cjs) · [表のレイアウト](tests/test_mobile_table_layout.cjs) · [横表示](tests/test_mobile_landscape.cjs)

## 計算と候補の採用

公開版は `api/background.py` が作成IDを発行し、ワークフローが画面を離れても計算を続けます。PCローカル版は画面を開いたまま `/api/schedule` を繰り返し呼びます。どちらも `service.dispatch` を通してCP-SATで表を作り、独立検査を行います。[公開版の入口](../api/background.py) · [ワークフロー](background.py) · [ローカル版の入口](app_server.py) · [共通の計算窓口](service.py)

1. **新しく作る**　初回は計算予算最大8分。成立した表があり、最適の確認前で処理エラーもなければ、その勤務を起点に追加改善を1回実行してから表示する。計算予算は合計最大約16分で、通信・待機時間は別。
2. **さらに改善する**　表示中の表から最大約8分の1回。初回・改善とも1回の計算要求は最長60秒。条件→残業合計→残業配分→配置の順に進み、停滞待ちは順に90秒・90秒・30秒・60秒。改善時は最後の配置だけ120秒になる。最少の証明が得られればその段階を早く終える。
3. **結果を採用する**　自動・手動とも、改善後に評価が上がったときだけ別の勤務配置に切り替える。同点なら元の勤務を保ち、同じ勤務に対する新たな証明は採用できる。自動の追加改善だけが失敗した場合は初回の確認済みの表を残す。

[探索の段階と停滞待ち](quality_search.py) · [公開版の候補比較](background_normal.py) · [ローカル版の候補比較](../public/creation-workflow.js) · [公開版との一致](tests/test_background_parity.py) · [画面の時間・採否テスト](tests/test_mobile_timing.cjs)

**候補の評価順**は、連休なしの例外、連勤・日勤種類などの例外、夜勤端数の例外、連休回数差の超過、単独出勤、3連休超過が先頭です。続いて人数不足・夜勤不足、同じ出勤サイクルでの残業超過、希望休の夜勤後配置の未達、夜勤回数差を比べます。そのあと残業合計、残業配分、人数超過、全員に共通して配れる追加公休、月内分散・A/B比率などの細部を評価します。残業の希望は配分の目安で、残業合計を増やして合わせる要件ではありません。[比較順の定義](background_normal.py) · [配置の評価](allocation.py) · [残業サイクル](overtime_cycles.py)

**結果の読み方**　`FEASIBLE` は成立、`DRAFT` は人数不足などを報告する候補、`OPTIMAL` は計算した条件の範囲で最適。例外の検出と、その件数が最少である証明は区別します。手編集後の検査や停滞終了だけでは、その配置が不可避とは言えません。`UNKNOWN` は時間内に成立を確認できなかった状態で、`INFEASIBLE` は条件が両立しない判定です。条件を緩めて調べた診断結果は理由の提示に使います。[独立検査](validator.py) · [例外と証明の表示テスト](tests/test_mobile_rule_exceptions.cjs)

## 保存と復元

- **作業中の表**は期間ごとに作成時の条件とともに `koukyu_v4_work` へ自動保存します。入力条件を変更しても元の表を保持し、当時の条件で表示・保存・印刷します。編集・追加改善には一致する条件が必要です。[作業表の復元](tests/test_mobile_work_restore.cjs) · [条件変更後の保持](tests/test_mobile_work_retention.cjs)
- **名前を付けて保存した表**は入力とともに `koukyu_v4_data` に保持します。保存一覧から開くと、その表のコピーが対象期間の作業表になり、再読み込み後も残ります。保存元の控えはそのままです。バックアップの書き出しは入力と名前付きの控えが対象なので、作業中の表を別端末へ移すときは先に「この表を保存」を使います。現在も同じIDで登録されている職員のチーム色には現在の区分を使います。[端末の保存・移行](../public/roster-storage.js) · [保存・読込テスト](tests/test_mobile_saved_tables.cjs) · [チーム表示](tests/test_mobile_teams.cjs)
- **公開版の途中復帰**は端末の作成IDと秘密を使います。戻ったときに対象期間・入力条件・表を照合し、完成表を端末に保存できてから受け取り情報を消します。保存に失敗した場合は再試行できます。[受け取り処理](../public/background-job.js) · [中止・再読込・保存失敗のテスト](tests/test_mobile_background.cjs)
- **廃止機能**の「おまかせ」は、通常画面に入口を設けず、APIで作成・検査を拒否します。旧バックアップからは通常の保存表を引き継ぎます。[APIテスト](tests/test_retired_auto.py) · [保存移行テスト](tests/test_mobile_retired_auto.cjs)

過去の測定条件・当時のUI・設計案を調べる際は[履歴目次](../docs/history/README.md)から対象の版を選んでください。
