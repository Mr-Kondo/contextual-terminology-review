# 記録・フィードバック・更新

仕様は設計資料 07-feedback-and-storage.md。ここでは操作だけを書く。

## 保存先

| 設定 | 内容 |
|---|---|
| `runtime_data_root` | この実行先の記録（runs/ と outbox/）。案件で保存を許可された場所 |
| `improvement_root` | 許可済み記録の取り込み先、更新案、評価、採否、基準データ（standard/） |
| `evaluation_gold_root` | 評価用の正解・未使用例。レビューを生成・改善するAgentから隔離する |
| Skillフォルダ | Skill本体のみ。実データを置かない |

絶対パスは利用開始時に利用者へ確認し、`--runtime-root` などで渡す。未指定なら記録しない（自動で別の場所へ退避しない）。保存先が使えない環境（リモートで永続領域がない等）は、消失リスクと「記録不能・未収集」を伝え、`ctr.py export` の書き出しか、手動の記録票（references/hosts.md）を案内する。

## 記録

```
ctr.py store init --runtime-root ABS            # policy.json（原文保存=不可、共有=未設定が初期値）
ctr.py record start --runtime-root ABS --host claude-code --route local --domains 業務用語 [--target-text-file F]
ctr.py record finish --run-id ID --review review.json --sources sources.json
ctr.py record fail   --run-id ID --error-class tool_failed
```

- 開始で run.json を作り、終了・失敗は別のイベントとして追記する。書き込みは一時ファイル→原子的な置換で、保存後に再読込して `verified` を返す。既存IDは上書きしない。
- 保存できなければ `ok:false`・終了コード3。「保存未確認」と伝え、記録済み件数に加えない。
- 終了イベントのない実行は `check runs` で `incomplete_suspected`（開始から一定時間内は `in_progress_or_unknown`）。原因は推測しない。
- 原文は `store set-policy --raw-text allow` のときだけ `private/` に保存する。不許可なら参照IDと非保存理由だけを残し、再現できる範囲が限られることを伝える。
- モデル識別子が取得できなければ `unknown`（後から埋めない）。

## フィードバック

```
ctr.py feedback add --run-id ID --finding-id F1 --validity ok|ng|unknown --intent kept|changed|unknown \
    --usage as_is|edited|unused --receiver confirmed|mismatch|unconfirmed [--reason ...] [--corrects EVENT_ID]
ctr.py feedback time --category record|evidence|compare|practice|setup --minutes 5 --who self
```

- 未回答は未回答のまま（肯定にしない）。AI疑義は `--source ai_suspicion`、自動検査は `automated_check`、人は `human`。集計は人の確認と別に数える。
- 訂正は元を消さず `--corrects` で追記する。集計は有効な最新だけ。訂正・再取り込みで独立例数を増やさない。
- 「受け手との確認: 確認できた」は理解の実測ではない。実測は質問・回答・必須項目の採点（references/evaluation.md）。

## 収集（ファイル方式のみ）

```
ctr.py store set-policy --share-fields run_status,versions,problem_axes --share-scope <範囲> --granted-by <許可者>
ctr.py export --runtime-root ABS            # outbox/<package_id>/ に manifest と項目別のイベント
ctr.py import PACKAGE_DIR --improvement-root ABS
```

- 共有許可が未設定なら export は止まる（終了コード4）。インストールを送信同意とみなさない。
- 書き出せる項目は列挙値・ID・件数・版だけ。入力全文、出力全文、引用、抜粋、添付、絶対パス、氏名・案件名、受け手の回答、評価用正解、理由の自由記述は含まれない。privateフォルダを除くだけで匿名化・共有可としない。
- import は一時領域で、スキーマ・ハッシュ・サイズ・許可項目・パス境界・リンクを検査してから確定する。同じイベントの再取り込みは重複加算せず、同一ID別内容は quarantine に隔離する。添付はデータとして読むだけで実行しない。ハッシュ一致は送信者の認証でも内容の正しさでもない。
- 自動送信・常駐・定期実行は設定しない。

## 更新（人の明示的な採用が必要）

```
ctr.py propose create --spec spec.json        # cause: definition_gap|retrieval|judgment|audience|unagreed
ctr.py evaluate compare --proposal ID --results results.json
ctr.py evaluate adopt --proposal ID --evaluation EID --approved-by NAME --reason ... --i-approve
ctr.py evaluate restore --to-version HASH --approved-by NAME --reason ... --i-approve
```

- 原因が「責任・成果物が未合意」なら差分を持てない（確認事項にする）。「取りまとめ＝常に主担当」のような一般規則を採用しない。
- 比較は同じ入力・資料・モデル・生成設定・採点条件で行う。違えば `confounded` として採用をブロックする。意味保持の fail/unknown が一つでもあれば、読みやすさの平均が高くてもブロック。修正不要例と正しく処理できていた例が必要。
- 採用は、評価時の直前の版と現在の版が同じ場合だけ。評価後に基準が変わっていれば `base_version_conflict`。承認は別の差分に使い回せない。AIの採点は採用承認にならない。復元も判断記録として追記する。
- 確認済みの問題だけを `evaluate regression` で回帰例にできる（確認者・理由・位置・保持条件・禁止変更が必要）。保留・好み・未合意は不可。回帰例にした例は未使用評価から外れる。

## 削除

`ctr.py delete plan --id ID` で派生物（出力内の抜粋・索引・outbox/inbox・回帰例）を確認。`delete apply --confirm` は追跡できた範囲を削除し、共有先・バックアップは「削除確認待ち」として残し、削除済みIDの再取り込みを防ぐ。通常の更新・アンインストールでログは消えない。
