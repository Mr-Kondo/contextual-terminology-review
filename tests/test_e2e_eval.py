"""E2E評価(tools/e2e_eval.py)の、課題集の検査・出力の解釈・採点・集計の検査。モデルは呼ばない。"""
import json
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import e2e_eval as e2e  # noqa: E402

DATA = json.loads(e2e.DATA.read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in DATA["cases"]}


def out(*findings):
    return {"findings": [{"target": t, "verdict": v, "proposal": p} for t, v, p in findings]}


class CaseSet(unittest.TestCase):
    def test_dataset_is_valid_and_balanced(self):
        self.assertEqual(e2e.validate(DATA), [])
        for split in ("dev", "test"):
            for kind in ("misuse", "ambiguity", "correct", "mismatch"):
                self.assertEqual(sum(c["split"] == split and c["kind"] == kind for c in DATA["cases"]), 4, (split, kind))

    def test_each_correct_case_pairs_with_a_misuse_case_on_the_same_source(self):
        src = {json.dumps(c["sources"]) for c in DATA["cases"] if c["kind"] == "misuse"}
        self.assertTrue(all(json.dumps(c["sources"]) in src for c in DATA["cases"] if c["kind"] == "correct"))

    def test_validate_catches_bad_regex_and_missing_fields(self):
        bad = {"cases": [{"id": "x", "kind": "misuse", "split": "dev", "text": "t", "sources": [{"lines": ["a"]}],
                          "gold": {"verdict_in": ["misuse"], "target": ["t"], "accept": ["("], "forbidden": []}}, {"id": "y"}]}
        errs = e2e.validate(bad)
        self.assertTrue(any("正規表現" in x for x in errs) and any(x.startswith("y:") for x in errs))

    def test_prompts_differ_only_by_the_skill_line_and_hide_gold(self):
        c = CASES["M1"]
        a, b = e2e.prompt_for(c, "baseline"), e2e.prompt_for(c, "skill")
        self.assertEqual(b.replace(f"{e2e.SKILL} のSkillを使ってください。\n", ""), a)
        for secret in ("gold", "accept", "forbidden", "misuse_expected"):
            self.assertNotIn(secret, a)


class Parse(unittest.TestCase):
    def test_extract_json_takes_the_last_valid_fenced_block(self):
        text = '説明\n```json\n{"findings": []}\n```\n追記\n```json\n{"findings": [{"target": "a", "verdict": "ok", "proposal": ""}]}\n```'
        self.assertEqual(len(e2e.extract_json(text)["findings"]), 1)
        self.assertIsNone(e2e.extract_json("JSONなし"))
        self.assertIsNone(e2e.extract_json('```json\n{"x": 1}\n```'))

    def test_parse_stream_collects_result_and_skill_calls(self):
        lines = [json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": e2e.SKILL}}]}}),
                 json.dumps({"type": "result", "result": "本文", "num_turns": 4, "total_cost_usd": 0.1, "duration_ms": 900, "is_error": False}), "壊れた行"]
        r = e2e.parse_stream(lines)
        self.assertEqual((r["text"], r["skills"], r["turns"]), ("本文", [e2e.SKILL], 4))

    def test_write_sources_creates_numbered_files_with_header(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            e2e.write_sources(CASES["M1"], Path(td))
            t = (Path(td) / "sources" / "doc-01.txt").read_text(encoding="utf-8")
            self.assertTrue(t.startswith("【資料名】設計用語集【版】2025-06\n"))
            self.assertIn("冪等:", t)


class Judge(unittest.TestCase):
    def test_misuse_needs_the_verdict_and_an_accepted_correction(self):
        c = CASES["M1"]
        self.assertTrue(e2e.judge(c, out(("冪等", "misuse", "結果の状態が同じになります")))["pass"])
        self.assertFalse(e2e.judge(c, out(("冪等", "misuse", "言葉を直してください")))["pass"])      # 修正案に語句が無い
        self.assertFalse(e2e.judge(c, out(("冪等", "ok", "")))["pass"])
        self.assertFalse(e2e.judge(c, None)["pass"])
        self.assertFalse(e2e.judge(c, None)["format_ok"])

    def test_ambiguity_passes_on_hold_but_fails_on_confident_misuse_or_invention(self):
        c = CASES["A1"]
        self.assertTrue(e2e.judge(c, out(("取りまとめ", "ambiguous", "範囲を確認します")))["pass"])
        self.assertTrue(e2e.judge(c, out(("取りまとめ", "insufficient", "")))["pass"])
        self.assertFalse(e2e.judge(c, out(("取りまとめ", "misuse", "")))["pass"])
        r = e2e.judge(c, out(("取りまとめ", "ambiguous", "承認は部長が行います")))
        self.assertTrue(r["invention"] and not r["pass"])

    def test_alt_scoring_does_not_depend_on_the_target_string(self):
        c = CASES["X8"]
        r = e2e.judge(c, out(("3重", "ambiguous", "確認する"), ("冗長化", "ok", "")))        # 保留は別の語句に付いている
        self.assertFalse(r["pass"])
        self.assertTrue(r["pass_alt"])

    def test_backup_case_flags_restorability_claim(self):
        c = CASES["A2"]
        self.assertTrue(e2e.judge(c, out(("取得済み", "ambiguous", "復元できるかは未確認です")))["pass"])
        self.assertFalse(e2e.judge(c, out(("取得済み", "ambiguous", "毎日取得し、復元できます")))["pass"])

    def test_correct_case_fails_only_when_the_target_term_is_flagged(self):
        c = CASES["C1"]
        self.assertTrue(e2e.judge(c, out(("冪等", "ok", "")))["pass"])
        self.assertTrue(e2e.judge(c, {"findings": []})["pass"])
        r = e2e.judge(c, out(("冪等", "ok", ""), ("リクエスト", "ambiguous", "要確認")))             # 対象語以外への指摘は合否に数えない
        self.assertTrue(r["pass"] and not r["false_flag"])
        self.assertTrue(r["false_flag_any"] and r["extra_flags"] == 1)
        r = e2e.judge(c, out(("冪等", "ambiguous", "判定基準を明記する")))
        self.assertTrue(r["false_flag"] and not r["pass"])
        self.assertTrue(e2e.judge(c, out(("冪等", "insufficient", "")))["false_flag"])

    def test_mismatch_requires_hold_not_confident_use_of_the_wrong_source(self):
        c = CASES["X1"]
        self.assertTrue(e2e.judge(c, out(("30日以内", "insufficient", "案件Aの契約は確認できません")))["pass"])
        self.assertFalse(e2e.judge(c, out(("30日以内", "ok", "")))["pass"])
        self.assertFalse(e2e.judge(c, out(("30日以内", "misuse", "")))["pass"])

    def test_unknown_verdicts_count_as_format_failure(self):
        c = CASES["C1"]
        r = e2e.judge(c, out(("冪等", "fine", "")))
        self.assertFalse(r["format_ok"] or r["pass"])

    def test_len_ratio(self):
        c = CASES["M1"]
        r = e2e.judge(c, out(("冪等", "misuse", "状態" * 10)))
        self.assertEqual(r["len_ratio"], round(20 / len(c["text"]), 2))


class Score(unittest.TestCase):
    def results(self, fn):
        rows = []
        for c in DATA["cases"]:
            if c["split"] != "dev":
                continue
            for cond in ("baseline", "skill"):
                rows.append({"id": c["id"], "condition": cond, "run": 1, "parsed": fn(c, cond), "skill_called": cond == "skill",
                             "seconds": 10.0, "cost_usd": 0.1, "turns": 3})
        return rows

    @staticmethod
    def good(c):
        k = c["kind"]
        if k == "misuse":
            return out((c["gold"]["target"][0], "misuse", {"M1": "状態が同じ", "M2": "確度", "M3": "一方向", "M4": "発注者が確認"}[c["id"]]))
        if k == "correct":
            return out((c["gold"]["target"][0], "ok", ""))
        return out((c["gold"]["target"][0], "insufficient", ""))

    def test_skill_better_than_baseline_passes_criteria(self):
        rep = e2e.score(DATA, self.results(lambda c, cond: self.good(c) if cond == "skill" else None), "dev")
        self.assertEqual(rep["conditions"]["skill"]["pass"]["k"], 16)
        self.assertEqual(rep["conditions"]["baseline"]["format_failures"], 16)
        self.assertEqual(rep["paired"]["mean_diff"], 1.0)
        self.assertTrue(all(rep["pass"].values()))

    def test_equal_outputs_do_not_claim_improvement(self):
        rep = e2e.score(DATA, self.results(lambda c, cond: self.good(c)), "dev")
        self.assertEqual((rep["paired"]["improved"], rep["paired"]["worsened"]), (0, 0))
        self.assertFalse(rep["pass"]["accuracy"])

    def test_more_false_flags_or_inventions_than_baseline_fail_those_criteria(self):
        def fn(c, cond):
            if cond == "baseline":
                return self.good(c)
            if c["kind"] == "correct":
                return out((c["gold"]["target"][0], "misuse", "直しました"))
            if c["id"] == "A1":
                return out(("取りまとめ", "ambiguous", "承認は部長が行います"))
            return self.good(c)
        rep = e2e.score(DATA, self.results(fn), "dev")
        self.assertFalse(rep["pass"]["false_flag"])
        self.assertFalse(rep["pass"]["invention"])


if __name__ == "__main__":
    unittest.main()
