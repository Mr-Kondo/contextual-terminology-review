"""意味判断ケースの出力例に対する機械側の検査。

これは意味の合否判定ではない。確認するのは、スキーマ・参照の機械検査・禁止変更の語彙ガード(必要条件のみ)・
ケースごとの構造上の期待。意味保持・適用条件の審査は、tools/semantic_sheet.py の確認票で独立した人が行う。
"""
import json
import unittest

from helpers import ACCEPT, FIXTURES, HAS_PDFPLUMBER, case, make_cases
from semantic_fixtures import CASES

from ctr_refs import Registry, Review, Source, load_registry, review_check


def registry_for(c):
    reg = load_registry(ACCEPT)
    src = [s for ids in reg.by_id.values() for s in ids.values()]
    if c.get("needs_figure"):
        src.append(Source.model_validate(json.loads((FIXTURES / "figure1.source.json").read_text(encoding="utf-8"))))
    return Registry(src)


def texts(c):
    out = []
    for f in c["review"]["findings"]:
        out += [f.get("proposal_text") or "", f.get("oral_rephrase") or ""]
    out += list(c.get("variants", {}).values())
    return out


class SemanticGuards(unittest.TestCase):
    def check(self, cid):
        c = CASES[cid]
        spec = case(cid)
        review = Review.model_validate(c["review"])
        rep = review_check(review, registry_for(c))
        self.assertEqual(rep["errors"], [], f"{cid}: {rep['errors']}")
        passed = sum(1 for r in rep["refs"] if r["mechanical"] == "pass")
        exp = c["expect"]
        if "refs_pass" in exp:
            self.assertEqual(passed, exp["refs_pass"])
        if exp.get("no_refs"):
            self.assertEqual(review.refs, [])                                 # 位置・引用を作らない
            self.assertTrue(all("参照元なし・未確認" in line for line in rep["footer"]))
        f = review.findings[0]
        if "premise" in exp:
            self.assertEqual(f.business_premise, exp["premise"])
        if "kind" in exp:
            self.assertEqual(f.proposal_kind, exp["kind"])
            self.assertIsNone(f.proposal_text)                                 # 修正不要なら無理に直さない
        if "fit" in exp:
            self.assertEqual(f.professional_fit, exp["fit"])
        if exp.get("has_correction"):
            self.assertIsNotNone(f.correction)
            self.assertEqual(f.correction.unrelated_additions, [])
        body = "\n".join(texts(c))
        for bad in c.get("forbid", []):
            self.assertNotIn(bad, body, f"{cid}: 禁止変更の語彙 {bad!r}")
        for need in c.get("require", []):
            self.assertIn(need, body)
        # ケース定義(03)の must_not と照合できるよう、期待を取り出して存在を確認する(内容の判定は人)
        self.assertTrue(spec["expected"]["must"] and spec["expected"]["must_not"] is not None)
        # 作成者(AI)による意味の自己確認は、独立確認の代わりにならない
        self.assertFalse(any(s.independent for s in review.semantic_reviews))


make_cases(SemanticGuards, ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11", "A12", "A17", "A19", "A28"],
           "mechanical_guards", lambda self, cid: SemanticGuards.check(self, cid))


class FigureAndAudience(unittest.TestCase):
    def test_A20_real_figure_requires_visual_record_and_separates_quote_from_inference(self):
        c = CASES["A20"]
        review = Review.model_validate(c["review"])
        rep = review_check(review, registry_for(c))
        self.assertEqual(rep["errors"], [])
        self.assertEqual([r["mechanical"] for r in rep["refs"]], ["pass", "pass"])
        modes = {r.ref_id: r.mode for r in review.refs}
        self.assertEqual(modes, {"r1": "direct_quote", "r2": "inference"})   # 図中の文字の引用と、視覚的な読み取りの推論を分ける
        self.assertTrue(all("PDF p.1" in line and "図1" in line for line in rep["footer"]))
        self.assertIn("右上の凡例", rep["footer"][0])
        # 視覚確認の記録を外すと、文字抽出が一致していても確認済みにならない
        d = json.loads(review.model_dump_json())
        for r in d["refs"]:
            r["visual_check"] = "not_run"
        rep2 = review_check(Review.model_validate(d), registry_for(c))
        self.assertEqual([r["mechanical"] for r in rep2["refs"]], ["needs_visual", "needs_visual"])
        self.assertEqual(rep2["findings"][0]["effective"], "needs_confirmation")

    @unittest.skipUnless(HAS_PDFPLUMBER, "pdfplumber 未導入: PDFの実抽出は未実施")
    def test_A20_pdf_text_extraction_matches_registered_source(self):
        import ctr_pdf
        got = ctr_pdf.extract_pdf(FIXTURES / "figure1.pdf", "figure-pdf", "1", "t")
        reg = json.loads((FIXTURES / "figure1.source.json").read_text(encoding="utf-8"))
        self.assertEqual(got["pages"], 1)
        self.assertEqual(got["page_text"], reg["page_text"])
        self.assertIn("破線：未承認", got["page_text"]["1"])

    def test_A29_audience_adaptation_keeps_facts_common(self):
        c = CASES["A29"]
        rep = review_check(Review.model_validate(c["review"]), registry_for(c))
        self.assertEqual(rep["errors"], [])
        colleague, other = c["variants"]["同僚"], c["variants"]["他職種"]
        self.assertGreater(len(other), len(colleague))                         # 補足量は相手で変わってよい
        for v in (colleague, other):
            self.assertIn("主担当", v)
            self.assertIn("部長", v)
            for bad in c["forbid"]:
                self.assertNotIn(bad, v)


if __name__ == "__main__":
    unittest.main()
