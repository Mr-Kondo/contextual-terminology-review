"""Ruri採否判断用の課題セット(tools/data/ruri-adoption-set.json)の構造検査。結果の良し悪しではなく、採点が崩れないことを守る。"""
import json
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import bench_ruri_adoption as bra  # noqa: E402

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
