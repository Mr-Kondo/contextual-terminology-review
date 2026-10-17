# 既存Skillから取り入れる設計と機能

調査日：2026年10月17日。対象：contextual-terminology-review（用語・文脈レビュー）の実装準備。

## 1. 文脈

既存Skillの「設計の参考」「スクリプトの再利用候補」「そのままでは使わない部分」を分けて検討した。今回はローカルにあるSkill本文とコード、関連資料を読み、公開リポジトリの説明も確認した。利用者の採用指示により設計・実装指示・受入条件へ反映した。Skill本体・既存リポジトリの変更やコード移植は未実施。

コードが存在することと、今回の用途へ移植して動作・効果を検証済みであることは異なる。ローカルの作業ツリーを調べたため、各コードが公開Releaseと同一とは確認していない。

## 2. 核心的な論理

### 証拠

japanese-readability-editorには、数値・条件・否定・主体を保つ推敲手順だけでなく、人による評価、匿名二候補比較、理解問題、フィードバックの回帰ケース化、文書単位の集計が実装されている。official-prompt-tailorには、引用の位置・本文ハッシュ・適用範囲を結び付け、参照検証・意味審査・効果測定を分ける設計がある。

enterprise-searchのsearch-strategyは語・案件・時点・否定を分けて検索を組み立て、knowledge-synthesisは重複・不一致と出典の扱いを定める。brand-voice-enforcementは、保つ要素と相手・媒体に応じて変える説明の深さや調子を分ける。

### 仮説

最も費用対効果が期待できるのは、用語の辞書をさらに増やすことよりも、既存の評価・証拠追跡の仕組みを今回の判定軸へ適応させることである。ただし開発工数や改善率は未計測であり、この順位は設計判断である。

### 反論

既存ツールを丸ごと使えば新規実装は少なくなる。しかし、比較ツールは明示的なモードBと二候補、固定の入力項目・採点軸を前提にし、複数の同居モジュールへ依存している。今回の引用検査・用語の正誤・保留の評価をそのまま表現できるとは限らない。既存Skillのインストール場所を実行時の必須依存にせず、入出力が合う機能の再利用、または必要部分だけの適応を選ぶ。

## 3. 重要ポイント

### 採用した設計と、実装時の再利用候補

| 優先度 | 由来 | 取り入れる機能・設計 | 今回の適応 | 機会費用・注意点 |
|---|---|---|---|---|
| 1 | japanese-readability-editorの意味保持・比較 | 数値、条件、否定、主体、言い切りの強さ、発話の働きの照合。意味変更候補と採否を分ける | 責務・承認・完了状態を重点化。誤用を直す箇所と保護する事実・意図を分ける | 原文の誤りまで固定すると用語訂正ができない。文字列一致を全レビューの合否にしない |
| 1 | 同Skillの匿名比較・理解問題 | 作成した方式を隠す二候補比較。意味保持に合格した候補の選好を別集計。受け手は一つの版だけ読む | 役割、成果物範囲、完了条件、次の行動を読み手が理解できたか測る | 評価者の負担が増す。週30分と必要例での協力に合わせて少数を選ぶ。選択式だけでは自由な言い直しを証明できない |
| 1 | 同Skillのfeedback_readability.py | 確認者・理由・該当箇所・保持条件・禁止変更を記録し、確認済み問題を回帰ケースへ出力 | 誤用、説明不足、好み、未合意、確認不能を分離して記録する | 回帰例は以後未使用評価ではない。フィードバックだけで一般用語定義を変えない |
| 1 | official-prompt-tailor | 資料の版・位置・短い引用・ハッシュ・適用範囲を結ぶ。参照検証、意味審査、効果を別状態にする | 社内・案件・製品版にも適用。出典一覧を検査済み記録から生成する | 公式ドメイン専用の取得規則や製品別ログ検証は今回へ丸ごと持ち込まない。ハッシュは真実性や意味の理解を証明しない |
| 必須 | japanese-readability-editorの配布・管理 | 共通正本、利用先ごとの配置・配布、事前確認、更新時の退避、対象限定アンインストール、配置後検査 | Claude Code・Codex・Gemini Antigravityを対象とし、Work/Coworkの利用経路も別確認 | 既存コードには元Skill名に結び付く検査がある。名前の変更だけで再利用完了とはしない。更新失敗時の復旧を別に検査する |
| 2 | enterprise-search | 既知語・略語の一致検索と概念検索を使い分け、案件・版・時点で絞る。重複と競合を区別する | まず一致検索とRuriを比較する。必要時に両方の候補を整理する | 早期に複雑な順位統合を追加しない。コピー由来の資料を複数の独立した証拠に数えない |
| 2 | brand-voice-enforcement | 保つ要素と、相手・媒体によって変える表現を分ける | 職場の同僚、他職種、顧客、口頭、チャットで説明量・用語補足を調整する | トーン調整や社内慣用で、専門的正誤・正式合意を上書きしない |

### 実装前調査：構成・frontmatter・分量の比較

2026年10月17日に各指定ルートで読めた既存Skillのサンプルを確認した。以下の行数は確認したファイルの分量であり、推奨値・性能値ではない。プラグインの詳細な調査対象は末尾の参照一覧に記載する。

| 確認した場所 | Skill・分量 | 構成とトリガー | 今回の採否 |
|---|---|---|---|
| `~/.codex/skills` | graphify・722行 | name・description。コードベース等を広く対象にし、referencesへ分ける | 補助資料分離だけ参考。広いトリガー、722行の入口、知識グラフ基盤は今回採用しない |
| `~/.claude/skills` | japanese-readability-editor・202行 | name・description。推敲依頼と対象外を記述し、scripts・references・assets・dataを分離 | 用途・対象外の明示と必要時の参照を採用。202行という分量を目標にはしない |
| `~/.gemini/config/skills` | japanese-readability-editor・202行 | name・description。推敲依頼と対象外を記述し、scripts・references・assets・dataを分離 | 用途・対象外の明示と必要時の参照を採用。202行という分量を目標にはしない |

skill-creatorの段階的な読込みも取り入れ、今回の入口は目的・境界・通常手順・出力を中心とする。暫定目安は80〜150行だが、機械的な合否にはしない。frontmatter案は次のとおり。これは設計例であり、生成・登録済みのSKILL.mdではない。

```yaml
name: contextual-terminology-review
description: 業務・IT・科学工学・ビジネスの用語の用法と文脈を資料に照らしてレビューし、根拠付きの修正案や口頭の言い直しを示す。役割・成果物範囲の曖昧さ、専門語が伝わりにくい説明の確認に使う。コード全体の検証や書式だけの調整には使わない。
```

調査済みSkill名と採用点は完了報告にも残す。実装担当は利用可能な環境の現行ファイルを再確認し、未接続ホストを確認済みにしない。

### 既存コードの再利用候補

- `tools/review_readability.py`：自動検査と人の評点・理由を分ける土台。意味の自動保証として使わない。
- `tools/compare_readability.py`：候補名を隠した配布、左右の割付記録、意味保持・選好・欠測の分離。現行コードはモードB専用であり、今回の記録形式との適合確認が必要。
- `tools/comprehension_readability.py`：一人が一つの版だけ読む配布物と、正解・根拠を保つ主催者用記録の分離。別フォルダだけでアクセス隔離を達成したとは扱わない。
- `tools/feedback_readability.py`：確認済み指摘の回帰ケース化、人とLLMの判定照合。原入力・ハッシュ・判断者を記録する。
- `tools/statistics_readability.py`：同じ文書の反復を独立例にせず、文書を単位とする比較。ただしその推定法を今回の全指標へ無条件に転用しない。初期は件数・分母・欠測を優先する。
- `tools/install.py`、`tools/uninstall.py`、`tools/verify_install.py`：対象を絞った導入・更新・削除と配置後確認。元の対応環境全部を新Skillへ追加する必要はない。
- official-prompt-tailorの証拠契約：取得本文と参照記録の対応、更新検知、未確認状態の管理。専用の証拠基盤全体を導入する前に、今回必要な小さな処理を既存ライブラリで実装する。

コードをコピーする場合、japanese-readability-editorとofficial-prompt-tailorのローカルLICENSEでMITを確認した。再配布には適用される著作権・許諾表示を保持する。第三者Skill全体やその配布物を同条件で自由に転載できるとは推定せず、実際の再利用対象の条件を確認する。

### そのまま採用しないもの

- 表層的な文章指標を足し合わせた総合点を、専門的正確さや理解の点数にする方法。
- 用語の誤りを直すレビュー全体に、原文との全文一致を要求すること。
- 根拠資料は常に最新が勝つ、公式文書は常に会話より正しい、といった一律の優先順位。
- 同じ情報の転載を、複数の独立した証拠として確信度へ加算すること。
- brand-voice-enforcementにある、未解決事項へAgentの推奨を既定採用する扱い。責務・納品条件では確認不能を維持する。
- science-reviewの次元検査等を、一般用語レビューの必須処理にすること。必要な科学・工学レビューだけの追加手段として残す。
- 独立した根拠のない自己採点を、校正済みの正しさの確率として表示すること。

### 新しい共通要件と、作成済み指示書の差分

2026年10月14日の実装指示書に対する以下の差分は、この一式の02-implementation-prompt.mdおよび06-acceptance-matrix.mdへ反映済み。旧版は履歴として別に残し、この一式を使用する。

1. **必須対象**：Claude Code・Codex・Gemini Antigravityの3環境で設計・実装する。既出のWork/Coworkも利用経路として残し、三つのCLIと同一動作だとは仮定しない。ローカル・リモートとも対象とし、未到達の環境は未検証と表示する。
2. **必須スクリプト**：インストール・更新・アンインストールを実装する。事前確認、既存データの保護、対象限定削除、更新失敗時の復旧、テスト用配置先での往復検査を含める。アカウント側の登録・削除をローカルスクリプトだけで完了したと報告しない。
3. **リリース後**：公開・マージの許可がある段階でのみ実施し、マージを確認してから作業用ブランチをローカル・リモートとも削除する。今回作った一時ファイル・仮想環境・バックグラウンド処理・worktreeを片付け、残す必要があるものは理由を報告する。成果物・利用データ・他者の作業は削除対象にしない。

## 4. 具体例

入力：「私が取りまとめます」。本人の意図は論点整理・関係者調整・成果物作成の主担当。案件資料では最終承認は上長とする。

意味保持の照合により、「私が最終承認します」を禁止する。根拠記録を付けて、「論点整理と関係者調整、成果物作成は私が主担当として進めます」のような候補を出す。匿名比較で好みを記録するだけでなく、別の受け手に一つの版だけ見せ、「誰が何を担当し、誰が承認するか」を確認する。相手の理解を確認できない場合は、理解改善は未評価のままにする。

誤解が確認されたら、原文、意図、資料、受け手の回答、問題箇所、保持すべき条件、禁止する変更を記録して開発用の回帰例へ追加する。用語帳を「取りまとめ＝常に主担当」と変更してはいけない。次回は別の場面・未使用例で確認する。

## 5. 平易な説明

わかりやすく言うと、既存Skillから文章を直す技だけでなく、直しすぎを防ぎ、相手に伝わったか確かめ、確認できた失敗を次回の検査へ戻す仕組みを取り入れるということである。

## 6. 自己批判的考察

今回確認したのは設計資料とコードの存在・処理内容であり、移植後の動作、ブラウザでの操作、各利用環境の呼び出し、職場での改善効果は未検証。過去のメモにある初期実装の検証状況を、現在の実装全体の検証状況へ拡張しない。

選択式の理解問題は出題範囲の理解を見るもので、口頭で自力説明できる能力を直接証明しない。評点、理解課題、AIなしの後日課題を別に残す。意味保持の採点基準も、誤用箇所の根拠付き訂正を許すよう適応が必要。

設計上の適合についての確かさは0.8（主観評価）。性能・改善率の確率ではなく、実測の信頼度は未評価である。

## 7. 結論

意味・責務の照合、匿名比較と理解問題、確認済みフィードバックの回帰例化、出典追跡を初期から取り入れる設計として採用する。配布・更新・削除は新しい共通要件により必須である。検索の複合化・高度な統計・大規模な評価基盤は、実例で必要性を確認してから追加する。全体のコピーではなく、既存の入出力を合わせるか、必要な処理だけ適応させる。

### 第3版：フィードバック処理の具体化

mece-cluster-advisorの目的・軸・含む／含まないの定義を、六つの処理段階の整理に採用した。今回は少数の設計項目のため埋め込み・クラスタリングは実行せず、同Skillを新Skillの必須依存にしない。japanese-readability-editorの人の確認と自動検査の分離・確認済み問題の回帰化、official-prompt-tailorの参照と意味と効果の分離を07の記録・採用契約へ接続した。既存コードを移植・実行したという意味ではない。

具体的な保存・収集仕様は[07-feedback-and-storage.md](07-feedback-and-storage.md)、追加の公開受入条件は03のA33〜A48。新たな収集サービスや全会話監視は導入せず、原文と共有可能な情報を分ける。

## 8. 参考文献・使用箇所

- ［意味保持／要約］[japanese-readability-editorのSKILL.md](~/.agents/skills/japanese-readability-editor/SKILL.md)｜「変更してはならないもの」「構造を直す短い手順」「書き換えた後の照合」｜条件・主体・否定・発話の働きの保持。
- ［評価全体／要約］[人手評価ガイド](/Volumes/SSD/Programming/japanese-readability-editor/docs/human-evaluation.md)｜「匿名二候補比較」「指摘を確認し、回帰ケースにする」「一つの候補だけを読んで理解問題を解く」｜評価機能の利用方法。
- ［匿名比較／要約］[compare_readability.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/compare_readability.py:71)｜assignment・validate_pair_review｜候補名の秘匿、割付保存、両候補の意味保持と選好の分離。
- ［理解問題／要約］[comprehension_readability.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/comprehension_readability.py:54)｜reader_assignment・prepare｜単一版の配布と主催者側の正解保持。
- ［フィードバック／要約］[feedback_readability.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/feedback_readability.py:37)｜validate_decision・regression_suite｜確認者・根拠・原入力照合と確認済み事例の出力。
- ［数量評価／要約］[statistics_readability.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/statistics_readability.py:20)｜document_outcomes・estimate・summarize｜文書単位での比較と推定の限界。
- ［配布と更新／要約］[install.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/install.py:259)｜install_one｜事前確認、競合処理、旧版の退避と配置。
- ［対象限定削除／要約］[uninstall.py](/Volumes/SSD/Programming/japanese-readability-editor/tools/uninstall.py:1)｜冒頭の契約・refusal・remove_entry｜正本と他Skillの保護、画面から削除する環境との区別。
- ［出典検証／要約］[official-prompt-tailorのSKILL.md](/Volumes/SSD/Programming/official-prompt-tailor/.claude/skills/official-prompt-tailor/SKILL.md)｜手順3・4・5｜引用・位置・ハッシュ、参照／意味／効果の分離。
- ［資料更新／要約］[evidence-contract.md](/Volumes/SSD/Programming/official-prompt-tailor/.claude/skills/official-prompt-tailor/references/evidence-contract.md:38)｜drift・rules｜更新検知は意味の変更判定ではないという境界。
- ［検索／要約］[search-strategy](~/.codex/plugins/cache/claude-cowork/enterprise-search/1.1.0/skills/search-strategy/SKILL.md)｜Query Decomposition｜意図、案件、時点、否定と検索方式を分ける。
- ［重複と不一致／要約］[knowledge-synthesis](~/.codex/plugins/cache/claude-cowork/enterprise-search/1.1.0/skills/knowledge-synthesis/SKILL.md)｜Deduplication・Conflicting Information｜重複と異なる結論を区別。一律の最新優先は今回採用しない。
- ［相手に合わせる／要約］[brand-voice-enforcement](~/.codex/plugins/cache/claude-cowork/brand-voice/1.0.0/skills/brand-voice-enforcement/SKILL.md)｜Apply Voice Constants・Flex Tone for Context・Open Questions Awareness｜説明の深さ等は参考にし、未解決事項の既定採用は移植しない。
- ［科学レビューの分離／要約］[science-review](/Volumes/SSD/Programming/science-review-design/.claude/skills/science-review/SKILL.md)｜判定軸・最初に守る境界｜専門的妥当性と別の判断軸の分離。
- ［公開情報／要約］[japanese-readability-editor](https://github.com/Mr-Kondo/japanese-readability-editor)｜READMEの共通正本とインストール・削除の説明｜共通のSkill本文と環境別配布の構成。
- ［再利用条件／要約］[japanese-readability-editor LICENSE](/Volumes/SSD/Programming/japanese-readability-editor/LICENSE)｜MIT許諾と表示条件｜コピー時の適用条件。
- ［再利用条件／要約］[official-prompt-tailor LICENSE](/Volumes/SSD/Programming/official-prompt-tailor/LICENSE)｜MIT許諾と表示条件｜コピー時の適用条件。
- ［必須要件／利用者指定］本会話の2026年10月17日のAGENTS.md指示｜共通スキル作成要件・開発の締めくくり｜3環境、導入更新削除、マージ後片付け。外部リンクなし。

未実施：Skill本体へのコード移植・コピー、既存ツールの実行・統合試験。設計資料・実装指示書の改訂は実施済み。
残るリスク：既存コードの存在や類似用途を、そのまま今回の品質・効果の証明と扱うこと。
