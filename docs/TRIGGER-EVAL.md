# 発動精度の評価（descriptionが、使うべき依頼で選ばれるか）

Skillの中身がよくても、**依頼のときに選ばれなければ利用者に届かない**。Skillは `description` を手がかりに選ばれる（Anthropic の [Skill作成の指針](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) も、descriptionを選択の要としている）。このページは、その発動精度を測った手順と結果。

測定は Claude Code の `claude -p` に加え、Codex（`codex exec`）と Antigravity（`agy -p`）でも行った（[Codex・Antigravity](#codex・antigravity-の測定issue-17)）。**測るのは「選ばれたか」だけで、選ばれた後のレビューの質ではない**（質は [E2E評価](E2E-EVAL.md) と [効果測定](EFFECT-MEASUREMENT.md) の側）。

## 方法

- 評価セット `tools/data/trigger-eval.json`（96件）。使うべき依頼（肯定）と、近いが別の依頼（否定）が、dev・test・test2・test3 に各12件ずつ。否定は、推敲・翻訳・コード・計算・書式・要約・生成・法務/設計レビュー・定義だけを尋ねる質問・無関係の質問。形式は skill-creator の `{query, should_trigger}` と互換。すべて架空の文面
- 実行 `tools/trigger_eval.py`: 依頼を1件ずつ新しいセッションに渡し、**最初に呼ばれた Skill** を記録して打ち切る（Skillの本文は実行しない）
- 競合: 利用者の環境にある `japanese-readability-editor` と `yomiyasu`（推敲系）を同居させた（`--skill-dir`）
- 基準（結果を見る前に固定）: **再現率 ≥ 0.75、誤発動率 ≤ 0.10**。`definition_qa`（用語の定義だけを尋ねる質問）は期待が割れるため `borderline` とし、基準に数えず別に報告
- dev は description を直してよい。test は直した後に1回だけ測る。**test を見て直したら、その test は使い終わりで、直した後に新しく書いた未使用のセット（test2、次は test3）を1回だけ測る**

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
| 実環境、スキル一覧の予算を 0.05 に上げて（`--settings`、設定ファイルは変えていない） | v0.1.3 | test2、各3回 | 19/36 = 0.53（0.37〜0.68） | 0/30 | 再現率が基準未満 |
| 同上、Opus | v0.1.3 | test2、各1回 | 9/12 = 0.75（0.47〜0.91） | 0/10 | 通過（件数が少ない） |
| 同上、Haiku | v0.1.3 | test2、各1回 | **0/12**（うち4件は japanese-readability-editor が選ばれた） | 0/10 | **再現率が基準未満** |

境界例（定義だけを尋ねる質問）は、どの測定でも発動しなかった（v0.1.2: test 0/3・test2 0/6、v0.1.3: test2 0/6）。

### 何が起きていたか

- v0.1.2 の取りこぼしは、別のSkillに取られたのではなく、**どのSkillも呼ばれなかった**（モデルが自力で答えた）。「この言葉の使い方は合っているか」「相手に伝わるか、言い直しがほしい」のような、**資料のない短い相談**に多かった。v0.1.2 の description は『資料に照らして』を前面に出していた
- v0.1.3 では、(1) 資料がなくても使うこと、(2) 依頼の言い回し（使い方の確認・使い分けの一貫性・役割/範囲/完了状態の曖昧さ・相手に伝わるかと言い直し）、(3) 使わない場合（定義だけの質問・コード/計算の検証・文体/書式だけの推敲・翻訳・要約）を、descriptionに書いた
- 推敲系の依頼は、競合の japanese-readability-editor に正しく流れた（dev の否定で3件）。取り合いではなく住み分けになっている

## 実環境の再測定と v0.1.5（Issue #21）

実環境（フック・CLAUDE.md・他のSkillあり、既定モデル）の再現率が、v0.1.3・v0.1.4 で基準（0.75）に届いていなかった。取りこぼしは別のSkillに取られたのではなく、どのSkillも呼ばれなかったもの。そこで、新しい未使用セット **test3**（肯定12・否定12、すべて架空。**現行版を測る前に書いてコミットした**）で、現行版（v0.1.4）と案を、同じ条件で比べた。

**変えたのは description の1文だけ**。「次のような依頼で使う」を「次のような依頼では、Skill名の指定がなくても、自分の知識だけで答える前にこのSkillを使う」にした。dev の現行版の取りこぼし（P09・P11）は、どちらも、モデルが自力で答えられそうな用語の確認だった。既存Skillの調査では、skill-creator は、Claude が Skill を使わなすぎる傾向があるので、description を少し強めに書くよう勧めている。`mece-cluster-advisor` は、明示がなくてもSkillを使うと書いている。この2点を取り入れた。

| 版 | 評価 | 再現率（95%区間） | 誤発動率 | 基準 |
|---|---|---|---|---|
| v0.1.4 | dev、各2回 | 21/24 = 0.88（0.69〜0.96） | 0/22 | 通過 |
| **v0.1.5** | dev、各2回 | 24/24 = 1.00（0.86〜1.00） | 0/22 | 通過 |
| v0.1.4 | **test3**、各3回 | 26/36 = 0.72（0.56〜0.84） | 0/30 | **再現率が基準未満** |
| **v0.1.5** | **test3**、各3回 | **33/36 = 0.92**（0.78〜0.97） | 0/30 | **通過** |

境界例（定義だけを尋ねる質問）は、どちらも 0/6 で発動しなかった。別のSkillに取られた回も、どちらも0件。

- 依頼ごとの発動回数（各3回）は、V09 が 0→3、V10 が 0→1、V02・V03 が 2→3、V11 が 1→2、そのほかは同じ。**V10（完了状態）と V11（役割の範囲）は、v0.1.5 でも取りこぼしが残る**（V10 は2回、V11 は1回）
- 同じ36回での差は +7回。フィッシャーの正確検定（片側）で p = 0.03。ただし、同じ依頼を3回ずつ測っているので、実際の不確かさはこれより大きい。区間も重なっている（0.78〜0.84）

### 限界

- **1回ずつの測定**で、2つの版は別の時刻に測った。この条件の測定は、同じ版でも揺れる（v0.1.3 の test2 は 0.53〜0.69）。0.92 が安定した値とは言えない
- **test3 は使い終わり**。結果を見た後に description は直していない。さらに直すなら、新しいセット（test4）を書く
- dev は description を直すときに見ているので、dev の値は参考にとどまる
- 評価セットの作成者は、Skillの設計者と同じAI。実際の利用者の言い回しは、これより多様なはず
- 『自分の知識だけで答える前に使う』は、定義だけの質問などを選びやすくするおそれがあった。測った範囲では誤発動は 0/30、境界例は 0/6 で、増えなかった
- **Codex・Antigravity・Haiku・Opus は v0.1.5 で測り直していない**。Codex の実環境（0.56）は、説明が一覧から除かれるのが原因らしく、Skill側では直せないと見ている

## Codex・Antigravity の測定（Issue #17）

同じ test2（24件×各3回）を、導入済みの v0.1.4 で測った。**発動の判定は各ホストで異なる**: Claude は `Skill` ツールの呼び出し、Codex は `skills/<名前>/SKILL.md` を読むコマンド、Antigravity は `view_file` で `SKILL.md` を開いたこと。最初に読まれたSkillを記録して打ち切る点は同じ。モデルは各CLIの既定（Codex は `gpt-6-sol`、Antigravity は `gemini-4-argon-medium`）。

| ホスト・条件 | 再現率（95%区間） | 誤発動率 | 基準 |
|---|---|---|---|
| **Antigravity**、実環境（隔離不可） | **36/36 = 1.00**（0.90〜1.00） | 0/30 | 通過 |
| **Codex**、隔離（偽HOME。作業ツリーのSkill＋競合2つだけ。設定・規則・記憶を読まない） | **36/36 = 1.00**（0.90〜1.00） | 0/30 | 通過 |
| **Codex**、実環境（利用者の設定・記憶・他のSkillあり） | 20/36 = 0.56（0.40〜0.70） | 0/30 | **再現率が基準未満** |
| Codex、実環境、記憶だけ無効（`--disable memories`） | 23/36 = 0.64（0.48〜0.78） | 0/30 | 再現率が基準未満 |

境界例（定義だけの質問）は、どの条件でも発動しなかった（0/6）。取りこぼしは、別のSkillに取られたのではなく**どのSkillも読まれなかった**もの（Codex 実環境で 15/16、残り1件は japanese-readability-editor）。Codex 実環境では、T02・T03・T06 が3回とも読まれなかった。

- **Codex の実環境で下がる理由は、切り分けていない**。この環境の Codex は、スキル一覧の予算超過でSkillの説明が除かれる。隔離（1.00）との差は、この除去と、利用者の設定・規則・他のSkillの合算で、どれがどれだけかは分からない。記憶を無効にしても 0.56 → 0.64 で、区間が重なる。記憶の汚染が主因ではなさそう、というところまで
- **Antigravity は隔離できない**（偽のHOMEにすると認証が通らない）。1.00 は、利用者の実環境での値で、競合するSkillの有無は統制していない。推敲系の依頼が japanese-readability-editor に流れたのは否定側の1件だけ（想定どおりの住み分け）
- Codex の隔離では、否定の推敲系の依頼 9 件が japanese-readability-editor に流れた（想定どおり）。Claude の測定（0.89）より Codex・Antigravity の方が選ばれやすい
- **1.00 は上限に張り付いている**。24件×3回で、区間の下限は 0.90。description の良し悪しの差を測るには易しすぎる可能性がある（test2 は v0.1.3 の description を直した後に書いたが、description の例と同じ語を含む T10 がある。T10 を除いても Codex 隔離・Antigravity は全て発動）
- 各ホストでモデル1つ、依頼3回。小さいモデル（Claude の Haiku のように）では別の結果になりうる

## 限界・注意

- **test は燃やした**。v0.1.2 の test の取りこぼしの傾向を見てから description を直したので、test は未使用のセットでなくなった。test2 は直した後に書いたが、**description の例（『障害とインシデント』）と同じ語を含む1件（T10）**がある。T10 を除くと v0.1.3 は 29/33 = 0.88、v0.1.2 は 13/33 = 0.39
- 評価セットの作成者は、Skillの設計者と同じAI（独立していない）。実際の利用者の言い回しは、これより多様なはず
- 各依頼3回（Opus・Haiku は1回）で、モデルの揺れがある。件数が少なく、区間は広い
- **実環境では、作業ツリーの版だけの条件より発動が減る**（0.69 対 0.89）。「作業ツリーの版だけ」の条件は、実環境のフック・CLAUDE.md・他のSkillを読まない。v0.1.3 を導入した後の再測定で、実環境の再現率は基準（0.75）に届かなかった。取りこぼしは別のSkillに取られたのではなく、どのSkillも呼ばれなかった（11/36）。実環境のデバッグログには `Skill listing over budget: 84 skills, 44454 chars > 30000 budget — descriptions will be truncated` が出ており、一覧の予算超過で説明が削られている可能性があった。そこで予算を上げて測ったが、再現率は上がらなかった（0.53）。実環境の測定は、同じ条件でも 0.53〜0.69 と揺れる（区間が重なる）。利用者のフック・CLAUDE.md・他のプラグインのSkillの影響もありうるが、**原因は切り分けていない**。**v0.1.3 の公開時の数値（0.89）は、実環境の数値ではない**（v0.1.5 の再測定は[上の節](#実環境の再測定と-v015issue-21)）
- Codex・Antigravity は下の節で別に測った。モデルが違えば選び方も違い、Claude Code の数値は当てはまらない
- **Haiku では自動では選ばれない**（test2 で0/12、dev で2/24。v0.1.2 は dev で0/24）。Haikuはどのスキルもほとんど呼ばず、呼んだときも推敲系に流れた。descriptionを足しても届かなかった。Haiku を使うときは、Skill名を書いて呼ぶ
- 選ばれた後の質（誤用を直せるか、正しい用法を直さないか、責務を作らないか）は、この評価では見ていない

## 再現

```bash
python3 tools/trigger_eval.py validate
# 実環境のSkillで測る（競合も実環境のまま）
python3 tools/trigger_eval.py run --split test3 --runs 3 --out .work/trigger.json
# 作業ツリーのSkillと競合だけで測る（実環境の設定は読まない）
python3 tools/trigger_eval.py run --split test2 --runs 3 --workers 4 \
    --skill-dir skill/contextual-terminology-review --skill-dir ~/.claude/skills/japanese-readability-editor \
    --out .work/trigger.json
python3 tools/trigger_eval.py score --results .work/trigger.json --split test2

# Codex（実環境 / 隔離）と Antigravity（実環境のみ）
python3 tools/trigger_eval.py run --split test2 --runs 3 --host codex --out .work/trigger-codex.json
python3 tools/trigger_eval.py run --split test2 --runs 3 --host codex --skill-dir skill/contextual-terminology-review \
    --skill-dir ~/.claude/skills/japanese-readability-editor --out .work/trigger-codex-iso.json
python3 tools/trigger_eval.py run --split test2 --runs 3 --host agy --out .work/trigger-agy.json
```

生データ（IDと回数だけ。依頼文は含まない）は [docs/evidence/trigger-eval/](evidence/trigger-eval/)。

## 参考にしたもの

- Anthropic の Skill 作成の指針（descriptionの書き方、評価を先に作ること、複数モデルでの確認）
- skill-creator のトリガー評価（約20件の肯定/否定、再現率と誤発動）。利用者の `mece-cluster-advisor` の `evals/` に前例があり、同じ形式にそろえた
- Codex・Antigravity への独立した助言の依頼（Codex は『実際に選ばれる条件の確認』を提案。測定の基準と手順は提案に沿った）
