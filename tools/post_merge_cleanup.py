#!/usr/bin/env python3
"""許可されたマージの後の後片付け(A31)。マージ・公開そのものは行わない。

  python3 tools/post_merge_cleanup.py --repo DIR --branch work/x --base main [--remote origin] [--remove-path P ...] [--apply]

- 既定は計画の表示だけ。--apply で、取り込みを確認できた指定ブランチだけを、ローカル・リモートの両方から削除する。
- base に取り込まれていない(未マージの)ブランチ、base 自身、現在チェックアウト中のブランチは削除しない。
- 指定した以外のブランチ(他者の作業を含む)には触れない。
- --remove-path は、今回の作業で作った一時ファイル・仮想環境などを明示して消す。--repo の中か、一時ディレクトリの中だけ受け付ける。
- 最後に、削除したもの・残したもの(理由つき)を報告する。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo: Path, *args, check=False):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")   # Windows の既定の文字コードで書けない文字があっても落とさない
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--remote", default=None)
    ap.add_argument("--remove-path", action="append", default=[], type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    report = {"mode": "apply" if a.apply else "plan-only", "deleted": [], "kept": [], "refused": []}
    repo = a.repo.resolve()
    if git(repo, "rev-parse", "--git-dir").returncode:
        report["refused"].append({"what": "repo", "why": "git リポジトリではない(ブランチの後片付けは対象外)"})
    else:
        cur = git(repo, "branch", "--show-current").stdout.strip()
        local_exists = git(repo, "rev-parse", "--verify", "-q", f"refs/heads/{a.branch}").returncode == 0
        merged_local = local_exists and git(repo, "merge-base", "--is-ancestor", f"refs/heads/{a.branch}", f"refs/heads/{a.base}").returncode == 0
        remote_ref = f"refs/remotes/{a.remote}/{a.branch}" if a.remote else None
        remote_exists = bool(remote_ref) and git(repo, "rev-parse", "--verify", "-q", remote_ref).returncode == 0
        merged_remote = remote_exists and git(repo, "merge-base", "--is-ancestor", remote_ref, f"refs/heads/{a.base}").returncode == 0
        if a.branch == a.base or a.branch == cur:
            report["refused"].append({"what": a.branch, "why": "base 自身または現在のブランチは削除しない"})
        else:
            for kind, exists, merged in (("local", local_exists, merged_local), ("remote", remote_exists, merged_remote)):
                if kind == "remote" and not a.remote:
                    report["kept"].append({"what": f"remote:{a.branch}", "why": "--remote が未指定のため対象外(リモートも消すなら --remote origin を付ける)"})
                elif not exists:
                    report["kept"].append({"what": f"{kind}:{a.branch}", "why": "存在しない(削除済みか未作成)"})
                elif not merged:
                    report["refused"].append({"what": f"{kind}:{a.branch}", "why": f"{a.base} への取り込みを確認できない(未マージ)。削除しない"})
                elif not a.apply:
                    report["deleted"].append({"what": f"{kind}:{a.branch}", "state": "plan"})
                elif kind == "local":
                    r = git(repo, "branch", "-d", a.branch)
                    report["deleted" if not r.returncode else "refused"].append({"what": f"local:{a.branch}", "detail": r.stderr.strip()})
                else:
                    r = git(repo, "push", a.remote, "--delete", a.branch)
                    report["deleted" if not r.returncode else "refused"].append({"what": f"remote:{a.branch}", "detail": r.stderr.strip()})
            others = [b for b in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split() if b not in (a.branch, a.base)]
            if others:
                report["kept"].append({"what": ",".join(others), "why": "指定外のブランチ(他者の作業を含み得る)。触れない"})
    allowed = [repo, Path(tempfile.gettempdir()).resolve()]
    for p in a.remove_path:
        rp = p.resolve()
        if not any(rp == r or r in rp.parents for r in allowed) or rp == repo:
            report["refused"].append({"what": str(p), "why": "リポジトリ内か一時ディレクトリ内のパスだけ受け付ける"})
        elif not rp.exists():
            report["kept"].append({"what": str(p), "why": "存在しない"})
        elif not a.apply:
            report["deleted"].append({"what": str(p), "state": "plan"})
        else:
            shutil.rmtree(rp) if rp.is_dir() else rp.unlink()
            report["deleted"].append({"what": str(p)})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
