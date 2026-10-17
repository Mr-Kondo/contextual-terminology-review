"""CLI(ctr.py)を実際にサブプロセスで起動する通し検査。終了コードとJSONを見る。"""
import json
import unittest
from pathlib import Path

from helpers import ACCEPT, SKILL, TmpCase, run_ctr


class Cli(TmpCase):
    def test_check_refs_example_and_exit_codes(self):
        code, out = run_ctr("check", "refs", "--review", SKILL / "references" / "review-example.json", "--sources", ACCEPT)
        self.assertEqual(code, 0)
        self.assertEqual([r["mechanical"] for r in out["refs"]], ["pass", "pass"])
        self.assertTrue(all(r["semantic"] == "not_run" for r in out["refs"]))          # 機械合格を意味適合にしない
        self.assertEqual(len(out["footer"]), 2)
        code, foot = run_ctr("check", "refs", "--review", SKILL / "references" / "review-example.json", "--sources", ACCEPT, "--footer-only")
        self.assertEqual(code, 0)
        self.assertEqual(len(foot.strip().splitlines()), 2)
        d = json.loads((SKILL / "references" / "review-example.json").read_text(encoding="utf-8"))
        d["refs"][1]["quote"] = "最終承認は担当者が行う。"
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        code, out = run_ctr("check", "refs", "--review", bad, "--sources", ACCEPT)
        self.assertEqual(code, 1)
        self.assertIn("quote_mismatch", out["error_classes"])
        self.assertIn("要確認", "\n".join(out["footer"]))
        code, out = run_ctr("check", "refs", "--review", self.tmp / "none.json", "--sources", ACCEPT)
        self.assertEqual((code, out["error"]), (1, "file_not_found"))
        invalid = self.tmp / "inv.json"
        invalid.write_text(json.dumps({"review_id": 1}), encoding="utf-8")
        self.assertEqual(run_ctr("check", "refs", "--review", invalid, "--sources", ACCEPT)[1]["error"], "invalid_review")

    def test_full_flow_store_record_feedback_export_blocked_then_allowed_import_metrics(self):
        rt, imp = self.mk("rt"), self.mk("imp")
        ex = SKILL / "references" / "review-example.json"
        self.assertEqual(run_ctr("store", "init", "--runtime-root", rt)[0], 0)
        self.assertEqual(run_ctr("store", "init", "--runtime-root", rt)[1]["error"], "already_initialized")
        code, st = run_ctr("record", "start", "--runtime-root", rt, "--host", "codex", "--route", "remote", "--domains", "業務用語")
        self.assertEqual(code, 0)
        rid = st["run_id"]
        code, fin = run_ctr("record", "finish", "--runtime-root", rt, "--run-id", rid, "--review", ex, "--sources", ACCEPT)
        self.assertEqual(code, 0)
        self.assertTrue(fin["write"]["verified"])
        code, fb = run_ctr("feedback", "add", "--runtime-root", rt, "--run-id", rid, "--finding-id", "F1", "--validity", "ok",
                           "--intent", "kept", "--usage", "as_is")
        self.assertEqual(code, 0)
        self.assertEqual(run_ctr("check", "runs", "--runtime-root", rt)[1][0]["status"], "completed")
        self.assertTrue(run_ctr("check", "store", "--runtime-root", rt)[1]["ok"])
        self.assertEqual(run_ctr("export", "--runtime-root", rt)[0], 4)                  # 共有許可が未設定 → 停止
        code, _ = run_ctr("store", "set-policy", "--runtime-root", rt, "--share-fields", "run_status,versions,environment,problem_axes,machine_checks,human_feedback",
                          "--share-scope", "試験用", "--granted-by", "試験者")
        self.assertEqual(code, 0)
        code, ex_out = run_ctr("export", "--runtime-root", rt)
        self.assertEqual(code, 0)
        pkg = ex_out["path"]
        self.assertIn("入力全文", ex_out["excluded_always"])
        code, im_out = run_ctr("import", pkg, "--improvement-root", imp)
        self.assertEqual((code, im_out["accepted"]), (0, 3))
        self.assertEqual(run_ctr("import", pkg, "--improvement-root", imp)[1]["status"], "already_imported")
        code, m = run_ctr("evaluate", "metrics", "--improvement-root", imp)
        self.assertEqual(code, 0)
        self.assertEqual(m["populations"]["shared_runs"], 1)
        self.assertEqual(run_ctr("export", "--runtime-root", rt)[1]["error"], "nothing_to_export")   # 書き出し済みを重複して出さない
        # 保存先を環境変数で渡す経路
        code, out = run_ctr("check", "store", env={"CTR_RUNTIME_ROOT": str(rt)})
        self.assertEqual(code, 0)

    def test_usage_error_and_store_status(self):
        code, _ = run_ctr("record")
        self.assertEqual(code, 2)
        rt = self.mk("rt2")
        run_ctr("store", "init", "--runtime-root", rt)
        code, st = run_ctr("store", "status", "--runtime-root", rt)
        self.assertFalse(st["raw_text_retention"])                                        # 原文保存は既定で不可
        self.assertIsNone(st["share_fields"])                                             # 共有は既定で未設定


if __name__ == "__main__":
    unittest.main()
