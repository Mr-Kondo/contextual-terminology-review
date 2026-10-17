# 発動精度の評価（descriptionが、使うべき依頼で選ばれるか）

Skillの中身がよくても、**依頼のときに選ばれなければ利用者に届かない**。Skillは `description` を手がかりに選ばれる（Anthropic の [Skill作成の指針](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) も、descriptionを選択の要としている）。このページは、その発動精度を測った手順と結果。

測定は Claude Code の `claude -p` だけ。Codex・Antigravity は未測定。**測るのは「選ばれたか」だけで、選ばれた後のレビューの質ではない**（質は [E2E評価](E2E-EVAL.md) と [効果測定](EFFECT-MEASUREMENT.md) の側）。

## 方法

- 評価セット `tools/data/trigger-eval.json`（72件）。使うべき依頼（肯定）と、近いが別の依頼（否定）が、dev・test・test2 に各12件ずつ。否定は、推敲・翻訳・コード・計算・書式・要約・生成・法務/設計レビュー・定義だけを尋ねる質問・無関係の質問。形式は skill-creator の `{query, should_trigger}` と互換。すべて架空の文面
- 実行 `tools/trigger_eval.py`: 依頼を1件ずつ新しいセッションに渡し、**最初に呼ばれた Skill** を記録して打ち切る（Skillの本文は実行しない）
- 競合: 利用者の環境にある `japanese-readability-editor` と `yomiyasu`（推敲系）を同居させた（`--skill-dir`）
- 基準（結果を見る前に固定）: **再現率 ≥ 0.75、誤発動率 ≤ 0.10**。`definition_qa`（用語の定義だけを尋ねる質問）は期待が割れるため `borderline` とし、基準に数えず別に報告
- dev は description を直してよい。test は直した後に1回だけ測る。**test を見て直したら、その test は使い終わりで、直した後に新しく書いた未使用のセット（test2）を1回だけ測る**

## 結果

| 条件 | 版 | 評価 | 再現率（95%区間） | 誤発動率 | 基準 |
|---|---|---|---|---|---|
| 実環境（フック等あり）、既定モデル | v0.1.2 | test、各3回 | **23/36 = 0.64**（0.48〜0.78） | 0/33 | **再現率が基準未満** |
| 実環境、既定モデル | v0.1.2 | dev、各2回 | 20/24 = 0.83 | 0/22 | 通過 |
| 作業ツリーの版だけ＋競合2つ、既定モデル | v0.1.2 | dev、各2回 | 21/24 = 0.88 | 0/22 | 通過 |
| 同上 | **v0.1.3** | dev、各2回 | 24/24 = 1.00 | 0/22 | 通過 |
| 同上 | v0.1.2 | **test2**、各3回 | 13/36 = 0.36（0.22〜0.52） | 0/30 | 再現率が基準未満 |
| 同上 | **v0.1.3** | **test2**、各3回 | **32/36 = 0.89**（0.75〜0.96） | 0/30 | **通過** |
| **実環境（フック・CLAUDE.md・他のSkillあり、導入後）**、既定モデル | v0.1.3 | test2、各3回 | **25/36 = 0.69**（0.53〜0.82） | 0/30 | **再現率が基準未満** |
| 同上、Opus | v0.1.3 | test2、各1回 | 9/12 = 0.75（0.47〜0.91） | 0/10 | 通過（件数が少ない） |
| 同上、Haiku | v0.1.3 | test2、各1回 | **0/12**（うち4件は japanese-readability-editor が選ばれた） | 0/10 | **再現率が基準未満** |

境界例（定義だけを尋ねる質問）は、どの測定でも発動しなかった（v0.1.2: test 0/3・test2 0/6、v0.1.3: test2 0/6）。

### 何が起きていたか

- v0.1.2 の取りこぼしは、別のSkillに取られたのではなく、**どのSkillも呼ばれなかった**（モデルが自力で答えた）。「この言葉の使い方は合っているか」「相手に伝わるか、言い直しがほしい」のような、**資料のない短い相談**に多かった。v0.1.2 の description は『資料に照らして』を前面に出していた
- v0.1.3 では、(1) 資料がなくても使うこと、(2) 依頼の言い回し（使い方の確認・使い分けの一貫性・役割/範囲/完了状態の曖昧さ・相手に伝わるかと言い直し）、(3) 使わない場合（定義だけの質問・コード/計算の検証・文体/書式だけの推敲・翻訳・要約）を、descriptionに書いた
- 推敲系の依頼は、競合の japanese-readability-editor に正しく流れた（dev の否定で3件）。取り合いではなく住み分けになっている

## 限界・注意

- **test は燃やした**。v0.1.2 の test の取りこぼしの傾向を見てから description を直したので、test は未使用のセットでなくなった。test2 は直した後に書いたが、**description の例（『障害とインシデント』）と同じ語を含む1件（T10）**がある。T10 を除くと v0.1.3 は 29/33 = 0.88、v0.1.2 は 13/33 = 0.39
- 評価セットの作成者は、Skillの設計者と同じAI（独立していない）。実際の利用者の言い回しは、これより多様なはず
- 各依頼3回（Opus・Haiku は1回）で、モデルの揺れがある。件数が少なく、区間は広い
- **実環境では、作業ツリーの版だけの条件より発動が減る**（0.69 対 0.89）。「作業ツリーの版だけ」の条件は、実環境のフック・CLAUDE.md・他のSkillを読まない。v0.1.3 を導入した後の再測定で、実環境の再現率は基準（0.75）に届かなかった。取りこぼしは別のSkillに取られたのではなく、どのSkillも呼ばれなかった（11/36）。利用者のフックやCLAUDE.mdが、Skillを使う前にモデル自身で答えさせる方向に働いている可能性があるが、原因は切り分けていない。**v0.1.3 の公開時の数値（0.89）は、実環境の数値ではない**
- Claude Code でのみ測った。Codex・Antigravity は、Skillの選び方が異なり、未測定
- **Haiku では自動では選ばれない**（test2 で0/12、dev で2/24。v0.1.2 は dev で0/24）。Haikuはどのスキルもほとんど呼ばず、呼んだときも推敲系に流れた。descriptionを足しても届かなかった。Haiku を使うときは、Skill名を書いて呼ぶ
- 選ばれた後の質（誤用を直せるか、正しい用法を直さないか、責務を作らないか）は、この評価では見ていない

## 再現

```bash
python3 tools/trigger_eval.py validate
# 実環境のSkillで測る（競合も実環境のまま）
python3 tools/trigger_eval.py run --split test2 --runs 3 --out .work/trigger.json
# 作業ツリーのSkillと競合だけで測る（実環境の設定は読まない）
python3 tools/trigger_eval.py run --split test2 --runs 3 --workers 4 \
    --skill-dir skill/contextual-terminology-review --skill-dir ~/.claude/skills/japanese-readability-editor \
    --out .work/trigger.json
python3 tools/trigger_eval.py score --results .work/trigger.json --split test2
```

生データ（IDと回数だけ。依頼文は含まない）は [docs/evidence/trigger-eval/](evidence/trigger-eval/)。

## 参考にしたもの

- Anthropic の Skill 作成の指針（descriptionの書き方、評価を先に作ること、複数モデルでの確認）
- skill-creator のトリガー評価（約20件の肯定/否定、再現率と誤発動）。利用者の `mece-cluster-advisor` の `evals/` に前例があり、同じ形式にそろえた
- Codex・Antigravity への独立した助言の依頼（Codex は『実際に選ばれる条件の確認』を提案。測定の基準と手順は提案に沿った）
