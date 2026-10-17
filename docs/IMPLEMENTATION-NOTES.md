# 実装メモ（着手時の確認・既存Skill調査・判断の根拠）

2026-10-17 に実装。設計資料第3版（`00`〜`07`、`manifest.json`）に従った。ここに書くのは、実装中の確認結果と判断で、設計資料の改訂ではない。

## 1. 着手時の確認と方針

| 確認したこと | 結果 |
|---|---|
| 設計資料の場所 | 依頼文は `./contextual-terminology-review-design` だが、そのフォルダは存在せず、資料はプロジェクト直下にあった。移動・改名せず、直下の資料を参照した（manifestは直下の相対パスで一致） |
| 作業場所・既存ファイル | `/Volumes/SSD/Programming/contextual-terminology-review`（実装時点ではgitリポジトリではなかった。公開時に `git init`）。既存は設計資料8点・`manifest.json`・空の `.claude/.cc-writes`。**どれも変更・上書きしていない**。新規は `skill/` `tools/` `tests/` `docs/` `requirements*.txt` |
| AGENTS.md / CLAUDE.md | プロジェクト内には無し。ユーザーのグローバルCLAUDE.md（RTK、graphify、スキル開発前の調査、締めくくりの後片付け）に従った |
| 実行環境 | システム Python 3.15.0（pydantic 2.14.1 あり、pdfplumber・sentence-transformers なし）。依存検証用にプロジェクト内 `.work/venv`（Python 3.12.15）を作成し、後片付けで削除する |
| ネットワーク | 既定では遮断。PyPI と Hugging Face には、許可リスト付きで接続した（依存導入・モデル取得のみ。資料・ログの外部送信は無し） |

方針: 小さく保つ。標準ライブラリ＋Pydantic＋既存ライブラリを使い、DB・サーバー・常駐処理・MCP・追加OCR・追加学習は作らない。Skill本体は短く、詳細は `references/`、反復する検査だけ `scripts/` に置いた。

## 2. 実装前の既存Skill調査（読んだ実ファイルと採否）

2026-10-17 に、読めた範囲を実際に開いて確認した（行数は確認時の値で、推奨値ではない）。

| 場所・Skill | 構成・frontmatter・分量 | 取り入れた点 | 取り入れなかった点と理由 |
|---|---|---|---|
| `~/.claude/skills/japanese-readability-editor`（`~/.gemini/config/skills/` にも同名。`~/.codex/skills/` も同名） | SKILL.md 202行。`name`・`description`のみ。`scripts/ references/ assets/ data/`。descriptionで用途と対象外を明示 | 用途と対象外をdescriptionに書く。詳細を`references/`へ分ける。保持すべき要素の照合観点（数値・条件・否定・主体・発話の働き） | 202行の入口・モード分け・国語データ（このSkillの範囲外）。既存Skillは変更せず、依存もしない |
| `/Volumes/SSD/Programming/japanese-readability-editor/tools/`（`install.py` `uninstall.py` `compare_readability.py` `comprehension_readability.py` `feedback_readability.py`） | MIT。`install.py` は配置先表・退避・事前確認。比較/理解問題はモードB専用の入出力と同居モジュール（`review`/`evaluation`）に依存 | 配置先の表、`--dry-run`相当の事前確認、退避して置換、対象限定削除、配置後照合の考え方。匿名比較の割付と主催者側の対応表、一人一版の配布、確認済み問題の回帰化 | **コードはコピーしていない**（モードB専用・元Skill名・同居モジュール依存のため）。設計だけを参考に `ctr_install.py` `ctr_blind.py` `ctr_improve.py` を新規に書いた（MITの表示義務を生む再配布は発生していない）。元の対応環境すべて（Copilot・OpenCode・Hermes）は対象外 |
| `/Volumes/SSD/Programming/official-prompt-tailor/.claude/skills/official-prompt-tailor`（SKILL.md 115行・`evidence-contract.md`） | MIT。引用・本文ハッシュ・行範囲・短い原文・`drift`（更新検知）。取得／読了／審査は別イベント | 参照検証・意味審査・実測を別の状態にする、資料の版・位置・短い引用・ハッシュを結ぶ、更新検知は意味の変更判定ではない | 公式ドメイン専用の取得規則・製品別ログ検証・専用の証拠基盤は持ち込まない。コードはコピーしていない |
| `~/.claude/skills/mece-cluster-advisor`（SKILL.md 124行、`references/judgment.md` 86行） | 目的・軸・含む/含まないで判断材料を出し、確定は人 | 07の六つの処理段階（記録→検出→確認→更新案→比較評価→反映・監視）を「含むもの/含まないもの」で定義するやり方。「判断材料を出し、確定は人」 | 埋め込み・クラスタリングの実行（今回の項目数では不要）。必須依存にしない |
| `~/.codex/plugins/cache/claude-cowork/enterprise-search/1.1.0/skills/search-strategy`（221行）・`knowledge-synthesis`（257行） | 検索の分解・出典の付け方・重複排除・矛盾情報 | 語・案件・時点・否定で検索を分ける。重複と不一致を区別する | 「最新版が勝つ」という重複排除の優先順位（Deduplication Priority）は採用しない（旧案件に旧版を適用できるため）。複雑な順位統合・信頼度の点数化 |
| `.../brand-voice/1.0.0/skills/brand-voice-enforcement`（107行） | 声は一定・調子は文脈で変える。Open Questions | 専門的意味・正式合意は固定し、説明量だけ相手・媒体に合わせる | 未解決事項へのAI推奨の既定採用は移植しない（責務・納品条件は確認不能を維持） |
| `~/.codex/skills/.system/skill-creator`（Codex用）／synced `skill-creator` | 段階的な開示、name・descriptionは安価に判別できること、`references/`は必要時のみ読む | 入口は目的・境界・手順・出力。詳細は`references/`、反復検査だけ`scripts/`。説明は用途を具体的に、除外は誤選択を防ぐ場合だけ | `agents/openai.yaml`（Codexの表示メタデータ）は追加しない。frontmatterを`name`/`description`に絞り、Cowork等への持ち込みを妨げない方針のため。必要になれば追加できる |
| `~/.claude/skills/test-guard`（119行）・他の *-guard | descriptionに「使う場面／使わない場面」を明記 | 「使わない」場面の明示（コード全体・計算・書式のみ） | 英語の長い用途列挙 |
| `~/.codex/skills/graphify`（722行、SKILL.md 41.5K） | 広いトリガー | 補助資料を分ける考え方のみ | 広いトリガー・722行の入口・知識グラフ基盤 |
| `~/.agents/skills/synced/`、`woo-guard` など無関係なSkill | — | — | 今回の用途と無関係。内容は読んでいない（未確認） |

未確認: 未接続ホスト（リモート・アカウント側）の `~/.codex/skills` 等。実装担当の環境で読めた範囲のみ。

## 3. 利用した依存・モデルと版

| 部品 | 版（検証時） | ライセンス | 役割 |
|---|---|---|---|
| Pydantic | 2.14.1 | MIT | 参照・レビュー・資料登録簿の検査。strict で暗黙の型変換を避ける。型検査は意味の判定器ではない |
| pdfplumber | 0.11.10（pdfminer.six 20260107、pypdfium2 5.14.0） | MIT | 機械生成PDFの文字・表・ページ・位置。スキャン・図は視覚確認が別に必要 |
| SentenceTransformers | 6.1.0（torch 2.14.1、transformers 5.20.1、numpy 2.5.4） | Apache-2.0 | 任意のRuri検索。既存の `util.semantic_search` を使用 |
| Ruri v3 310m（既定） | `cl-nagoya/ruri-v3-310m`、revision `18b60fb8c2b9df296fb4212bb7d23ef94e579cd3`（採否の検証に使ったsnapshot。重み約1.2GB）。70m（`cl-nagoya/ruri-v3-70m`、revision `07a8b0aba47d29d2ca21f89b915c1efe2c23d1cc`）は `--model` で指定できるが、基準に届かなかった | Apache-2.0（モデルカード確認） | 検索クエリ `検索クエリ: `・検索文書 `検索文書: ` の接頭辞（モデルカードで確認） |
| Pillow | 13.0.0（venv）／12.3.0（A20の素材を生成したシステムPython） | MIT-CMU（メタデータ確認） | A20の試験素材の生成のみ（テスト用、Skill配布物に含めない） |

「無償OSS優先」を非商用限定と読み替えていない。新規成果物（このSkill自体）のライセンスは、当初は指定が無く未確定だったが、のちに利用者がMITと指定したため `LICENSE`（MIT、Copyright (c) 2026 Mr-Kondo）を置いた（Skill配布物にも同じLICENSEを同梱）。モデル取得では、Xet転送がプロキシを通らなかったため `HF_HUB_DISABLE_XET=1` を使った。再現できる版は `requirements-lock.txt`。

## 4. 構成

| 場所 | 内容 |
|---|---|
| `skill/contextual-terminology-review/SKILL.md` `VERSION` | 入口（名前・説明・境界・手順・出力）。`VERSION`はSkill版 |
| `…/references/` | judgment・citation・feedback-loop・evaluation・hosts・review-example.json |
| `…/scripts/` | `ctr.py`（CLI）、`ctr_common`（原子的保存）、`ctr_refs`（登録簿・引用検査・出典生成）、`ctr_log`（記録・フィードバック・export/import・削除）、`ctr_improve`（更新案・比較・採用・復元・集計・抽出・回帰・未使用評価）、`ctr_blind`（匿名比較・理解問題）、`ctr_search`（一致検索・Ruri）、`ctr_pdf` |
| `tools/` | `ctr_install.py`（導入・更新・削除・照合・配布物）、`check_design_docs.py`、`run_acceptance.py`、`host_evidence.py`、`post_merge_cleanup.py`、`bench_search.py` |
| `tests/` | unittest 116件。A01〜A48 の機械検査。A20の図とPDFの素材 |
| `docs/` | USAGE・本メモ・ACCEPTANCE-REPORT（生成）・SEMANTIC-REVIEW-SHEET（生成）・HOST-EVIDENCE.json・evidence/ |

## 5. 主な判断と理由

- **既定の保存先を持たない／原文は既定で保存しない／共有は項目別許可が無ければ書き出さない**: 07の要件。許可なしで外へ出る経路を作らない。実測: 共有許可なしの export は終了コード4で停止（`tests/test_log.py`）。
- **共有書き出しは「名前付きの列挙値・ID・件数」だけを通す検証器**（ブラックリストではなくホワイトリスト）。取り込みも同じ検証器を使い、添付内の命令・未知のキーを拒否する。ハッシュは移送中の同一性であり認証ではない。
- **引用の一致は空白・改行だけ緩め、NFKCはしない**: `m/s²` が `m/s2` に化けて一致扱いになるのを防ぐため。省略引用は明示フラグと順序を要求。
- **機械検査と意味適合を別フィールドに分ける**: 意味適合は人の記録（`semantic_reviews`）がある場合だけ表示し、ツールは自動で埋めない。
- **更新案は自動採用しない**: 採用には人の名前・理由・`--i-approve`、同条件の比較、直前の版の一致が要る。意味保持の fail/unknown が1件でもあれば、読みやすさの平均に関係なくブロック。採用中に判断記録が書けなければ基準を巻き戻す。
- **索引は基準データ・資料のハッシュとの照合で古さを検出**: 一致しなければ検索せず `stale_index`。
- **導入スクリプトは既定が計画表示**、同名の識別できない既存・手編集は上書き・削除しない、更新は失敗時に旧版へ戻す。アカウント側（Work/Cowork）は操作しない。
- **A20の図**: 実際にPNGとPDFを生成し、PNGを開き、PDFはページ1を描画して開いて確認した。その確認で、最初の素材の凡例見本が実線で、「破線」の説明と矛盾していたため、凡例見本を破線に直した（目視確認で発見）。PDFは画像に不可視の文字層を重ねたもので、`text_origin: ocr` 扱い（視覚確認が無ければ確認済みにならない）。

## 6. 資料との差異・注意

- `manifest.json` の `local_links_checked: 36` と、`check_design_docs.py` が数えたローカルリンク数（20）は数え方が異なる（リンクの定義の違い）。破損リンクは無し。manifestのハッシュは全8点が現物と一致。
- 06が「現在すべて未実施」としている項目のうち、仮保存先・仮配置・実Ruri・実PDFで確認できたものだけを `ACCEPTANCE-REPORT.md` に反映した。実呼び出し・実務効果などは未実施のまま。
- 03の `must_not` の一部は語彙で近似できない（意味の判断）。語彙ガードは必要条件であり、意味審査は確認票で人が行う。

## 7. 未実施・残る問題

- **3環境の実呼び出し（2026-10-17、合成データの1プロンプトのみ）**: 利用者の許可を得て、実ユーザーのホームへ導入（`~/.claude/skills`・`~/.agents/skills`・`~/.gemini/config/skills`・`~/.gemini/antigravity-cli/skills`）し、Claude Code・Codex・Antigravity CLI で、スキル名を書かないプロンプトによる実モデルの呼び出しを確認した（`docs/evidence/real-host-*.md`）。Skillの自動選択、`check refs`、記録の保存と再読込、出典一覧の出力を観測。ただし1入力の結果で、品質・他入力・他モデルは示さない。
  - Codex: 既定モデル `gpt-6.1-sol` がChatGPTアカウントで未対応のため `-m gpt-6-sol` を指定した（利用者の設定は変更していない）。
  - Antigravity CLI: 1回目は権限拒否で回答が空。2回目は `--sandbox --dangerously-skip-permissions`（ターミナル制限付き・合成データの一時ディレクトリのみ）で成功。1・2回目の `json` 出力では `references/` の読込の直接ログが取れなかったが、`--output-format stream-json` の実行で `view_file` による読込を直接確認した（`docs/evidence/real-host-antigravity.md`）。モデルIDは出力に無いまま。
  - 書き出し・取り込み（export/import）は、Claude Code に加え Codex と Antigravity CLI でも、ホスト自身が実行して受理3・重複0・隔離0を確認した（同じ合成データの1プロンプト、共有許可は一時の保存先に設定した仮のもの。`docs/evidence/real-host-*.md` の追加の実呼び出し）。
  - 0.1.1へ更新した実ユーザー環境で、3ホストが記録から書き出し・取り込みまで再び成功した。Antigravityは `--model` 指定で `gemini-4-argon-medium` と記録でき、保存系コマンドが初回に `storage_unwritable` で拒否される挙動も観測した（`docs/evidence/real-host-*.md`）。v0.1.1のzipも一時ホームで確認した。
  - リリースv0.1.0のzipを取得し、展開物を一時ホームで実行・導入・検証・更新・削除した（`docs/evidence/release-zip-check.md`）。zipに導入ツールと `INSTALL-ON-REMOTE.txt` が入っていないことが分かった。
  - 未実施: Antigravity IDE/App、リモート、ChatGPT Work、Claude Cowork。
- 意味審査（A01〜A12, A17, A19, A20, A28, A29）は、作成者がAIで独立ではないため**未確定**。別モデル2つ（Codex gpt-6-sol、Antigravity gemini-4-argon-high）による確認で出力例と確認票の不備が見つかり直した（[docs/evidence/cross-model-semantic-review.md](evidence/cross-model-semantic-review.md)）が、人による独立審査の代わりにならない。指摘された「資料づくり」が資料の「成果物の作成」より範囲を狭め得る点は、版0.1.2で直し（Issue #5）、3回目の確認で両モデルとも解消を確認した。
- 匿名比較・理解問題の実際の評価者による採点、受け手の理解、本人の習得、実務での改善効果は未測定。性能の数値目標・週30分で確認できる件数は、初回試行後に提案する。
- Ruri検索（追記: 公開された実文章での確認を実施。Issue #6）: 日本語Wikipediaの実文章（150語・581課題、正解は機械的）で、70m・310mとも事前基準を満たした。合成データで70mが届かなかった主因は閾値の決め方とみられる。詳細は docs/RURI-ADOPTION.md の追記。自分のデータで回す手順は docs/RURI-REAL-DATA-GUIDE.md。以下は合成データでの経緯:
- Ruri検索: 架空の用語集40語・課題80件で一致検索・文字2-gram・Ruri 70m/310mを比較した（[docs/RURI-ADOPTION.md](RURI-ADOPTION.md)）。事前に固定した基準を、310mは満たし70m（既定）は満たさなかった。課題は作成者が作った独立でないもので、実データでの確認が残る。利用者の決定により既定モデルを310m（版固定）に変更した。この変更を含めてSkillの版を0.1.1にした（0.1.0からの違いは、Ruriの既定モデルと、その版固定のみ）。
- A31（マージ後の後片付け）は、マージ・公開が未実施のため未到達。

## 参照（確認箇所ごとに1行）

- ［Claude Code配置／直接確認］Anthropic公式 Skills｜Choose where skills load の表｜Personal `~/.claude/skills/<skill-name>/SKILL.md` は「Cowork or cloud sessions では読まれない」、Project `.claude/skills/`｜https://code.claude.com/docs/en/skills
- ［Codex配置／直接確認］OpenAI公式 Codex Skills｜Where Codex loads local skills｜REPO `$CWD/.agents/skills`、USER `$HOME/.agents/skills`、SKILL.mdに name と description が必須｜https://developers.openai.com/codex/skills
- ［Antigravity配置／直接確認］Google Antigravity Agent skills｜App/CLI/IDE skill locations｜workspace `.agents/skills`、IDE/App global `~/.gemini/config/skills`、CLI global `~/.gemini/antigravity-cli/skills`、frontmatterは description が必須・name 任意｜https://antigravity.google/docs/skills
- ［ChatGPT Work／確認のみ］OpenAI Skills & Plugins｜ページ全体｜Work側の登録・接続方法は本ページから特定できず、未確認として扱った｜https://learn.chatgpt.com/docs/skills-and-plugins
- ［Ruri／直接確認］Hugging Face モデルカード cl-nagoya/ruri-v3-70m｜使用例（1+3 prefix scheme）とLicense｜「検索クエリ: 」「検索文書: 」、Apache 2.0｜https://huggingface.co/cl-nagoya/ruri-v3-70m
- ［既存Skill／要約］japanese-readability-editor `tools/install.py`｜install_one・配置先表｜事前確認・退避・置換の設計を参考（コード非コピー）｜/Volumes/SSD/Programming/japanese-readability-editor/tools/install.py
- ［既存Skill／要約］official-prompt-tailor `SKILL.md` 手順2・3｜取得・読了・drift・recommendations.json｜本文ハッシュ・行範囲・短い原文の結び付け（コード非コピー）｜/Volumes/SSD/Programming/official-prompt-tailor/.claude/skills/official-prompt-tailor/SKILL.md
