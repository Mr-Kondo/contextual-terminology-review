"""Ruri採否判断用の課題セット(tools/data/ruri-adoption-set.json)の構造検査。結果の良し悪しではなく、採点が崩れないことを守る。"""
import json
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import bench_ruri_adoption as bra  # noqa: E402
import fetch_wiki_bench  # noqa: E402,F401

sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))
import ctr_search as se  # noqa: E402


class RuriBenchSet(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(bra.DATA.read_text(encoding="utf-8"))
        self.terms = {"terms": [{"id": t["id"], "term": t["term"], "aliases": t["aliases"], "scope": {"kind": "professional"}} for t in self.data["terms"]]}

    def test_ids_are_unique_and_counts_are_as_registered(self):                 # 初回の実行で接頭辞の衝突があった
        qs = self.data["queries"]
        self.assertEqual(len({q["id"] for q in qs}), len(qs))
        from collections import Counter
        c = Counter((q["category"], q["split"]) for q in qs)
        want = {"verbatim": 8, "variant": 10, "paraphrase": 12, "negative": 10}
        self.assertEqual(c, Counter({(cat, sp): n for cat, n in want.items() for sp in ("dev", "test")}))

    def test_gold_ids_exist_and_negatives_have_none(self):
        ids = {t["id"] for t in self.data["terms"]}
        for q in self.data["queries"]:
            self.assertEqual(bool(q["gold"]), q["category"] != "negative", q["id"])
            self.assertTrue(set(q["gold"]) <= ids, q["id"])

    def test_categories_mean_what_they_say_for_exact_search(self):
        for q in self.data["queries"]:
            hit = {h["term_id"] for h in se.exact_search(self.terms, q["text"])["hits"]}
            if q["category"] == "verbatim":
                self.assertTrue(hit & set(q["gold"]), q["id"])                   # 語がそのまま入っている
            else:
                self.assertFalse(hit & set(q["gold"]), q["id"])                  # variant/paraphrase は正解の語が一致検索では見つからない
                if q["category"] == "negative":
                    self.assertFalse(hit, q["id"])                                # 無関係な文には何も一致しない

    def test_bigram_baseline_runs_without_extra_dependencies(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            terms, reg = bra.terms_and_registry(self.data, Path(td))
            r = bra.Bigram(terms, reg).search("同じ請求が二重に来ても結果が変わらない")
            self.assertEqual(len(r), 5)
            self.assertTrue(all(0 <= s <= 1.0001 for _, s in r))


if __name__ == "__main__":
    unittest.main()


class BenchKit(unittest.TestCase):
    """自分のデータで回すキット(--data)と、Wikipediaから課題セットを作る取得スクリプトの、通信を使わない部分の検査。"""

    def test_user_data_template_is_valid_and_validation_catches_broken_data(self):
        tmpl = json.loads((ROOT / "tools" / "data" / "user-data-template.json").read_text(encoding="utf-8"))
        self.assertEqual(bra.validate_dataset(tmpl), [])
        bad = json.loads(json.dumps(tmpl))
        bad["queries"][1]["id"] = bad["queries"][0]["id"]                       # id重複
        bad["queries"][2]["gold"] = ["tXX"]                                      # 無い用語
        bad["queries"][6]["gold"] = ["t01"]                                      # negative に正解
        bad["queries"][3]["split"] = "train"                                     # 不正な split
        text = " ".join(bra.validate_dataset(bad))
        for needle in ("重複", "gold", "negative", "split"):
            self.assertIn(needle, text)
        no_neg = json.loads(json.dumps(tmpl))
        no_neg["queries"] = [q for q in no_neg["queries"] if q["category"] != "negative"]
        self.assertTrue(any("negative が無い" in p for p in bra.validate_dataset(no_neg)))

    def test_threshold_rules(self):
        qs = [{"id": f"n{i}", "category": "negative", "split": "dev"} for i in range(20)]
        ranked = {f"n{i}": [("t", i / 100)] for i in range(20)}                  # 0.00〜0.19
        self.assertEqual(bra.threshold_from_dev(ranked, qs, "max"), 0.19)
        self.assertEqual(bra.threshold_from_dev(ranked, qs, "p95"), 0.18)        # 上位5%(1件)を外れ値として許す
        self.assertEqual(bra.threshold_from_dev({}, [], "p95"), 0.0)

    def test_wiki_fetcher_builds_a_valid_dataset_from_a_fake_page_without_network(self):
        import fetch_wiki_bench as fw
        extract = ("リファクタリングとは、プログラムの外部から見た動作を変えずに内部構造を整理することである。保守性を高める目的で行う。\n\n\n== 概要 ==\n"
                   "リファクタリングは小さな変更を繰り返して進める作業であり、一度に大きく変えない。テストが整っていると、変更を安全に繰り返し行うことができる。"
                   "変更の前後で外から見た動作が同じであることを確かめながら進めるのが基本である。"
                   "重複した処理を一か所にまとめて、読みやすい形に整えることもある。" + "あ" * 300)
        item = fw.build_item("リファクタリング (プログラミング)", extract, ["リファクタ", "リファクタリング技法", "Refactoring"])
        self.assertEqual(item["title"], "リファクタリング")                      # 括弧書きは除く
        self.assertIn("リファクタリング", item["verbatim"])
        self.assertNotIn("リファクタリング", item["paraphrase"])
        self.assertEqual(item["variants"], ["Refactoring"])                      # 項目名を含む『リファクタリング技法』・項目名に含まれる『リファクタ』は除く
        self.assertIsNone(fw.build_item("曖昧", "曖昧。\n\n\n== x ==\n" + "あ。" * 50, []))   # 第1文が短い(曖昧さ回避など)
        data = fw.build_dataset([item], ["会議室の予約を変更したという、近い分野の別の話の文である。", "リファクタリングを含む文は、否定の課題から外れる。"])
        self.assertEqual(bra.validate_dataset(data) if any(q["split"] == "dev" and q["category"] == "negative" for q in data["queries"]) else [], [])
        self.assertEqual(sum(1 for q in data["queries"] if q["category"] == "negative"), 1)   # 用語を含む否定は除かれる
