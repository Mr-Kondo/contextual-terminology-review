"""Exercise the real, pinned Skills CLI in disposable project directories."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


NAME = "contextual-terminology-review"
SOURCE = "Mr-Kondo/contextual-terminology-review"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-probe", action="store_true")
    args = parser.parse_args()
    # A global probe may replace installs, so only use a disposable Windows runner.
    if args.global_probe and not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_OS") == "Windows"
    ):
        parser.error("--global-probe requires a disposable Windows GitHub runner")
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    assert npx, "npx is required"
    env = dict(os.environ, DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", NO_COLOR="1")
    log_dir = ROOT / "feedback" / "skills-cli-windows"
    log_dir.mkdir(parents=True, exist_ok=True)

    def run(label, cwd, *command):
        result = subprocess.run(
            [npx, "--yes", "skills@1.7.6", *command], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", timeout=180,
        )
        (log_dir / f"{label}.log").write_text(result.stdout, encoding="utf-8")
        assert result.returncode == 0, f"{label}: {result.stdout}"
        return result.stdout

    with tempfile.TemporaryDirectory(prefix="skills-cli-") as temporary:
        base = Path(temporary)
        text = (ROOT / "skill" / NAME / "SKILL.md").read_text(encoding="utf-8")
        for label, data in (
            ("lf", text.encode("utf-8")),
            ("crlf", text.replace("\n", "\r\n").encode("utf-8")),
            ("bom", text.encode("utf-8-sig")),
        ):
            fixture = base / label
            fixture.mkdir()
            (fixture / "SKILL.md").write_bytes(data)
            output = run(f"yaml-{label}", base, "add", str(fixture), "--list")
            assert "Found 1 skill" in output, f"{label}: {output}"

        workspace = base / "日本語 project"
        workspace.mkdir()
        run("project-add", workspace, "add", SOURCE, "--skill", NAME,
            "--agent", "codex", "-y")
        dest = workspace / ".agents" / "skills" / NAME
        lock_path = workspace / "skills-lock.json"
        expected = {p.relative_to(dest): p.read_bytes()
                    for p in dest.rglob("*") if p.is_file()}
        assert Path("SKILL.md") in expected and Path("VERSION") in expected

        def stale(lock_path, dest, hash_key):
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            assert lock["skills"][NAME]["source"] == SOURCE
            # Construct a stale registration, rather than claiming a historical upgrade.
            lock["skills"][NAME][hash_key] = "0" * 40
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            (dest / "VERSION").write_text("stale-fixture\n", encoding="utf-8")

        def verify(dest):
            actual = {p.relative_to(dest): p.read_bytes()
                      for p in dest.rglob("*") if p.is_file()}
            assert actual == expected, f"installed files differ: {dest}"

        stale(lock_path, dest, "computedHash")
        run("project-update", workspace, "update", NAME, "-p", "-y")
        verify(dest)
        output = run("project-current", workspace, "update", NAME, "-p", "-y")
        assert "up to date" in output, output
        run("project-remove", workspace, "remove", NAME, "-y")
        assert not dest.exists()
        print("PASS: UTF-8 LF/CRLF/BOM parsing; Unicode project add/update/current/remove")

        if args.global_probe:
            home = Path.home()
            lock_path = home / ".agents" / ".skill-lock.json"
            assert not lock_path.exists(), "global probe requires an empty runner lock"
            run("global-add", workspace, "add", SOURCE, "--skill", NAME,
                "--agent", "codex", "-g", "-y")
            dest = home / ".agents" / "skills" / NAME
            verify(dest)
            stale(lock_path, dest, "skillFolderHash")
            run("global-bare-update", workspace, "update")
            verify(dest)
            output = run("global-current", workspace, "update", NAME, "-g", "-y")
            assert "up to date" in output, output
            run("global-remove", workspace, "remove", NAME, "-g", "-y")
            assert not dest.exists()
            print("PASS: global add/bare update/current/remove; all installed files restored")


if __name__ == "__main__":
    main()
