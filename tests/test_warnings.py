"""check refs の警告(エラーにしない確認候補)の検査: 修正案が足した責務語、引用の近くの適用条件。"""
import unittest

from helpers import ROOT  # noqa: F401  (sys.path の設定)

from ctr_refs import Registry, Review, Source, review_check

LINES = ["【草案】役割分担", "取りまとめ: 田中が論点整理と資料作成を行う。", "ただし、旧案件には適用しない。", "別の段落。", "さらに別の段落。", "もう一つ。"]


def reg(lines=LINES):
    return Registry([Source(id="s", title="役割分担", version="1", lines=lines)])


def review(proposal=None, oral=None, reason="資料に合う", facts=(), intent=None, start=2, end=2, quote=None, target="私が取りまとめます"):
    quote = quote if quote is not None else LINES[start - 1]
    return Review.model_validate({
        "review_id": "r", "purpose": "確認", "intent": intent, "confirmed_facts": list(facts),
        "findings": [{"id": "F1", "target": target, "judgment": "confirmed", "professional_fit": "conformant", "intent_clarity": "ambiguous",
                      "business_premise": "agreed", "proposal_kind": "meaning_preserving_fix", "reason": reason, "proposal_text": proposal,
                      "oral_rephrase": oral, "ref_ids": ["r1"]}],
        "refs": [{"ref_id": "r1", "finding_ids": ["F1"], "source_id": "s", "version": "1", "mode": "direct_quote",
                  "location": {"kind": "lines", "start": start, "end": end}, "quote": quote}]})


def classes(rep):
    return [w["class"] for w in rep["warnings"]]


class ProposalWarnings(unittest.TestCase):
    def test_added_responsibility_words_are_flagged(self):
        rep = review_check(review(proposal="論点整理は私が担当し、最終承認も私が行います。"), reg())
        w = [x for x in rep["warnings"] if x["class"] == "proposal_adds_protected_term"]
        self.assertEqual(w[0]["terms"], ["承認"])
        self.assertEqual(rep["errors"], [])              # 警告はエラーにしない

    def test_oral_rephrase_is_checked_too(self):
        rep = review_check(review(proposal="論点を整理します。", oral="整理は私で、完了まで責任を持ちます"), reg())
        self.assertEqual(sorted(rep["warnings"][0]["terms"]), ["完了", "責任"])

    def test_words_from_target_facts_intent_or_quote_are_allowed(self):
        self.assertNotIn("proposal_adds_protected_term", classes(review_check(review(proposal="承認は部長です。", facts=["最終承認は部長が行う"]), reg())))
        self.assertNotIn("proposal_adds_protected_term", classes(review_check(review(proposal="承認を取ります。", target="承認を取ります"), reg())))
        self.assertNotIn("proposal_adds_protected_term", classes(review_check(review(proposal="完了させます。", intent="完了まで進める"), reg())))
        self.assertNotIn("proposal_adds_protected_term", classes(review_check(
            review(proposal="完了を報告します。", start=2, end=2, quote="取りまとめ: 田中が論点整理と資料作成を行う。完了を報告する。"), reg(LINES[:1] + ["取りまとめ: 田中が論点整理と資料作成を行う。完了を報告する。"] + LINES[2:]))))

    def test_no_proposal_no_warning(self):
        self.assertNotIn("proposal_adds_protected_term", classes(review_check(review(), reg())))


class ConditionWarnings(unittest.TestCase):
    def test_draft_heading_and_following_exception_are_flagged(self):
        rep = review_check(review(proposal="田中が論点整理と資料作成を行います。"), reg())
        ws = [x for x in rep["warnings"] if x["class"] == "surrounding_condition_unaddressed"]
        self.assertEqual(sorted((x["line"], tuple(x["words"])) for x in ws), [(1, ("草案",)), (3, ("ただし",))])
        self.assertEqual(rep["errors"], [])

    def test_words_the_finding_already_states_are_not_flagged(self):
        rep = review_check(review(reason="見出しは草案であり、但し書きで旧案件には適用しない(ただし)。", proposal="x"), reg())
        self.assertEqual([x for x in rep["warnings"] if x["class"] == "surrounding_condition_unaddressed"], [])

    def test_words_inside_the_quoted_range_are_not_outside_context(self):
        rep = review_check(review(start=2, end=3, quote=LINES[1] + "\n" + LINES[2], proposal="x"), reg())
        self.assertEqual([x["line"] for x in rep["warnings"] if x["class"] == "surrounding_condition_unaddressed"], [1])

    def test_lines_further_than_two_away_are_ignored_but_the_heading_is_found(self):
        lines = ["【暫定】手順", "a", "b", "c", "d", "対象の行。", "e", "f", "g(除く)"]
        rep = review_check(review(start=6, end=6, quote="対象の行。", proposal="x"), reg(lines))
        ws = [(x["line"], tuple(x["words"])) for x in rep["warnings"] if x["class"] == "surrounding_condition_unaddressed"]
        self.assertEqual(ws, [(1, ("暫定",))])           # 見出しは遠くても拾う。9行目(3行先)の『除く』は拾わない

    def test_clean_neighbourhood_has_no_warning(self):
        rep = review_check(review(start=4, end=4, quote="別の段落。", proposal="別の段落です。", reason="別の段落"), reg(["見出しなし", "a", "b", "別の段落。", "c", "d"]))
        self.assertEqual(rep["warnings"], [])

    def test_failed_refs_are_not_inspected(self):
        rep = review_check(review(quote="資料にない引用", proposal="x"), reg())
        self.assertIn("ref_check_failed", rep["error_classes"])
        self.assertEqual([x for x in rep["warnings"] if x["class"] == "surrounding_condition_unaddressed"], [])


if __name__ == "__main__":
    unittest.main()
