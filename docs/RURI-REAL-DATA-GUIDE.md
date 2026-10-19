# 自分のデータでRuri検索を確認する手順

[docs/RURI-ADOPTION.md](RURI-ADOPTION.md) の確認は、架空の用語集と公開された実文章（Wikipedia）で行った。**あなたの業務の用語・文章で成り立つかは別の話**で、ここは自分で回すための手順。データは手元の端末から出さない。リポジトリにも入れない（`.work/` や `~/` など、追跡されない場所に置く）。

## 1. 用意するもの

`tools/data/user-data-template.json`（架空の見本）をコピーして、中身を自分のデータに置き換える。

```json
{
  "description": "何のデータか（自分用のメモ）",
  "terms": [
    {"id": "t01", "term": "検収", "aliases": [], "sense": "納品物を確認して受け入れること",
     "source_id": "doc-01", "line": "根拠にする資料の一文（用語集の定義文など）"}
  ],
  "queries": [
    {"id": "ver01", "category": "verbatim",   "split": "dev",  "text": "来週、検収を行います。", "gold": ["t01"]},
    {"id": "var01", "category": "variant",    "split": "test", "text": "受入確認の日程を決めます。", "gold": ["t01"]},
    {"id": "par01", "category": "paraphrase", "split": "dev",  "text": "…名前を出さずに概念だけ言っている文…", "gold": ["t01"]},
    {"id": "neg01", "category": "negative",   "split": "test", "text": "用語集のどの語にも当たらない文", "gold": []}
  ]
}
```

- **terms**: 自分の用語集。`aliases` に登録済みの別名を入れる。入れた別名は一致検索で見つかるので、Ruriの評価には『登録していない言い方』をvariantに使う
- **queries** のカテゴリ:
  - `verbatim`: 用語（または登録済みの別名）がそのまま入っている文。一致検索で見つかるはずの対照
  - `variant`: 同じ意味を、登録していない表記・略称・英名・言い換え語で言っている文
  - `paraphrase`: 用語を出さずに、意味だけを説明している文
  - `negative`: 用語集のどの語も当てはまらない文。**用語に近い分野の文**を混ぜる（無関係な雑談だけだと閾値が甘くなる）
- **split**: `dev` は閾値を決めるためだけに使い、`test` が報告の主になる。**テストの結果を見てから課題やdev/testを入れ替えない**
- **gold**: 正解の用語の `id`（複数可）。`negative` は空。正解は、**このSkillの出力を見る前に**、人が付ける。可能なら、課題を書いた人と別の人が付ける

## 2. 件数の目安

| 項目 | 目安 | 理由 |
|---|---|---|
| test の variant + paraphrase | 30件以上 | 22件では95%区間が0.57〜0.90と広かった |
| dev の negative | 20件以上（閾値の規則 `max`）／50件以上（`p95`） | 件数が少ないと、1件の外れ値が閾値を決めてしまう |
| test の negative | 20件以上 | 誤検出率の見積り |

## 3. 実行

まず書式だけ検査する（モデルは使わない）。

```bash
python3 tools/bench_ruri_adoption.py --data ~/ctr-data/my-set.json --validate-only
```

次に比較を実行する（要 sentence-transformers。初回は ruri-v3-310m の重み約1.2GBの取得が必要）。

Windows（PowerShell）では、先に `$env:HF_HUB_DISABLE_XET = "1"` を実行し、`.venv/bin/python` を `.venv\Scripts\python` に読み替える。

```bash
HF_HUB_DISABLE_XET=1 .venv/bin/python tools/bench_ruri_adoption.py --data ~/ctr-data/my-set.json \
    --threshold-rule max --models 310m --out ~/ctr-data/my-result.json
```

- `--threshold-rule max`: devのnegativeの1位得点の最大値を閾値にする（negativeが少ないとき）。`p95` は95パーセンタイル（negativeが50件以上のとき）。**どちらを使うかは、結果を見る前に決める**
- 出力には課題の文面を含まない（IDと数値だけ）。ただし用語集の語が結果に出るので、共有するときは中身を確認する

## 4. 読み方

結果の `decision`（Ruriが基準を満たしたか）は、次の3つがすべて成り立つときだけ『任意の補助として推奨できる』になる。

- A: testの variant + paraphrase で、閾値つきの上位3件の命中率が 0.60 以上
- B: 文字2-gramより 0.15 以上高い
- C: testの negative の誤検出率が 0.20 以下

見るべきことは、命中率だけではない。

- **閾値なし**の命中率（上位3件を人に見せる使い方）と**閾値あり**の命中率（自動で絞る使い方）の差。差が大きいときは、閾値の決め方が合っていない
- 95%区間（`wilson_95`）。区間が基準をまたぐときは、点推定で満たしても『確かな合格』ではない
- 一致検索（`exact`）が拾えなかった課題を、Ruriがどれだけ拾ったか（variant・paraphrase の行）

## 5. 注意

- この比較は、Ruriを**使うかどうか**の判断材料で、Skillの判断が正しいことの証拠ではない
- 結果が基準を満たしても、Ruriは任意の補助のまま。Skillは一致検索を基本とし、Ruriの結果は『確認候補』として出す（得点は正しさの確率ではない）
- 個人情報・機密を含む文面は、評価者以外に見せない。課題を作る前に、扱ってよい範囲を確認する
