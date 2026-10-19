"""資料の整合性・環境別証拠台帳(A32, A48)・マージ後の後片付け(A31)・Skillの構成と境界。"""
import json
import re
import subprocess
import sys
import unittest

from helpers import ROOT, SKILL, TmpCase

sys.path.insert(0, str(ROOT / "tools"))
import check_design_docs as cdd  # noqa: E402
import host_evidence as he  # noqa: E402

CLEANUP = ROOT / "tools" / "post_merge_cleanup.py"


class DesignDocs(unittest.TestCase):
    def test_design_documents_are_consistent(self):
        res = cdd.check()
        self.assertTrue(res["ok"], res["problems"])
        self.assertIn("実装", res["scope"])                                      # 資料の検査であり実装の検証ではないと明記


class HostEvidence(unittest.TestCase):
    def ledger(self):
        return json.loads(he.LEDGER.read_text(encoding="utf-8"))

    def test_A32_ledger_is_valid_and_unavailable_paths_are_recorded_as_not_run_with_reason_and_next_step(self):
        led = self.ledger()
        self.assertEqual(he.validate(led), [])
        remote = [e for e in led["entries"] if e["route"] == "remote"]
        self.assertGreaterEqual(len(remote), 3)
        for e in remote + [e for e in led["entries"] if e["route"] == "account"]:
            for st in ("register", "invoke", "record_saved"):
                s = e["stages"][st]
                self.assertEqual(s["state"], "not_run")
                self.assertTrue(s["reason"] and s["next_step"])                   # 再開条件を残す
        # アクセス不能でも、残りの実装・検査は止めない: ローカル経路の実行段階は成功として記録されている
        cc = next(e for e in led["entries"] if (e["host"], e["route"]) == ("claude-code", "local"))
        self.assertEqual(cc["stages"]["record_saved"]["state"], "success")

    def test_A32_placement_never_makes_an_environment_verified(self):
        led = self.ledger()
        for e in led["entries"]:
            st = e["stages"]
            if he.overall(e) == "verified":                                         # verified は、実呼び出しの証拠がある経路だけ
                self.assertEqual(st["invoke"]["evidence"]["kind"], "real_invocation", f"{e['host']}/{e['route']}")
            if st["invoke"]["state"] != "success":
                self.assertEqual(he.overall(e), "incomplete", f"{e['host']}/{e['route']}")
        placement_only = [e for e in led["entries"] if e["stages"]["placement"]["state"] == "success" and e["stages"]["invoke"]["state"] != "success"]
        self.assertTrue(placement_only)                                              # 仮配置・導入だけの経路が残っている
        e = led["entries"][0]
        e2 = json.loads(json.dumps(e))
        e2["stages"]["invoke"] = {"state": "success", "evidence": {"kind": "file_placement_in_temp_home", "detail": "置いただけ"}}
        self.assertTrue(he.validate({"entries": [e2]}))                              # 配置の証拠で呼び出しを成功にできない
        e3 = json.loads(json.dumps(e))
        e3["stages"]["scripts_run"] = {"state": "success"}
        self.assertIn("success_without_evidence", " ".join(he.validate({"entries": [e3]})))
        e4 = json.loads(json.dumps(e))
        e4["stages"]["register"] = {"state": "not_run"}
        self.assertIn("not_run_without_reason_or_next_step", " ".join(he.validate({"entries": [e4]})))

    def test_A48_three_required_environments_are_covered_per_route_and_a_placement_only_environment_is_not_reported_as_collecting(self):
        led = self.ledger()
        hosts = {(e["host"].split("-")[0] if e["host"].startswith("antigravity") else e["host"], e["route"]) for e in led["entries"]}
        for h in ("claude-code", "codex", "antigravity"):
            self.assertIn((h, "local"), hosts)
            self.assertIn((h, "remote"), hosts)
        for e in led["entries"]:
            if e["stages"]["placement"]["state"] == "success" and e["stages"]["invoke"]["state"] != "success":
                self.assertNotEqual(he.overall(e), "verified")
        for f in ("real-host-claude-code.md", "real-host-codex.md", "real-host-antigravity.md"):          # 実呼び出しの証拠ファイル
            txt = (ROOT / "docs" / "evidence" / f).read_text(encoding="utf-8")
            self.assertIn("出典一覧" if "出典一覧" in txt else "参照", txt)
            for private in ("@gmail", "@hotmail", "/Users/", "/private/tmp"):
                self.assertNotIn(private, txt, f)                                    # 認証情報・個人パスを公開物へ入れない
        self.assertTrue((ROOT / "docs" / "evidence" / "claude-code-local-run.txt").exists())   # 実記録・再読込の証拠ファイル


class PostMergeCleanup(TmpCase):
    def sh(self, *cmd, cwd=None):
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)

    def setup_repos(self):
        remote = self.mk("remote.git")
        self.sh("git", "init", "-q", "--bare", "-b", "main", str(remote))
        work = self.tmp / "work"
        self.sh("git", "clone", "-q", str(remote), str(work))
        g = lambda *a: self.sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *a, cwd=work)
        (work / "a.txt").write_text("a")
        g("add", "."); g("commit", "-q", "-m", "init"); g("push", "-q", "origin", "main")
        for b in ("work/merged", "work/unmerged", "other/people"):
            g("checkout", "-q", "-b", b, "main")
            (work / f"{b.replace('/', '_')}.txt").write_text(b)
            g("add", "."); g("commit", "-q", "-m", b); g("push", "-q", "origin", b)
        g("checkout", "-q", "main"); g("merge", "-q", "--no-ff", "-m", "merge", "work/merged"); g("push", "-q", "origin", "main")
        return work, remote, g

    def run_cleanup(self, work, *args):
        p = subprocess.run([sys.executable, str(CLEANUP), "--repo", str(work), *args], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def test_A31_merged_branch_is_deleted_locally_and_remotely_and_unmerged_or_others_are_kept(self):
        work, remote, g = self.setup_repos()
        scratch = self.mk("scratch-venv")
        (scratch / "x").write_text("tmp")
        code, plan = self.run_cleanup(work, "--branch", "work/merged", "--base", "main", "--remote", "origin", "--remove-path", str(scratch))
        self.assertEqual(code, 0)
        self.assertEqual({d["state"] for d in plan["deleted"]}, {"plan"})
        self.assertTrue(scratch.exists())                                          # 計画だけでは消さない
        code, rep = self.run_cleanup(work, "--branch", "work/merged", "--base", "main", "--remote", "origin", "--remove-path", str(scratch), "--apply")
        self.assertEqual(code, 0, rep)
        refs = self.sh("git", "for-each-ref", "--format=%(refname:short)", cwd=work).stdout.split()
        self.assertNotIn("work/merged", refs)
        self.assertNotIn("origin/work/merged", self.sh("git", "branch", "-r", cwd=work).stdout.replace(" ", "\n").split())
        remote_heads = self.sh("git", "for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=remote).stdout.split()
        self.assertNotIn("work/merged", remote_heads)                              # リモート側も削除
        self.assertEqual({"main", "work/unmerged", "other/people"} <= set(remote_heads), True)
        self.assertFalse(scratch.exists())
        self.assertTrue(any("指定外" in k["why"] for k in rep["kept"]))             # 他者の作業を残した理由を報告

    def test_A31_without_remote_option_the_remote_is_reported_as_out_of_scope_not_as_missing(self):
        work, remote, g = self.setup_repos()
        code, rep = self.run_cleanup(work, "--branch", "work/merged", "--base", "main")
        self.assertEqual(code, 0)
        why = [k["why"] for k in rep["kept"] if k["what"] == "remote:work/merged"]
        self.assertTrue(why and "--remote" in why[0] and "存在しない" not in why[0])

    def test_A31_unmerged_base_current_branch_and_outside_paths_are_refused(self):
        work, remote, g = self.setup_repos()
        code, rep = self.run_cleanup(work, "--branch", "work/unmerged", "--base", "main", "--remote", "origin", "--apply")
        self.assertEqual(code, 1)
        self.assertTrue(any("未マージ" in r["why"] for r in rep["refused"]))
        refs = self.sh("git", "for-each-ref", "--format=%(refname:short)", cwd=work).stdout.split()
        self.assertIn("work/unmerged", refs)
        self.assertIn("work/unmerged", self.sh("git", "for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=remote).stdout.split())
        code, rep = self.run_cleanup(work, "--branch", "main", "--base", "main", "--apply")
        self.assertEqual(code, 1)
        outside = "/usr/local/some-unrelated-dir"
        code, rep = self.run_cleanup(work, "--branch", "work/merged", "--base", "main", "--remove-path", outside, "--apply")
        self.assertTrue(any(r["what"] == str(Path(outside)) for r in rep["refused"]))   # Windows では区切りが \ になる

    def test_A31_not_a_git_repo_is_reported_not_faked(self):
        code, rep = self.run_cleanup(self.mk("plain"), "--branch", "x", "--base", "main")
        self.assertEqual(code, 1)
        self.assertIn("git リポジトリではない", rep["refused"][0]["why"])


class SkillShape(unittest.TestCase):
    def test_frontmatter_is_minimal_and_description_states_scope_and_exclusions(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        fm = text.split("---\n")[1]
        keys = [l.split(":")[0] for l in fm.splitlines() if re.match(r"^[a-z-]+:", l)]
        self.assertEqual(keys, ["name", "description"])                              # 共通frontmatterは最小(Cowork等への持ち込みを妨げない)
        desc = next(l for l in fm.splitlines() if l.startswith("description:"))
        for must in ("用法", "文脈", "レビュー", "使わない"):
            self.assertIn(must, desc)
        for linked in re.findall(r"\]\((references/[^)]+)\)", text):
            self.assertTrue((SKILL / linked).exists(), linked)

    def test_skill_folder_has_no_real_data_and_no_dependency_on_other_skills(self):
        bad = [str(p.relative_to(SKILL)) for p in SKILL.rglob("*") if p.is_file() and
               (p.suffix in (".log", ".sqlite", ".db", ".npy") or {"runtime_data", "gold", "private", "outbox", "inbox"} & set(p.relative_to(SKILL).parts))]
        self.assertEqual(bad, [])
        for p in SKILL.rglob("*.py"):
            self.assertNotIn("japanese-readability-editor", p.read_text(encoding="utf-8").replace("japanese-readability-editor の", ""), p.name)
            self.assertNotIn("sys.path.insert(0, str(Path.home()", p.read_text(encoding="utf-8"))

    def test_scripts_do_not_start_network_services_or_resident_processes(self):
        for p in SKILL.rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            for banned in ("socket.", "http.server", "urllib.request", "requests.", "schedule", "crontab", "launchd", "daemon"):
                self.assertNotIn(banned, src, f"{p.name}: {banned}")             # 自動送信・常駐・定期実行を設定しない


if __name__ == "__main__":
    unittest.main()
