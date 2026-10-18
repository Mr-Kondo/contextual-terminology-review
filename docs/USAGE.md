# 用語・文脈レビュー(contextual-terminology-review)の使い方

Skill 本体は `skill/contextual-terminology-review/`。導入・更新・削除は `tools/ctr_install.py`。依存は `requirements.txt`（検証した版は `requirements-lock.txt`）。

## 0. 前提と保存先の決め方（最初に一度）

1. 依存を入れる。システムのPythonに入れるか、仮想環境を作る。
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
   `pydantic` だけでも、レビュー・出典検査・記録は使える。PDF抽出は `pdfplumber`、Ruri検索は `sentence-transformers`。
2. 保存先を**あなたが決める**。このSkillは既定の保存先を持たない。決めること:
   - `runtime_data_root`: この実行先の記録の置き場（案件で保存を許可された永続領域の絶対パス）
   - `improvement_root`: 許可済み記録の取り込み・更新案・基準データの置き場（本人または承認された管理者）
   - `evaluation_gold_root`: 評価用の正解・未使用例。レビューを生成・改善するAgentから**アクセスできない**場所
   - 原文を保存してよいか（既定は不可）、共有してよい項目、共有範囲、保存期限
   Skillのフォルダ、公開リポジトリ、自動同期されるフォルダを業務ログの置き場にしない。
3. 初期化する。
   ```bash
   python3 skill/contextual-terminology-review/scripts/ctr.py store init --runtime-root /abs/path/runtime
   ```
   `policy.json` が作られる（原文保存=不可、共有=未設定）。許可したときだけ変更する:
   ```bash
   ctr.py store set-policy --runtime-root /abs/path/runtime --raw-text allow
   ctr.py store set-policy --runtime-root /abs/path/runtime --share-fields run_status,versions,problem_axes \
       --share-scope "<共有範囲>" --granted-by "<許可者>"
   ```
   共有できる項目: `run_status, environment, versions, domains, problem_axes, machine_checks, human_feedback, project_opaque_id, effort`。

## 1. 導入・更新・アンインストール（`tools/ctr_install.py`）

既定は**計画の表示だけ**。操作・配置先・変更点を確認してから `--apply` を付ける。

| 環境 | user（ホーム） | workspace（プロジェクト） | 公式資料での確認（2026-10-17） |
|---|---|---|---|
| Claude Code | `~/.claude/skills/` | `.claude/skills/` | code.claude.com/docs/en/skills |
| Codex | `~/.agents/skills/` | `.agents/skills/` | developers.openai.com/codex/skills |
| Antigravity IDE/App | `~/.gemini/config/skills/` | `.agents/skills/` | antigravity.google/docs/skills |
| Antigravity CLI | `~/.gemini/antigravity-cli/skills/` | `.agents/skills/` | 同上 |

```bash
python3 tools/ctr_install.py install   --target claude-code --scope user            # 計画の表示（変更なし）
python3 tools/ctr_install.py install   --target claude-code --scope user --apply
python3 tools/ctr_install.py update    --target all --scope user --apply            # all = claude-code, codex, antigravity-ide, antigravity-cli
python3 tools/ctr_install.py verify    --target codex --scope user                  # 正本との照合
python3 tools/ctr_install.py uninstall --target antigravity --scope user --apply    # このSkillのフォルダだけを削除
```

- 配置したSkillには `.ctr-install.json`（版と全ファイルのsha256）が付く。これが無い同名のものは「識別できない既存」として上書き・削除しない（`--on-conflict backup` で退避してから置換）。導入後に手で編集したファイルがある場合も同様。
- 更新は、新版を一時領域に作る → 旧版を `skills.bak/` へ退避 → 置換 → 照合。途中で失敗したら旧版に戻る。更新後は、用語データ・索引の版を `ctr.py check data --improvement-root ABS [--index-meta PATH]` で確認する（索引が古ければ作り直す）。
- アンインストールは当該Skillのフォルダだけを消す。原資料・用語正本・評価履歴・ログ・他のSkillには触れない（これらはSkillフォルダの外に置く設計）。データの削除は別操作（`ctr.py delete plan/apply`）。
- 他のホームや別の作業領域を試すには `--home DIR` / `--workspace DIR` / `--dest DIR`。リモートでは、対象ホストで同じスクリプトを実行する。`package` で配布物を作れる:
  ```bash
  python3 tools/ctr_install.py package --out dist/     # zip と INSTALL-ON-REMOTE.txt（再現できるzip）
  ```

### ChatGPT Work / Claude Cowork（アカウント側）

ローカルスクリプトでは**操作できない**。`package` が作る zip を、各サービスのSkill登録の手順に従って利用者が登録する。Claude の公式説明では、Coworkは `~/.claude/skills/` を直接読まず、アカウントで有効なSkillを読み込む。ローカル配置だけで導入完了にしない。登録後に、呼び出し・資料参照・スクリプト実行（実行できるか）・保存を観測し、`docs/HOST-EVIDENCE.json` に成功・失敗・未実施を記録する。スクリプトを実行できない環境では、`references/hosts.md` の手動記録の経路を使う。

## 2. 初回の使い方

Agent に依頼する（Skillが自動選択される。環境により明示的な呼び出しも可）。

自動で選ばれるかは、Agent のモデルで違う。Claude Code では、このSkillと推敲系だけを置いた条件で使うべき依頼の約9割（既定モデル）・4分の3（Opus）、実際の利用環境（フック・CLAUDE.md・多数のSkillあり）では5〜7割（測定のたびに揺れる）で選ばれ、**Haiku では選ばれなかった**。Antigravity は実環境で全件選ばれた。Codex は、Skillだけを置いた条件では全件選ばれたが、**実際の利用環境（説明が一覧から除かれる設定など）では約6割**だった（[docs/TRIGGER-EVAL.md](TRIGGER-EVAL.md)）。選ばれないときは、依頼文に Skill 名（`contextual-terminology-review`）を書いて呼ぶ。

> 「私が取りまとめます」と会議で言うつもりです。役割は論点整理と調整と資料作成の主担当で、最終承認は部長です。資料は <パス>。用語として問題ないか、伝わるかを確認して。

Agent は、入力を確認し、`ctr.py record start`（保存先が設定済みなら）→ 資料読解 → 判定 → `ctr.py check refs` → 出典付きの返答 → `record finish` を行う。返答の末尾の出典一覧は1参照1行で、検査を通った記録から生成される。`要確認` が付いた行は断定の根拠に使われていない。

手元で出典検査だけを試す:
```bash
python3 skill/contextual-terminology-review/scripts/ctr.py check refs \
    --review skill/contextual-terminology-review/references/review-example.json --sources 03-acceptance-cases.json
```

## 3. 週次の手順（本人の時間は合計30分程度、初期設定・日々の入力を含む）

| 時間 | やること | コマンド |
|---|---|---|
| 5分 | 当週の実例を選び、原文・意図・相手・場面を記録 | （日々は `feedback add` の4項目だけでもよい） |
| 15分 | 根拠を読み、判断可能な範囲と正解を確認 | `check sample`（指摘なし例を含む確認候補） |
| 5分 | AIの指摘・修正案と照合し、フィードバックを残す | `feedback add --validity ... --intent ... --usage ... --receiver ...` |
| 5分 | AIなしで言い直し、更新候補を残す | `propose create --spec spec.json` |

時間は `ctr.py feedback time --category setup|record|evidence|compare|practice --minutes N --who self|collaborator` で記録する。固定件数や全分野を毎週こなす必要はない。超えたら確認数を減らして保留を残す。集計は `ctr.py evaluate metrics --runtime-root ... --improvement-root ...`（分母0は未評価、利用総数が未知なら収集率は出ない）。

### 別PC・他の利用者・リモートの記録を集める（ファイル方式）

```bash
ctr.py export --runtime-root ABS_ON_THAT_HOST            # 共有許可が設定済みのときだけ。outbox/<package_id>/ ができる
ctr.py import /path/to/package --improvement-root ABS     # 一時領域で検査してから確定
```
自動送信・常駐・定期実行は設定しない。パッケージのハッシュは移送中の同一性の検査で、送信者の認証や内容の正しさではない。

### 更新案の採用（明示的な人の判断のみ）

`propose create` → `evaluate compare`（同条件の新旧比較）→ 人が確認 → `evaluate adopt --approved-by ... --reason ... --i-approve`。評価後に基準が変わったら競合として止まる。悪化したら `evaluate restore`。AIの採点や提案を採用承認として扱わない。

## 4. 検査の実行

```bash
python3 -m unittest discover -s tests                 # 標準ライブラリのみ。未導入の依存に当たるテストは skip（未実施）
python3 tools/check_design_docs.py                     # 設計資料の整合性（資料の検査）
python3 tools/run_acceptance.py                        # A01〜A48 の機械検査と docs/ACCEPTANCE-REPORT.md の生成
# Ruri実検索込み（既定は ruri-v3-310m。重みは約1.2GBで、初回取得にネットワークが必要。Xet転送がプロキシを通らない環境では HF_HUB_DISABLE_XET=1）
HF_HUB_DISABLE_XET=1 .venv/bin/python tools/bench_search.py --out docs/evidence/search-bench.json
CTR_RUN_RURI=1 .venv/bin/python -m unittest discover -s tests
```

## 5. 意味審査の依頼

`docs/SEMANTIC-REVIEW-SHEET.md` が、独立した確認者向けの票（A01〜A12, A17, A19, A20, A28, A29）。機械検査の合格は意味保持の合格ではない。確認者の判断・理由・日付を票に記入し、保留は保留のまま残す。この票の結果が出るまで、意味の合否は「未実施」。
