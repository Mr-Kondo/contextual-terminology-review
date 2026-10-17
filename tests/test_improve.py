"""更新案・新旧比較・明示的採用・復元・回帰例化・未使用評価(A24, A25, A40〜A42, A46)。"""
import unittest

from helpers import SKILL, TmpCase, run_ctr  # noqa: I001 (sys.path を整えるため先に読む)

import ctr_improve as im
from ctr_common import CtrError, read_json

TERM = {"id": "t-torimatome", "term": "取りまとめ", "sense": "案件Aでは、論点整理・調整・成果物作成を主担当として行う意味", "status": "adopted",
        "scope": {"kind": "project", "project": "prj-a"}}
KEEP = ["主担当の範囲(論点整理・関係者調整・成果物作成)", "最終承認は部長"]
FORBID = ["最終承認権を足す", "取りまとめを常に主担当と定義する"]


def spec(base, cause="definition_gap", diff=None, hypothesis=False, **kw):
    return {"cause": cause, "scope": {"kind": "project", "project": "prj-a", "domains": ["業務用語"]}, "summary": "案件A限定の語義を追加",
            "evidence": [{"run_id": "run-1", "note": "本人の意図確認済み"}], "diff": [{"op": "add", "term": TERM}] if diff is None else diff,
            "base_version": base, "keep_conditions": KEEP, "forbidden_changes": FORBID, "evaluation_plan": "回帰例と修正不要例で同条件比較",
            "hypothesis": hypothesis, **kw}


def results(base, *, cand_meaning="pass", model_c="m1", extra_items=None, no_fix=True, readability_c=3):
    items = [
        {"id": "k1", "kind": "known_failure", "current": {"meaning": "fail", "readability": 4}, "candidate": {"meaning": cand_meaning, "readability": readability_c}},
        {"id": "p1", "kind": "previously_ok", "current": {"meaning": "pass"}, "candidate": {"meaning": "pass"}},
    ]
    if no_fix:
        items.append({"id": "n1", "kind": "no_fix_needed", "current": {"meaning": "pass", "over_flag": False},
                      "candidate": {"meaning": "pass", "over_flag": False}})
    items += extra_items or []
    return {"conditions": {"base_version": base,
                           "current": {"model_id": "m1", "sources_sha": "s1", "params": {"temperature": 0}, "grader": "human", "terms_version": "v-old"},
                           "candidate": {"model_id": model_c, "sources_sha": "s1", "params": {"temperature": 0}, "grader": "human", "terms_version": "v-new"}},
            "order": "interleaved", "repeats": 1, "items": items}


class Base(TmpCase):
    def setUp(self):
        super().setUp()
        self.imp = self.mk("improvement")
        self.base = im.init_standard(self.imp)["version"]

    def propose(self, **kw):
        return im.propose_create(self.imp, **spec(self.base, **kw))["proposal_id"]

    def evaluated(self, pid, **kw):
        return im.evaluate_compare(self.imp, results(self.base, **kw), pid)


class Proposals(Base):
    def test_A24_unresolved_feedback_stays_a_hypothesis_and_is_never_promoted(self):
        pid = self.propose(hypothesis=True)
        rec = read_json(self.imp / "proposals" / f"{pid}.json")
        self.assertTrue(rec["hypothesis"])
        self.assertEqual(rec["status"], "proposed")
        ev = self.evaluated(pid)
        with self.assertRaises(CtrError) as cm:
            im.adopt(self.imp, pid, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        self.assertEqual(cm.exception.code, "not_adoptable")             # 確定誤用・採用済み規則へ自動昇格しない
        self.assertEqual(read_json(self.imp / "standard" / "terms.json")["terms"], [])
        # 保留(未分類・未確認)は回帰例にもならない
        with self.assertRaises(CtrError) as cm:
            im.regression_add(self.imp, self.reg_case(classification="pending_unresolved"))
        self.assertEqual(cm.exception.code, "regression_requires_confirmed")

    def test_A40_unagreed_responsibility_becomes_a_confirmation_item_not_a_general_rule(self):
        with self.assertRaises(CtrError) as cm:
            im.propose_create(self.imp, **spec(self.base, cause="unagreed"))        # 一般規則の差分を伴えない
        self.assertEqual(cm.exception.code, "unagreed_cannot_change_terms")
        pid = im.propose_create(self.imp, **spec(self.base, cause="unagreed", diff=[]))["proposal_id"]
        rec = read_json(self.imp / "proposals" / f"{pid}.json")
        self.assertEqual((rec["target"], rec["diff"]), ("confirmation_item", []))
        ev = self.evaluated(pid)
        with self.assertRaises(CtrError):
            im.adopt(self.imp, pid, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        # 案件限定の候補は、適用範囲(project)を持つ。一般規則(「取りまとめ=常に主担当」)の禁止変更を保持
        pid2 = self.propose()
        rec2 = read_json(self.imp / "proposals" / f"{pid2}.json")
        self.assertEqual(rec2["scope"]["kind"], "project")
        self.assertIn("取りまとめを常に主担当と定義する", rec2["forbidden_changes"])
        with self.assertRaises(CtrError):
            im.propose_create(self.imp, **spec(self.base, keep_conditions=[]))   # 保持条件・禁止変更が必要

    def reg_case(self, **kw):
        return {"case_id": "reg-1", "classification": "confirmed_problem", "reviewer": "確認者A", "reason": "意味改変を確認",
                "original_input_sha256": "ab" * 32, "location": "行2", "keep_conditions": KEEP, "forbidden_changes": FORBID,
                "scope": {"kind": "project"}, "derived_from": ["run-1"], **kw}

    def test_A25_confirmed_problem_becomes_regression_and_leaves_holdout(self):
        gold = self.mk("gold")
        im.holdout_register(gold, ["reg-1", "hold-2"])
        self.assertEqual(im.holdout_status(gold)["counts"], {"unused": 2})
        for missing in ("reviewer", "reason", "original_input_sha256", "keep_conditions", "forbidden_changes", "location"):
            bad = self.reg_case()
            bad.pop(missing)
            with self.assertRaises(CtrError, msg=missing):
                im.regression_add(self.imp, bad, gold)
        out = im.regression_add(self.imp, self.reg_case(), gold)
        self.assertTrue(out["ex_holdout"])
        rec = read_json(self.imp / "regressions" / "reg-1.json")
        self.assertEqual(rec["evaluation_eligibility"], "development_only")
        self.assertEqual(im.holdout_status(gold)["counts"], {"unused": 1, "used_for_improvement": 1})   # 以後、未使用に数えない

    def test_A46_gold_separation_is_reported_as_not_demonstrated_and_overlap_is_detected(self):
        gold = self.mk("gold")
        agent_ws = self.mk("agent-workspace")
        res = im.check_isolation(gold, [agent_ws])
        self.assertTrue(res["separate_path"])
        self.assertEqual(res["access_isolated"], "not_demonstrated")      # フォルダ分離だけでアクセス隔離完了としない
        nested = gold / "inside"
        nested.mkdir()
        res2 = im.check_isolation(nested, [gold])
        self.assertFalse(res2["separate_path"])
        self.assertTrue(res2["overlapping_agent_roots"])
        # 評価結果は未使用評価を改善に使ったら以後の資格を変える(A25と同じ登録簿)
        im.holdout_register(gold, ["u1"])
        im.mark_used_for_improvement(gold, "u1", "改善で使用")
        self.assertEqual(im.holdout_status(gold)["counts"], {"used_for_improvement": 1})
        self.assertIn("evaluation_gold_root", (SKILL_FEEDBACK).read_text(encoding="utf-8"))


SKILL_FEEDBACK = SKILL / "references" / "feedback-loop.md"


class Evaluation(Base):
    def test_A41_meaning_failure_blocks_adoption_even_when_average_improves_and_confounds_are_recorded(self):
        pid = self.propose()
        ev = self.evaluated(pid, cand_meaning="pass", model_c="m2", extra_items=[
            {"id": "n2", "kind": "no_fix_needed", "current": {"meaning": "pass", "over_flag": False},
             "candidate": {"meaning": "fail", "over_flag": True, "readability": 5}}], readability_c=5)
        self.assertEqual(ev["verdict"], "blocked")
        codes = {r["code"] for r in ev["reasons"]}
        self.assertTrue({"meaning_change_fail", "over_correction", "confounded"} <= codes)
        conf = next(r for r in ev["reasons"] if r["code"] == "confounded")
        self.assertEqual(conf["keys"], ["model_id"])                           # モデル条件の差を記録
        rec = read_json(self.imp / "evaluations" / f"{ev['evaluation_id']}.json")
        self.assertIn("相殺しない", next(r["detail"] for r in rec["block_reasons"] if r["code"] == "meaning_change_fail"))
        self.assertEqual(rec["holdout_evaluation"], "not_run")                 # 未使用評価が未実施なら未実施
        with self.assertRaises(CtrError) as cm:
            im.adopt(self.imp, pid, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        self.assertEqual(cm.exception.code, "evaluation_not_passing")

    def test_A41_same_conditions_with_all_pass_is_improved_but_needs_coverage(self):
        pid = self.propose()
        self.assertEqual(self.evaluated(pid)["verdict"], "improved")
        missing = self.evaluated(pid, no_fix=False)                            # 修正不要例がない
        self.assertEqual(missing["verdict"], "blocked")
        self.assertIn("coverage_gap", {r["code"] for r in missing["reasons"]})
        unknown = self.evaluated(pid, cand_meaning="unknown")
        self.assertEqual(unknown["verdict"], "blocked")

    def test_A42_adoption_requires_matching_base_version_and_does_not_reuse_approval(self):
        pid = self.propose()
        ev = self.evaluated(pid)
        # AI採点・自動処理は採用承認にならない: 人の名前・理由・明示フラグが必要
        for kw in ({"approved_by": "", "reason": "x", "confirmed": True}, {"approved_by": "人A", "reason": "", "confirmed": True},
                   {"approved_by": "人A", "reason": "x", "confirmed": False}):
            with self.assertRaises(CtrError) as cm:
                im.adopt(self.imp, pid, ev["evaluation_id"], **kw)
            self.assertEqual(cm.exception.code, "approval_required")
        # 評価後に基準版が変わった → 競合で止める
        other = im.propose_create(self.imp, **spec(self.base, diff=[{"op": "add", "term": {**TERM, "id": "t-other", "term": "別語"}}]))["proposal_id"]
        ev_other = self.evaluated(other)
        dec = im.adopt(self.imp, other, ev_other["evaluation_id"], approved_by="人A", reason="別案を採用", confirmed=True)
        with self.assertRaises(CtrError) as cm:
            im.adopt(self.imp, pid, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        self.assertEqual(cm.exception.code, "base_version_conflict")
        # 承認(評価)を別の差分に使い回せない
        with self.assertRaises(CtrError) as cm:
            im.adopt(self.imp, other, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        self.assertIn(cm.exception.code, ("approval_not_for_this_diff", "already_adopted"))
        # 再確認・再評価(新しい基準版を base に)した後は採用できる。復元も履歴に残る
        cur = im.current_version(self.imp)["hash"]
        pid3 = im.propose_create(self.imp, **spec(cur))["proposal_id"]
        ev3 = im.evaluate_compare(self.imp, results(cur), pid3)
        dec3 = im.adopt(self.imp, pid3, ev3["evaluation_id"], approved_by="人A", reason="再評価後に採用", confirmed=True)
        self.assertEqual(dec3["from_version"], cur)
        self.assertTrue(dec3["index_rebuild_required"])
        ids = {t["id"] for t in read_json(self.imp / "standard" / "terms.json")["terms"]}
        self.assertEqual(ids, {"t-other", "t-torimatome"})
        back = im.restore(self.imp, dec["to_version"], approved_by="人A", reason="悪化の疑いで復元", confirmed=True)
        self.assertEqual(back["type"], "restore")
        self.assertEqual({t["id"] for t in read_json(self.imp / "standard" / "terms.json")["terms"]}, {"t-other"})
        decisions = [read_json(p)["type"] for p in sorted((self.imp / "decisions").glob("*.json"))]
        self.assertEqual(sorted(decisions), ["adopt", "adopt", "restore"])     # 履歴は改変されず追記される
        with self.assertRaises(CtrError) as cm:
            im.adopt(self.imp, pid3, ev3["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        self.assertEqual(cm.exception.code, "already_adopted")

    def test_A42_decision_record_failure_rolls_back_the_standard(self):
        pid = self.propose()
        ev = self.evaluated(pid)
        before = read_json(self.imp / "standard" / "terms.json")
        real = im.write_json
        calls = {"n": 0}

        def flaky(path, obj, **kw):
            if "decisions" in str(path):
                raise CtrError("storage_unwritable")
            return real(path, obj, **kw)
        im.write_json = flaky
        try:
            with self.assertRaises(CtrError):
                im.adopt(self.imp, pid, ev["evaluation_id"], approved_by="人A", reason="x", confirmed=True)
        finally:
            im.write_json = real
        self.assertEqual(read_json(self.imp / "standard" / "terms.json"), before)          # 失敗時に既存の基準を失わない
        self.assertEqual(list((self.imp / "decisions").glob("*.json")) if (self.imp / "decisions").exists() else [], [])

    def test_cli_adopt_needs_explicit_flag(self):
        pid = self.propose()
        ev = self.evaluated(pid)
        code, out = run_ctr("evaluate", "adopt", "--improvement-root", self.imp, "--proposal", pid, "--evaluation", ev["evaluation_id"],
                            "--approved-by", "人A", "--reason", "x")
        self.assertEqual((code, out["error"]), (4, "approval_required"))


if __name__ == "__main__":
    unittest.main()
