"""参照・引用の機械検査(A13〜A18, A26, A27 の機械側)。意味適合は別(test_semantic.py と人の確認票)。"""
import copy
import json
import unittest

from helpers import ACCEPT, FIXTURES, acceptance, case, make_cases

from ctr_refs import Location, Ref, Registry, Review, Source, check_ref, load_registry, normalize, quote_matches, review_check


def registry():
    return load_registry(ACCEPT)


def ref_from(spec, rid="r1"):
    return Ref(ref_id=rid, finding_ids=["F1"], source_id=spec["source_id"], version=spec["version"], mode=spec["mode"],
               location=Location(kind="lines", start=spec["start_line"], end=spec["end_line"]), quote=spec["quote"])


def minimal_review(refs, findings=None):
    f = findings or [{"id": "F1", "target": "t", "judgment": "confirmed", "professional_fit": "conformant",
                      "intent_clarity": "explicit", "business_premise": "agreed", "proposal_kind": "no_change",
                      "reason": "r", "ref_ids": [r.ref_id for r in refs]}]
    return Review.model_validate({"review_id": "x", "purpose": "p", "findings": f,
                                  "refs": [r.model_dump() for r in refs]})


class RefIntegrity(unittest.TestCase):
    def check_expected(self, cid):
        c = case(cid)
        spec = c["given"]["reference_to_check"]
        res = check_ref(ref_from(spec), registry())
        self.assertEqual(res["status"], "fail")
        for cls in c["given"]["expected_error_classes"]:
            self.assertIn(cls, res["errors"], cid)
        # 不備のある参照は断定の根拠に使えない: 確定判断は要確認へ下がり、出典行にも要確認が出る
        rep = review_check(minimal_review([ref_from(spec)]), registry())
        self.assertEqual(rep["findings"][0]["effective"], "needs_confirmation")
        self.assertIn("要確認", rep["footer"][0])
        self.assertIn("unsupported_confirmed_judgment", rep["error_classes"])


make_cases(RefIntegrity, ["A13", "A14", "A15", "A16", "A18"], "reference_integrity",
           lambda self, cid: RefIntegrity.check_expected(self, cid))


class MechanicalVsSemantic(unittest.TestCase):
    def test_A17_quote_matches_but_conclusion_is_not_supported(self):
        c = case("A17")
        res = check_ref(ref_from(c["given"]["reference_to_check"]), registry())
        self.assertEqual(res["status"], "pass")                    # 機械検査は合格
        self.assertTrue(c["given"]["mechanical_expected_valid"])
        rep = review_check(minimal_review([ref_from(c["given"]["reference_to_check"])]), registry())
        self.assertEqual(rep["refs"][0]["semantic"], "not_run")    # 意味適合は未審査のまま。機械合格で埋めない
        self.assertEqual(rep["refs"][0]["semantic_user_claim"], "not_run")


class QuoteRules(unittest.TestCase):
    def test_A18_negation_dropped_is_detected_and_no_fuzzy_match(self):
        reg = registry()
        r = Ref(ref_id="r1", finding_ids=["F1"], source_id="architecture", version="1", mode="direct_quote",
                location=Location(start=2, end=2), quote="サービスの開発と本番公開は本発注の成果物に含む。")
        self.assertEqual(check_ref(r, reg)["errors"], ["quote_mismatch"])

    def test_numbers_units_negations_not_normalized(self):
        self.assertFalse(quote_matches("単位はm/s2である", "単位はm/s²である", False))  # NFKCで² を 2 にしない
        self.assertFalse(quote_matches("含まない", "含む", False))
        self.assertTrue(quote_matches("単位は  m/s²である", "単位は m/s²である", False))     # 空白の幅だけは許容

    def test_newline_between_cjk_chars_is_joined_and_latin_gets_space(self):
        self.assertEqual(normalize("成果物\n一覧"), "成果物一覧")
        self.assertEqual(normalize("hello\nworld"), "hello world")
        self.assertEqual(normalize("全角　空白"), "全角 空白")

    def test_elision_requires_flag_and_order(self):
        orig = "担当者は論点の整理、関係者調整、成果物の作成を主担当として行う。"
        self.assertFalse(quote_matches("担当者は…主担当として行う。", orig, False))
        self.assertTrue(quote_matches("担当者は…主担当として行う。", orig, True))
        self.assertFalse(quote_matches("主担当として行う。…担当者は", orig, True))      # 順序が逆
        self.assertFalse(quote_matches("担当者は…最終承認", orig, True))

    def test_summary_recorded_as_direct_quote_is_rejected(self):
        r = Ref(ref_id="r1", finding_ids=["F1"], source_id="owner", version="1", mode="direct_quote",
                location=Location(start=1, end=2), quote="担当者が論点整理などを主担当で行い、承認は部長。")
        self.assertIn("quote_mismatch", check_ref(r, registry())["errors"])

    def test_summary_and_inference_modes_need_content_and_are_labelled(self):
        reg = registry()
        r = Ref(ref_id="r1", finding_ids=["F1"], source_id="owner", version="1", mode="summary", location=Location(start=1, end=1))
        self.assertEqual(check_ref(r, reg)["errors"], ["mode_content_missing"])
        r2 = r.model_copy(update={"used_content": "主担当の範囲を定める"})
        rep = review_check(minimal_review([r2]), reg)
        self.assertTrue(rep["footer"][0].startswith("［F1／要約］"))

    def test_strict_types_do_not_coerce(self):
        with self.assertRaises(Exception):
            Ref.model_validate({"ref_id": "r1", "finding_ids": ["F1"], "source_id": "owner", "version": 1,  # 版は文字列
                                "mode": "direct_quote", "location": {"start": "2"}})


class ReviewLevel(unittest.TestCase):
    def test_confirmed_without_basis_is_downgraded_and_footer_says_unconfirmed(self):
        rev = minimal_review([], findings=[{"id": "F1", "target": "t", "judgment": "confirmed", "professional_fit": "misuse_with_basis",
                                           "intent_clarity": "explicit", "business_premise": "agreed", "proposal_kind": "meaning_preserving_fix",
                                           "reason": "根拠なしの断定", "ref_ids": []}])
        rep = review_check(rev, registry())
        self.assertEqual(rep["findings"][0]["effective"], "needs_confirmation")
        self.assertEqual(rep["footer"], ["［F1／推論］参照元なし・未確認｜—｜—｜—"])

    def test_user_statement_is_labelled_and_does_not_confirm_professional_fit(self):
        r = Ref(ref_id="r1", finding_ids=["F1"], basis="user_statement", mode="summary", used_content="本人は主担当の意図と説明")
        rep = review_check(minimal_review([r]), registry())
        self.assertIn("本人の説明", rep["footer"][0])
        self.assertIn("外部資料で確認済みではない", rep["footer"][0])
        self.assertEqual(rep["findings"][0]["effective"], "needs_confirmation")
        self.assertIn("confirmed_on_user_statement_only", rep["findings"][0]["errors"])

    def test_footer_has_one_line_per_ref_and_same_location_ids_merge(self):
        good = {"source_id": "owner", "version": "1", "mode": "direct_quote", "start_line": 1, "end_line": 1,
                "quote": "担当者は論点の整理、関係者調整、成果物の作成を主担当として行う。"}
        r1, r2 = ref_from(good, "r1"), ref_from({**good, "start_line": 2, "end_line": 2, "quote": "最終承認は部長が行う。"}, "r2")
        rep = review_check(minimal_review([r1, r2]), registry())
        self.assertEqual(len(rep["footer"]), 2)
        self.assertIn("行1", rep["footer"][0])
        self.assertIn("行2", rep["footer"][1])
        self.assertEqual(rep["errors"], [])

    def test_body_footer_correspondence_mismatch_is_reported(self):
        r = ref_from({"source_id": "owner", "version": "1", "mode": "direct_quote", "start_line": 2, "end_line": 2,
                      "quote": "最終承認は部長が行う。"})
        rev = minimal_review([r])
        d = json.loads(rev.model_dump_json())
        d["findings"][0]["ref_ids"] = []                    # 本文側が参照を持たないのに、参照は指摘を指す
        rep = review_check(Review.model_validate(d), registry())
        self.assertIn("ref_finding_mismatch", rep["error_classes"])

    def test_A26_copies_do_not_count_as_independent_support(self):
        d = copy.deepcopy(acceptance()["source_catalog"])
        d.append({**next(s for s in d if s["id"] == "owner"), "id": "owner-copy", "copy_of": "owner", "relation": "copy",
                  "origin": "reprint"})
        reg = Registry([Source.model_validate(s) for s in d])
        q = "最終承認は部長が行う。"
        r1 = Ref(ref_id="r1", finding_ids=["F1"], source_id="owner", version="1", mode="direct_quote", location=Location(start=2, end=2), quote=q)
        r2 = r1.model_copy(update={"ref_id": "r2", "source_id": "owner-copy"})
        rep = review_check(minimal_review([r1, r2]), reg)
        self.assertEqual([x["mechanical"] for x in rep["refs"]], ["pass", "pass"])
        self.assertEqual(rep["independent_source_count"], 1)                      # 転載は1件分
        self.assertEqual(rep["independent_source_roots"], ["owner"])

    def test_A27_changed_source_is_flagged_for_recheck_not_judged_reversed(self):
        d = copy.deepcopy(acceptance()["source_catalog"])
        from ctr_refs import source_text_hash
        owner = Source.model_validate(next(s for s in d if s["id"] == "owner"))
        stamped = {**next(s for s in d if s["id"] == "owner"), "sha256": source_text_hash(owner)}
        changed = {**stamped, "lines": [stamped["lines"][0], "最終承認は担当者が行う。"]}   # 登録後に本文が変わった
        reg = Registry([Source.model_validate(changed)])
        r = Ref(ref_id="r1", finding_ids=["F1"], source_id="owner", version="1", mode="direct_quote", location=Location(start=1, end=1),
                quote=stamped["lines"][0])
        res = check_ref(r, reg)
        self.assertIn("source_hash_mismatch", res["errors"])       # 再確認候補。意味が反転したとは言わない
        self.assertEqual(res["status"], "fail")
        # 旧案件には旧版を適用できる: 版を分けた登録簿では旧版の参照が引き続き合格する
        reg2 = Registry([Source.model_validate(stamped), Source.model_validate({**changed, "version": "2", "sha256": None})])
        self.assertEqual(check_ref(r, reg2)["status"], "pass")

    def test_A20_visual_required_for_figure_and_ocr_sources(self):
        src = json.loads((FIXTURES / "figure1.source.json").read_text(encoding="utf-8"))
        reg = Registry([Source.model_validate(src)])
        loc = Location(kind="figure", page=1, figure="図1", region="右上の凡例")
        r = Ref(ref_id="r1", finding_ids=["F1"], source_id="figure-pdf", version="1", mode="direct_quote", location=loc, quote="破線：未承認")
        self.assertEqual(check_ref(r, reg), {"status": "needs_visual", "errors": ["visual_check_missing"]})   # 文字抽出だけでは確認済みにしない
        self.assertEqual(check_ref(r.model_copy(update={"visual_check": "agent_viewed"}), reg)["status"], "pass")
        bad = r.model_copy(update={"location": Location(kind="figure", page=1, figure="図9"), "visual_check": "agent_viewed"})
        self.assertEqual(check_ref(bad, reg)["errors"], ["location_out_of_range"])        # 存在しない図番号を補わない
        pg = r.model_copy(update={"location": Location(kind="pdf_page", page=2), "visual_check": "agent_viewed"})
        self.assertEqual(check_ref(pg, reg)["errors"], ["location_out_of_range"])


if __name__ == "__main__":
    unittest.main()
