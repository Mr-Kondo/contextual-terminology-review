"""導入・更新・アンインストールの往復検査(A30)。すべて一時ディレクトリの仮のホーム/作業領域で行い、実ユーザーの配置先を変更しない。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from helpers import INSTALL, ROOT, SKILL, TmpCase

sys.path.insert(0, str(ROOT / "tools"))
import ctr_install as ci  # noqa: E402

NAME = ci.NAME
CURRENT = (SKILL / "VERSION").read_text(encoding="utf-8").strip()   # 現行の版。テストを版の更新に依存させない
REAL_SKILL_DIRS = [Path.home() / ".claude" / "skills" / NAME, Path.home() / ".agents" / "skills" / NAME,
                   Path.home() / ".gemini" / "config" / "skills" / NAME, Path.home() / ".gemini" / "antigravity-cli" / "skills" / NAME]


def run(*args, expect=None):
    p = subprocess.run([sys.executable, str(INSTALL), *map(str, args)], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = p.stdout + p.stderr
    return p.returncode, out


def tree(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


class Install(TmpCase):
    def setUp(self):
        super().setUp()
        self.home = self.mk("home")
        self.src = self.tmp / "src" / NAME                       # 正本のコピー(更新・改変の検査に使う)
        shutil.copytree(SKILL, self.src, ignore=shutil.ignore_patterns("__pycache__"))
        self.real_before = [p.exists() for p in REAL_SKILL_DIRS]
        self.addCleanup(lambda: self.assertEqual([p.exists() for p in REAL_SKILL_DIRS], self.real_before,
                                                 "実ユーザーの配置先が変化した"))

    def dirs(self, target):
        return [d / NAME for d, _ in ci.resolve_dirs("user", [target], self.home.resolve(), self.tmp, None)]

    def args(self, op, target, *extra, apply=False):
        a = [op, "--target", target, "--scope", "user", "--home", self.home, "--source", self.src]
        return a + list(extra) + (["--apply"] if apply else [])

    def bump(self, text="x"):
        (self.src / "VERSION").write_text("99.0.0\n", encoding="utf-8")   # 実際の版に依存させない
        with open(self.src / "references" / "judgment.md", "a", encoding="utf-8") as f:
            f.write(f"\n<!-- {text} -->\n")

    def test_A30_plan_only_is_default_and_shows_operation_destination_and_changes(self):
        code, out = run(*self.args("install", "all"))
        self.assertEqual(code, 0)
        self.assertIn("plan-only", out["mode"])
        self.assertEqual(len(out["results"]), 4)
        for r in out["results"]:
            self.assertEqual((r["plan"]["op"], r["plan"]["action"], r["applied"]), ("install", "install", None))
            self.assertIn(str(self.home), r["plan"]["dest"])
        self.assertEqual(list(self.home.iterdir()), [])          # 何も作られない
        self.assertIn("触れない", out["data_protection"])

    def test_A30_round_trip_for_each_target(self):
        for target in ("claude-code", "codex", "antigravity-ide", "antigravity-cli"):
            with self.subTest(target=target):
                dest = self.dirs(target)[0]
                code, out = run(*self.args("install", target, apply=True))
                self.assertEqual((code, out["results"][0]["applied"]["result"]), (0, "install"))
                self.assertEqual(code, 0)
                marker = json.loads((dest / ci.MARKER).read_text(encoding="utf-8"))
                self.assertEqual(marker["version"], CURRENT)
                self.assertEqual({k: v for k, v in tree(dest).items() if k != ci.MARKER}, {k: v for k, v in tree(self.src).items()})
                self.assertEqual(run(*self.args("verify", target))[0], 0)
                self.assertEqual(run(*self.args("install", target, apply=True))[1]["results"][0]["applied"]["result"], "noop")
                self.assertEqual(run(*self.args("update", target, apply=True))[1]["results"][0]["applied"]["result"], "noop")
                code, out = run(*self.args("uninstall", target, apply=True))
                self.assertEqual((code, out["results"][0]["applied"]["result"]), (0, "remove"))
                self.assertFalse(dest.exists())
                self.assertEqual(run(*self.args("verify", target))[0], 1)       # 削除後の照合は失敗として報告

    def test_A30_target_paths_are_distinct_per_environment(self):
        paths = {t: str(self.dirs(t)[0].relative_to(self.home)) for t in ("claude-code", "codex", "antigravity-ide", "antigravity-cli")}
        self.assertEqual(len(set(paths.values())), 4)
        self.assertEqual(paths["claude-code"], f".claude/skills/{NAME}")
        self.assertEqual(paths["antigravity-ide"], f".gemini/config/skills/{NAME}")
        ws = self.mk("ws")
        d = ci.resolve_dirs("workspace", ["all"], self.home, ws.resolve(), None)
        self.assertEqual(sorted(str(p.relative_to(ws.resolve())) for p, _ in d), [".agents/skills", ".claude/skills"])   # 同じ場所は一つにまとめる

    def test_A30_update_backs_up_old_version_and_preserves_other_skills_and_data(self):
        run(*self.args("install", "claude-code", apply=True))
        skills = self.home / ".claude" / "skills"
        other = skills / "other-skill"
        other.mkdir()
        (other / "SKILL.md").write_text("---\nname: other-skill\n---\n", encoding="utf-8")
        data = self.home / "ctr-data" / "runtime"                 # 配置先の外にある利用データ・用語正本・評価履歴
        data.mkdir(parents=True)
        (data / "run.json").write_text("{}", encoding="utf-8")
        before_other, before_data = tree(other), tree(data)
        self.bump()
        code, out = run(*self.args("update", "claude-code"))      # 計画: 変更点を表示
        self.assertEqual(out["results"][0]["plan"]["action"], "update")
        self.assertTrue(out["results"][0]["plan"]["state"]["version_differs"])
        code, out = run(*self.args("update", "claude-code", apply=True))
        self.assertEqual((code, out["results"][0]["applied"]["result"]), (0, "update"))
        dest = skills / NAME
        self.assertEqual((dest / "VERSION").read_text().strip(), "99.0.0")
        bak = Path(out["results"][0]["applied"]["backup"])
        self.assertEqual((bak / "VERSION").read_text().strip(), CURRENT)        # 旧版を退避
        self.assertEqual(tree(other), before_other)                              # 他のSkillに触れない
        self.assertEqual(tree(data), before_data)                                # データに触れない
        self.assertEqual(run(*self.args("verify", "claude-code"))[0], 0)
        code, out = run(*self.args("uninstall", "claude-code", apply=True))
        self.assertEqual(out["results"][0]["applied"]["result"], "remove")
        self.assertEqual((tree(other), tree(data)), (before_other, before_data))   # アンインストールでも保護
        self.assertTrue(bak.exists())                                            # 退避した旧版は残る

    def test_A30_failure_at_every_stage_restores_previous_version(self):
        for stage in ("after_stage", "after_backup", "after_replace"):
            with self.subTest(stage=stage):
                home = self.mk(f"h-{stage}")
                skills = home / ".claude" / "skills"
                info0 = ci.validate_source(self.src)
                plan = ci.plan_one("install", skills, ["claude-code"], self.src, info0, "refuse")
                self.assertEqual(ci.apply_one(plan, self.src, info0, skills)["result"], "install")
                old = tree(skills / NAME)
                self.bump(stage)
                info1 = ci.validate_source(self.src)
                plan = ci.plan_one("update", skills, ["claude-code"], self.src, info1, "refuse")
                self.assertEqual(plan["action"], "update")

                def boom(s, want=stage):
                    if s == want:
                        raise OSError("注入した失敗")
                res = ci.apply_one(plan, self.src, info1, skills, fail_hook=boom)
                self.assertIn(res["result"], ("failed_and_restored", "failed"))
                self.assertEqual(tree(skills / NAME), old, "旧版が完全に戻っていない")
                self.assertEqual([p.name for p in skills.iterdir() if p.name.startswith(".")], [])   # 作りかけを残さない
                shutil.copytree(SKILL, self.src, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
                (self.src / "VERSION").write_text(CURRENT + "\n", encoding="utf-8")

    def test_A30_foreign_and_modified_installs_are_not_overwritten_or_deleted_without_consent(self):
        dest = self.dirs("codex")[0]
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(f"---\nname: {NAME}\ndescription: 手で置いた別物\n---\n", encoding="utf-8")
        before = tree(dest)
        for op in ("install", "update", "uninstall"):
            code, out = run(*self.args(op, "codex", apply=True))
            self.assertEqual(code, 1, op)
            self.assertEqual(out["results"][0]["applied"]["result"], "refuse")
            self.assertEqual(tree(dest), before, f"{op} が識別できない既存を変更した")
        code, out = run(*self.args("install", "codex", "--on-conflict", "backup", apply=True))
        self.assertEqual(out["results"][0]["applied"]["result"], "replace-with-backup")
        bak = Path(out["results"][0]["applied"]["backup"])
        self.assertEqual(tree(bak), before)                                      # 退避で保持
        # 導入後に手で編集された場合
        (dest / "references" / "judgment.md").write_text("手での編集", encoding="utf-8")
        code, out = run(*self.args("update", "codex", apply=True))
        self.assertEqual(out["results"][0]["applied"]["result"], "refuse")
        self.assertIn("手で変更", out["results"][0]["plan"]["notes"][0])
        code, out = run(*self.args("uninstall", "codex", apply=True))
        self.assertEqual(out["results"][0]["applied"]["result"], "refuse")
        self.assertEqual((dest / "references" / "judgment.md").read_text(encoding="utf-8"), "手での編集")
        code, out = run(*self.args("uninstall", "codex", "--on-conflict", "backup", apply=True))
        self.assertEqual(out["results"][0]["applied"]["result"], "remove-with-backup")
        self.assertFalse(dest.exists())
        self.assertEqual((Path(out["results"][0]["applied"]["backup"]) / "references" / "judgment.md").read_text(encoding="utf-8"), "手での編集")

    def test_A30_verify_detects_tampering_after_install(self):
        run(*self.args("install", "antigravity-cli", apply=True))
        f = self.dirs("antigravity-cli")[0] / "scripts" / "ctr_refs.py"
        f.write_text(f.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
        code, out = run(*self.args("verify", "antigravity-cli"))
        self.assertEqual(code, 1)
        self.assertIn("正本と不一致", "; ".join(out["results"][0]["problems"]))

    def test_A30_source_with_real_data_is_refused_and_dest_option_works(self):
        (self.src / "runtime_data").mkdir()
        (self.src / "runtime_data" / "a.json").write_text("{}")
        code, out = run(*self.args("install", "codex", apply=True))
        self.assertEqual(code, 2)
        self.assertEqual(list(self.home.iterdir()), [])
        shutil.rmtree(self.src / "runtime_data")
        dest_dir = self.mk("remote-skills")
        code, out = run("install", "--target", "codex", "--dest", dest_dir, "--source", self.src, "--apply")
        self.assertEqual(code, 0)
        self.assertTrue((dest_dir / NAME / "SKILL.md").exists())

    def test_package_for_account_side_registration_is_reproducible_and_states_not_done(self):
        out1, out2 = self.mk("pk1"), self.mk("pk2")
        c1, r1 = run("package", "--source", self.src, "--out", out1)
        c2, r2 = run("package", "--source", self.src, "--out", out2)
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(r1["sha256"], r2["sha256"])                              # 再現できるzip
        self.assertIn("未実施", r1["account_side_registration"])
        import zipfile
        names = zipfile.ZipFile(r1["zip"]).namelist()
        self.assertIn(f"{NAME}/SKILL.md", names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(ci.MARKER)])
        self.assertIn("Work/Cowork", (out1 / "INSTALL-ON-REMOTE.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
