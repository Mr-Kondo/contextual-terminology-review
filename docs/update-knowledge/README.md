# 更新時の知識索引（限定試行）

スキルの更新案を検討するときだけ使う、任意の探索補助。通常の用語レビューには読み込まない。この索引は根拠の場所を案内するものであり、実行用スキル、原資料、採用承認を置き換えない。[試行設計](../../adr/2026-11-03-update-knowledge-pilot.md)と[比較結果・採否](../WIKISKILL-PILOT.md)を先に確認する。

## K1 引用が一致しても、意味と適用条件を確認する

- 探す言葉: 引用一致、保護語、責務、承認、草案、ただし、範囲の縮小、部分否定、警告。
- 適用: 参照検査が通ったのに修正案が意味を変える疑いがあるとき。
- 根拠: [参照検査](../../skill/contextual-terminology-review/references/citation.md)、[判断基準・反例](../../skill/contextual-terminology-review/references/judgment.md)、[Issue #15](https://github.com/Mr-Kondo/contextual-terminology-review/issues/15)、[Issue #5](https://github.com/Mr-Kondo/contextual-terminology-review/issues/5)。
- 確認済みの範囲: 機械的な引用一致と、文脈上の妥当性は別の確認である。警告は人またはAgentが原文・資料・周辺条件を読むための候補であり、確定誤用ではない。
- 反証・不採用条件: 警告だけを根拠に不適合と断定しない。「成果物」を「資料」へ狭めるなど、読みやすさのために対象・責務を変える案は意味保持として採用しない。
- 次の調査: 原文・本人の説明・資料に修正案の追加内容があるか、引用の前後で適用範囲が変わるかを確認する。

## K2 発動精度と検索の改善は、条件を分けて評価する

- 探す言葉: description、発動、ホスト差、Codex、Antigravity、未使用、test2、dev3、部分一致、キャッシュ・フロー。
- 適用: あるモデル・環境での成績を他環境へ広げたいとき、検索の誤検出を判断規則の変更で直そうとするとき。
- 根拠: [発動評価](../TRIGGER-EVAL.md)、[検索の採否](../RURI-ADOPTION.md)、[Issue #23](https://github.com/Mr-Kondo/contextual-terminology-review/issues/23)、[Issue #32](https://github.com/Mr-Kondo/contextual-terminology-review/issues/32)、[Issue #15](https://github.com/Mr-Kondo/contextual-terminology-review/issues/15)。
- 確認済みの範囲: 改善に使った課題は未使用評価ではない。モデルや資料などの条件差を分離する。長い語に含まれる短い語の一致は、専門的な誤用とは別の検索上の問題である。
- 反証・不採用条件: 1ホストの改善だけを3環境の改善としない。既知セットの成績だけでdescription変更を正当化しない。検索方式の問題を一般的な用語定義の変更に置き換えない。
- 次の調査: 原因を検索・発動・判断に分け、事前固定した条件で新旧を比べる。独立した未使用評価の制約は[更新・評価契約](../FEEDBACK-AND-STORAGE.md)を読む。

## K3 更新の完了には、配布工程と配置の確認が要る

- 探す言葉: VERSION、リリースノート、マージ、配布漏れ、installer、導入ツール、照合、cleanup。
- 適用: スキル版を上げる、配布物に必要なものが足りない、マージ後の確認を検討するとき。
- 根拠: [リリース手順](../RELEASING.md)、[導入・更新・削除](../INSTALL.md)、[版とノートの検査](../../tests/test_release_notes.py)、[Issue #49](https://github.com/Mr-Kondo/contextual-terminology-review/issues/49)、[Issue #5](https://github.com/Mr-Kondo/contextual-terminology-review/issues/5)。
- 確認済みの範囲: VERSIONに対応するノートが必要で、ノートの欠落はマージ前に検査する。配布物があることと利用先への配置は別である。既存のctr_install.pyを使い、導入先でverifyする。
- 反証・不採用条件: リリース作成だけでMacが更新されたと扱わない。開発資料だけの変更をスキル内容の変更と混同しない。
- 次の調査: 変更が配布スキルに入るかを確認し、該当する版・リリース・配置・後片付けを検証する。

## K4 記録は許可された範囲で共有し、未確認を知識へ昇格させない

- 探す言葉: export、ログ、匿名化、入力全文、共有、未回答、未確認、採用承認、rollback。
- 適用: 実行ログを改善に再利用する、指摘から一般規則を作る、AI採点で更新案を採用したいとき。
- 根拠: [記録・共有・更新の契約](../FEEDBACK-AND-STORAGE.md)、[週次手順・採用](../WEEKLY.md)、[実行時のフィードバック手順](../../skill/contextual-terminology-review/references/feedback-loop.md)。
- 確認済みの範囲: 共有対象の許可と内容確認が必要。匿名化だけで共有可能とは限らない。未確認の指摘は仮説として扱い、意味保持・比較条件・明示的な人の採用判断を分ける。
- 反証・不採用条件: 収集への未回答を肯定としない。入力全文や認証情報を索引へコピーしない。AIの採点を人の承認として扱わない。
- 次の調査: exportの許可項目と除外項目を確認し、原本は指定された保管領域に置く。採用前に根拠・比較結果・対象版・変更ハッシュを照合する。

## 維持のルール

根拠が変わったら該当項目を再確認する。新しい事例ごとにページを増やさず、既存4件で扱えるかを先に見る。矛盾や未確認は消さず、確認状態を更新する。Issue・ADR・評価結果の本文は複製しない。索引を自動的にproposeや実行用スキルへ接続しない。
