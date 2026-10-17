# 受入検査レポート(自動生成)

`tools/run_acceptance.py` が生成した。ここでの「合格」は機械検査だけを指す。人による意味審査、実モデルでの判断品質、各利用経路での実呼び出し、実務での改善効果は、下表のとおり別に示す。公開された開発例の合格を、未使用評価・誤り率0・実務性能の証拠にしない。

## 実行環境

| 項目 | 版 |
|---|---|
| python | 3.15.0 |
| platform | macOS-27.0.1-arm64-arm-64bit-Mach-O |
| pydantic | 2.14.1 |
| pdfplumber | 未導入 |
| pdfminer.six | 未導入 |
| pypdfium2 | 未導入 |
| sentence-transformers | 未導入 |
| torch | 未導入 |
| transformers | 未導入 |
| numpy | 2.5.4 |
| Pillow | 12.3.0 |

テスト 108 件: 失敗 0・エラー 0・skip 4。skip は未実施であり合格に数えない(Ruri実検索・pdfplumber が未導入の環境で出る)。

## 区分別の状態(06-acceptance-matrix.md)

| 区分 | 状態 | 根拠・残り |
|---|---|---|
| 設計資料の整合性 | 検査済み(合格) | `tools/check_design_docs.py`(manifestのハッシュ・JSON・ID・リンク)。資料の検査であり実装の検証ではない |
| 用語・責務の判断 A01〜A12, A17, A28〜A29 | 機械ガード合格／**意味審査は未実施(独立確認待ち)** | 作成者は実装担当AI。語彙ガードは必要条件のみ。確認票: docs/SEMANTIC-REVIEW-SHEET.md |
| 出典・引用の機械検査 A13〜A18 | 機械検査 合格 | 不明ID・版違い・範囲外・改変・否定欠落を検出。A17は機械合格と意味不支持を別表示 |
| 画像・PDFの実読解 A19〜A20 | 機械側合格／視覚確認は自己確認のみ | A20: 実PNG・1ページPDFを開いて凡例を確認(実装担当AI)。独立確認・実利用でのPDF読解は未実施 |
| 匿名比較・理解問題 A21〜A23 | 機械検査 合格／人の評価は未実施 | 配布物の秘匿・割付保存・非相殺・単一版配布を検査。実際の評価者による採点は未実施 |
| フィードバックと更新 A24〜A27 | 機械検査 合格 | 保留の保持・回帰例化・転載の扱い・資料変更の検出 |
| 更新競合・保存失敗 | 機械検査 合格 | 版の競合、採用失敗時の巻き戻し、原子的保存(A34, A42) |
| 検索 | 実Ruri実行済み(下記)／効果は未評価 | 一致検索とRuri(cl-nagoya/ruri-v3-70m)を同一課題で比較。件数が少ない公開例で、Ruri採用の根拠にしない |
| 導入・更新・削除 A30 | 仮配置で機械検査 合格／実環境へ導入済み | 3環境(4配置先)を一時HOMEで往復。実ユーザーのホームへは導入(--apply)と照合まで実施。実環境での更新・削除は未実施 |
| 実呼び出し | 一部実施(下の環境別表) | Claude Code・Codex・Antigravity CLI は合成データ1プロンプトで実モデルによる呼び出しを観測(docs/evidence/real-host-*.md)。リモート・Work・Coworkは未実施。1プロンプトの結果で、品質・他入力・他モデルは示さない |
| 開発の後片付け A31 | **未到達** | マージ・公開は未実施。`tools/post_merge_cleanup.py` を仮のgitで検査済み |
| 利用不能時の表示 A32 | 機械検査 合格 | 環境別証拠台帳 docs/HOST-EVIDENCE.json |
| 分散ログと改善ループ A33〜A48 | 仮保存先の機械検査 合格／各ホストの実記録は Claude Code ローカルのみ | A48の環境別は下表 |
| 本人の習得・実務効果 | **未実施** | 相手の理解・自力説明・再発機会・時間を実測していない |

## 環境別の証拠(docs/HOST-EVIDENCE.json)

| 環境／経路 | placement | register | invoke | source_read | scripts_run | footer_output | record_saved | export_import | 総合 |
|---|---|---|---|---|---|---|---|---|---|
| claude-code / local | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | verified |
| claude-code / remote | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |
| codex / local | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | 成功 | verified |
| codex / remote | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |
| antigravity-ide / local | 成功 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |
| antigravity-cli / local | 成功 | 成功 | 成功 | 未実施 | 成功 | 成功 | 成功 | 成功 | incomplete |
| antigravity / remote | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |
| chatgpt-work / account | 成功 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |
| claude-cowork / account | 成功 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | 未実施 | incomplete |

成功は、証拠(種別と内容)がある段階だけ。仮配置・導入の成功は登録・呼び出しの根拠にならない。総合 verified の経路: 2(合成データ1プロンプトの観測に限る)。

## 検索(実Ruri・同一課題)

課題 11 件(独立 11 件・公開された開発用ケース。未使用評価ではない)。

| 方式 | hit@1 | hit@3 |
|---|---|---|
| 用語・別名の一致 | 9/11 | 10/11 |
| Ruri | 9/11 | 11/11 |

モデル `cl-nagoya/ruri-v3-70m` revision `07a8b0aba47d29d2ca21f89b915c1efe2c23d1cc`、sentence-transformers 6.1.0・torch 2.14.1・transformers 5.20.1、接頭辞 `検索クエリ: `/`検索文書: `。
用語エントリは根拠資料の行から作っており、正解も同じ資料。小規模な自己参照的な動作確認であり、Ruriの採否を決める証拠ではない(件数・独立課題数が少ない)。

## A01〜A48

| ID | 種類 | 検証区分(03) | 状態 |
|---|---|---|---|
| A01 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A02 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A03 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A04 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A05 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A06 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A07 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A08 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A09 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A10 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A11 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A12 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A13 | reference_integrity | deterministic | 機械検査 合格 |
| A14 | reference_integrity | deterministic | 機械検査 合格 |
| A15 | reference_integrity | deterministic | 機械検査 合格 |
| A16 | reference_integrity | deterministic | 機械検査 合格 |
| A17 | semantic | human_or_independent_semantic_review | 機械検査 合格／意味・運用の独立確認待ち |
| A18 | reference_integrity | deterministic | 機械検査 合格 |
| A19 | visual_unavailable | human_or_independent_semantic_review | 機械検査 合格／視覚確認は実装担当AIの自己確認のみ。独立確認待ち |
| A20 | visual_available | human_or_independent_semantic_review | 一部未実施(skip) |
| A21 | blind_assignment | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A22 | non_compensatory_scoring | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A23 | single_version_comprehension | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A24 | feedback_unresolved | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A25 | feedback_to_regression | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A26 | duplicate_evidence | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A27 | source_drift | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A28 | supported_correction | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A29 | audience_adaptation | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A30 | install_update_uninstall | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A31 | post_merge_cleanup | implementation_artifact_check_and_independent_review | 未到達(マージ・公開は未実施)。後片付けの手順は仮のgitで機械検査済み |
| A32 | unavailable_host | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A33 | run_lifecycle | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A34 | logging_failure | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A35 | feedback_correction | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A36 | export_permission | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A37 | import_deduplication | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A38 | untrusted_package | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A39 | disconnected_remote | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A40 | cause_scoped_proposal | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A41 | paired_evaluation | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A42 | adoption_version_conflict | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A43 | metrics_missingness | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A44 | retention_deletion | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A45 | feedback_budget_sampling | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A46 | gold_separation | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A47 | source_nonretention | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |
| A48 | portable_logging | implementation_artifact_check_and_independent_review | 機械検査 合格／意味・運用の独立確認待ち |

自動検査の集計: 合格 47・不合格 0・一部skip 1・自動検査なし 0(A31は未到達として別扱い)。
