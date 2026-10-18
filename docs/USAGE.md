# 用語・文脈レビュー(contextual-terminology-review)の使い方

Skill 本体は `skill/contextual-terminology-review/` にある。導入・更新・削除には `tools/ctr_install.py` を使う。依存は `requirements.txt` に書いてある。検証した版は `requirements-lock.txt` にある。

## 全体の流れ

1. 依存を入れ、保存先を決める。→ [SETUP.md](SETUP.md)
2. Skillを導入する。→ [INSTALL.md](INSTALL.md)
3. Agent に依頼する。→ このページの「初回の使い方」
4. 週に30分ほど、実例を確認して記録する。→ [WEEKLY.md](WEEKLY.md)
5. 検査を実行し、意味審査を依頼する。→ [CHECKS.md](CHECKS.md)

## 初回の使い方

### 依頼する

Agent に依頼する。Skillは自動で選ばれる。環境によっては、名前を指して明示的に呼び出すこともできる。

> 「私が取りまとめます」と会議で言うつもりです。役割は論点整理と調整と資料作成の主担当で、最終承認は部長です。資料は <パス>。用語として問題ないか、伝わるかを確認して。

### 自動で選ばれる割合

選ばれる割合は、Agent とモデルで違う。

- **Claude Code**
  - このSkillと推敲系だけを置いた条件では、使うべき依頼の約9割（既定モデル）で選ばれた。Opus は、v0.1.3 の1回測定で4分の3、v0.1.5 の3回測定で 35/36
  - 実際の利用環境（フック・CLAUDE.md・多数のSkillあり）では、v0.1.4 までは5〜7割だった。v0.1.5 では、新しい依頼文の束で約9割（33/36）だった。1回の測定で、測定のたびに揺れる
  - **Haiku では選ばれなかった**
- **Antigravity**: 実環境で全件選ばれた（v0.1.4・v0.1.5）
- **Codex**: Skillだけを置いた条件では全件選ばれた。**実際の利用環境（説明が一覧から除かれる設定など）では6〜7割**だった（v0.1.4 は 20/36、v0.1.5 は 26/36。差は揺れの範囲）

測定の方法と限界は、[TRIGGER-EVAL.md](TRIGGER-EVAL.md)にある。選ばれないときは、依頼文に Skill 名（`contextual-terminology-review`）を書いて呼ぶ。

### Agent の動き

Agent は、入力を確認したあと、次の順に進む。

1. `ctr.py record start`（保存先が設定済みのとき）
2. 資料読解
3. 判定
4. `ctr.py check refs`
5. 出典付きの返答
6. `record finish`

返答の末尾の出典一覧は、1参照1行である。検査を通った記録から生成される。`要確認` が付いた行は、断定の根拠に使われていない。

### 出典検査だけを試す

手元では、出典検査だけを試せる。

```bash
python3 skill/contextual-terminology-review/scripts/ctr.py check refs \
    --review skill/contextual-terminology-review/references/review-example.json --sources 03-acceptance-cases.json
```
