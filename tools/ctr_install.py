#!/usr/bin/env python3
"""contextual-terminology-review の導入・更新・アンインストール・照合・配布物の作成。

  python3 tools/ctr_install.py install   --target claude-code --scope user [--apply]
  python3 tools/ctr_install.py update    --target codex       --scope workspace --workspace DIR [--apply]
  python3 tools/ctr_install.py uninstall --target antigravity --scope user [--apply]
  python3 tools/ctr_install.py verify    --target all         --scope user
  python3 tools/ctr_install.py package   --out DIR            Work/Cowork/リモート用の配布物(zip+手順)

安全方針:
  - 何も指定しなければ「計画の表示」だけ(--apply を付けたときだけ変更する)。計画には操作・配置先・変更点を出す。
  - 配置先は --scope user(--home の下)か workspace(--workspace の下)か --dest。実ユーザーのホームを使うのは、
    --home を省略して --apply したときだけ。検査では必ず一時ディレクトリを --home に指定する。
  - 配置したSkillには .ctr-install.json(版・全ファイルのsha256)を置く。同名でもこれが無いものは「識別できない既存」として
    上書きしない(--on-conflict backup で退避してから置換)。配置後に手で編集されたものも同様に扱う。
  - 更新は 新版を一時領域に作る → 旧版を退避 → 置換 → 照合、の順。どこで失敗しても旧版を戻す。
  - アンインストールが消すのは、識別できた当該Skillのディレクトリだけ。runtime_data_root / improvement_root / 用語正本 /
    評価履歴 / 他のSkill は対象外(そもそも配置先に置かない設計)。ログは既定で保持する。

配置先(既存の japanese-readability-editor/tools/install.py の表を参考にした。公式資料での再確認は docs/IMPLEMENTATION-NOTES.md):
  claude-code      workspace: .claude/skills        user: ~/.claude/skills
  codex            workspace: .agents/skills        user: ~/.agents/skills
  antigravity-ide  workspace: .agents/skills        user: ~/.gemini/config/skills
  antigravity-cli  workspace: .agents/skills        user: ~/.gemini/antigravity-cli/skills
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

NAME = "contextual-terminology-review"
MARKER = ".ctr-install.json"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "skill" / NAME
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
EXCLUDE_NAMES = {".DS_Store", MARKER}
EXCLUDE_SUFFIX = {".pyc"}

WORKSPACE = {"claude-code": ".claude/skills", "codex": ".agents/skills",
             "antigravity-ide": ".agents/skills", "antigravity-cli": ".agents/skills"}
USER = {"claude-code": ".claude/skills", "codex": ".agents/skills",
        "antigravity-ide": ".gemini/config/skills", "antigravity-cli": ".gemini/antigravity-cli/skills"}
TARGETS = sorted(WORKSPACE) + ["antigravity", "all"]
EXPAND = {"antigravity": ["antigravity-ide", "antigravity-cli"],
          "all": ["claude-code", "codex", "antigravity-ide", "antigravity-cli"]}


class InstallError(Exception):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts) or p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIX:
            continue
        if p.is_symlink():
            raise InstallError(f"シンボリックリンクは配布物に含めない: {rel}")
        if p.is_file():
            yield rel


def tree_hashes(root: Path) -> dict:
    return {rel.as_posix(): sha(root / rel) for rel in iter_files(root)}


def read_frontmatter_name(skill_md: Path):
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    for line in text.split("---\n", 2)[1].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def validate_source(src: Path) -> dict:
    md = src / "SKILL.md"
    if not md.is_file():
        raise InstallError(f"SKILL.md がない: {src}")
    if read_frontmatter_name(md) != NAME:
        raise InstallError(f"SKILL.md の name が {NAME} ではない")
    version = (src / "VERSION").read_text(encoding="utf-8").strip() if (src / "VERSION").exists() else None
    if not version:
        raise InstallError("VERSION がない")
    forbidden = [str(r) for r in iter_files(src) if r.suffix in (".log", ".sqlite") or "runtime_data" in r.parts or "gold" in r.parts]
    if forbidden:
        raise InstallError(f"実データらしきファイルが配布物に含まれる: {forbidden[:3]}")
    return {"version": version, "files": tree_hashes(src)}


def resolve_dirs(scope: str, targets: list, home: Path, workspace: Path, dest: Path | None) -> list:
    """[(skills_dir, [target...])]。同じ場所は一つにまとめる。"""
    if dest is not None:
        return [(dest.expanduser().resolve(), ["custom"])]
    table, base = (USER, home) if scope == "user" else (WORKSPACE, workspace)
    out: dict = {}
    for t in targets:
        for tt in EXPAND.get(t, [t]):
            if tt not in table:
                raise InstallError(f"不明な target: {tt}")
            out.setdefault((base / table[tt]).resolve(), []).append(tt)
    return list(out.items())


def inspect(dest_dir: Path, src_info: dict) -> dict:
    """配置先の同名Skillを識別する。"""
    if not (dest_dir.exists() or dest_dir.is_symlink()):
        return {"state": "absent"}
    if dest_dir.is_symlink() or not dest_dir.is_dir():
        return {"state": "foreign", "why": "ディレクトリではない/シンボリックリンク"}
    marker = dest_dir / MARKER
    if not marker.is_file():
        return {"state": "foreign", "why": "識別用の .ctr-install.json がない(別の手段で置かれた同名のもの)"}
    try:
        m = json.loads(marker.read_text(encoding="utf-8"))
    except ValueError:
        return {"state": "foreign", "why": ".ctr-install.json が読めない"}
    actual = tree_hashes(dest_dir)
    modified = sorted(k for k in set(actual) | set(m.get("files", {})) if actual.get(k) != m.get("files", {}).get(k))
    same_as_source = actual == src_info["files"]
    return {"state": "managed", "installed_version": m.get("version"), "modified_since_install": modified,
            "identical_to_source": same_as_source, "version_differs": m.get("version") != src_info["version"]}


def copy_tree(src: Path, dst: Path, info: dict) -> None:
    for rel in info["files"]:
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, t)
    marker = {"name": NAME, "version": info["version"], "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "files": info["files"]}
    (dst / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def backup_dir(skills_dir: Path) -> Path:
    return skills_dir.parent / f"{skills_dir.name}.bak"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def plan_one(op: str, skills_dir: Path, targets: list, src: Path, info: dict, on_conflict: str) -> dict:
    dest = skills_dir / NAME
    cur = inspect(dest, info)
    action, notes, ok = None, [], True
    st = cur["state"]
    if op == "install":
        if st == "absent":
            action = "install"
        elif st == "managed" and cur["identical_to_source"] and not cur["modified_since_install"]:
            action, notes = "noop", ["既に同じ内容が導入済み"]
        elif st == "managed":
            ok, action = False, "refuse"
            notes.append("導入済みの版/内容が異なる。update を使う")
        else:
            action = "replace-with-backup" if on_conflict == "backup" else "refuse"
            ok = on_conflict == "backup"
            notes.append(f"識別できない既存の同名Skill: {cur['why']}" + ("" if ok else "。--on-conflict backup で退避して置換できる"))
    elif op == "update":
        if st == "absent":
            ok, action = False, "refuse"
            notes.append("導入されていない。install を使う")
        elif st == "foreign":
            action = "replace-with-backup" if on_conflict == "backup" else "refuse"
            ok = on_conflict == "backup"
            notes.append(f"識別できない既存: {cur['why']}")
        elif cur["identical_to_source"] and not cur["modified_since_install"]:
            action, notes = "noop", ["最新(内容一致)"]
        elif cur["modified_since_install"]:
            action = "replace-with-backup" if on_conflict == "backup" else "refuse"
            ok = on_conflict == "backup"
            notes.append(f"導入後に手で変更されたファイルがある: {cur['modified_since_install'][:5]}")
        else:
            action = "update"
    elif op == "uninstall":
        if st == "absent":
            action, notes = "noop", ["導入されていない"]
        elif st == "foreign":
            ok, action = False, "refuse"
            notes.append(f"{NAME} として識別できないので削除しない: {cur['why']}")
        elif cur["modified_since_install"] and on_conflict != "backup":
            ok, action = False, "refuse"
            notes.append("導入後に変更されたファイルがある。--on-conflict backup で退避してから削除できる")
        else:
            action = "remove" if not cur["modified_since_install"] else "remove-with-backup"
    return {"op": op, "dest": str(dest), "targets": targets, "state": cur, "action": action, "ok": ok, "notes": notes}


def apply_one(plan: dict, src: Path, info: dict, skills_dir: Path, fail_hook=None) -> dict:
    """fail_hook(stage) は検査用。指定した段階で例外を投げ、復旧を確かめる。"""
    dest = skills_dir / NAME
    act = plan["action"]
    if act in ("noop", "refuse") or not plan["ok"]:
        return {"dest": str(dest), "result": act, "changed": False}
    bak = None
    staging = skills_dir / f".{NAME}.staging-{os.getpid()}-{stamp()}"
    try:
        skills_dir.mkdir(parents=True, exist_ok=True)
        if act in ("install", "update", "replace-with-backup"):
            copy_tree(src, staging, info)
            if fail_hook:
                fail_hook("after_stage")
        if dest.exists() or dest.is_symlink():
            if act == "install":
                raise InstallError("配置先が存在する")
            if act == "remove":  # 識別でき、導入後の変更もないので、退避せず削除する
                shutil.rmtree(dest)
            else:
                bak = backup_dir(skills_dir) / f"{NAME}-{stamp()}"
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(bak))
            if fail_hook:
                fail_hook("after_backup")
        if act != "remove" and act != "remove-with-backup":
            os.replace(staging, dest)
            if fail_hook:
                fail_hook("after_replace")
            verify = verify_one(dest, info)
            if not verify["ok"]:
                raise InstallError("配置後の照合に失敗: " + "; ".join(verify["problems"]))
        return {"dest": str(dest), "result": act, "changed": True, "backup": str(bak) if bak else None}
    except BaseException as exc:
        # 失敗時は旧版を戻す。新しく作りかけたものは消す
        if dest.exists() and bak is not None:
            shutil.rmtree(dest, ignore_errors=True)
        if bak is not None and bak.exists() and not dest.exists():
            shutil.move(str(bak), str(dest))
        return {"dest": str(dest), "result": "failed_and_restored" if bak is not None else "failed", "changed": False,
                "error": f"{type(exc).__name__}: {exc}", "restored_previous": bak is not None}
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_one(dest: Path, info: dict) -> dict:
    problems = []
    if not dest.is_dir():
        return {"ok": False, "problems": ["配置されていない"]}
    if read_frontmatter_name(dest / "SKILL.md") != NAME:
        problems.append("SKILL.md の name が違う")
    actual = tree_hashes(dest)
    for k in sorted(set(actual) | set(info["files"])):
        if actual.get(k) != info["files"].get(k):
            problems.append(f"正本と不一致: {k}")
    if not (dest / MARKER).is_file():
        problems.append("識別用ファイルがない")
    return {"ok": not problems, "problems": problems}


def build_zip(src: Path, info: dict, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    z = out / f"{NAME}-{info['version']}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in info["files"]:
            zi = zipfile.ZipInfo(f"{NAME}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))  # 再現できるzip
            zi.external_attr = (0o755 if (src / rel).stat().st_mode & 0o111 else 0o644) << 16
            zf.writestr(zi, (src / rel).read_bytes(), zipfile.ZIP_DEFLATED)
    return z


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("op", choices=["install", "update", "uninstall", "verify", "package"])
    ap.add_argument("--target", action="append", help=f"{', '.join(TARGETS)}(複数可)")
    ap.add_argument("--scope", choices=["user", "workspace"])
    ap.add_argument("--home", type=Path, help="user scope の基準(既定: 実ユーザーのホーム)")
    ap.add_argument("--workspace", type=Path, help="workspace scope の基準(既定: カレントディレクトリ)")
    ap.add_argument("--dest", type=Path, help="skills ディレクトリを直接指定する(リモートで確認済みの場所など)")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--on-conflict", choices=["refuse", "backup"], default="refuse")
    ap.add_argument("--apply", action="store_true", help="指定しなければ計画の表示だけ")
    ap.add_argument("--out", type=Path, help="package の出力先")
    a = ap.parse_args(argv)
    try:
        info = validate_source(a.source.resolve())
        if a.op == "package":
            if not a.out:
                raise InstallError("--out が必要")
            z = build_zip(a.source.resolve(), info, a.out)
            shutil.copy2(Path(__file__).resolve(), a.out / "ctr_install.py")   # 手順が配布物だけで完結するように、導入ツールも置く
            (a.out / "INSTALL-ON-REMOTE.txt").write_text(
                f"1. {z.name} と ctr_install.py をリモートへ移す(同じ出力先に置いてある。依存は pydantic: pip install pydantic)\n"
                f"2. リモートで: python3 ctr_install.py install --target <claude-code|codex|antigravity> --scope user --source <展開したskill/{NAME}>\n"
                "   (計画が表示される。内容を確認して --apply を付ける)\n"
                "   Windows(PowerShell)では python3 を py -3 に、パスの / を \\ に読み替える。絶対パスはドライブ文字から書く(例: C:\\Users\\me)\n"
                "3. Work/Cowork などアカウント側の登録はこのスクリプトでは操作できない。docs/INSTALL.md の手順で利用者が登録する\n",
                encoding="utf-8")
            print(json.dumps({"zip": str(z), "sha256": sha(z), "files": len(info["files"]),
                              "account_side_registration": "未実施(スクリプトでは操作できない)"}, ensure_ascii=False, indent=2))
            return 0
        if not a.target:
            raise InstallError("--target が必要")
        if not a.dest and not a.scope:
            raise InstallError("--scope か --dest が必要")
        home = (a.home or Path.home()).resolve()
        ws = (a.workspace or Path.cwd()).resolve()
        dirs = resolve_dirs(a.scope or "user", a.target, home, ws, a.dest)
        results, worst = [], 0
        for skills_dir, targets in dirs:
            if a.op == "verify":
                v = verify_one(skills_dir / NAME, info)
                results.append({"dest": str(skills_dir / NAME), "targets": targets, **v})
                worst = max(worst, 0 if v["ok"] else 1)
                continue
            plan = plan_one(a.op, skills_dir, targets, a.source.resolve(), info, a.on_conflict)
            entry = {"plan": plan, "applied": None}
            if a.apply:
                entry["applied"] = apply_one(plan, a.source.resolve(), info, skills_dir)
                worst = max(worst, 1 if entry["applied"]["result"] in ("failed", "failed_and_restored", "refuse") else 0)
            else:
                worst = max(worst, 0 if plan["ok"] else 1)
            results.append(entry)
        print(json.dumps({"op": a.op, "mode": "apply" if a.apply else "plan-only(変更なし)", "source_version": info["version"],
                          "results": results, "data_protection": "runtime_data_root / improvement_root / 用語正本 / 評価履歴 / 他のSkill には触れない"},
                         ensure_ascii=False, indent=2))
        return worst
    except InstallError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
