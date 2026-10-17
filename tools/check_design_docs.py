#!/usr/bin/env python3
"""設計資料(00〜07・manifest)の整合性検査。Skillの品質検証ではない。

確認するもの: manifest のSHA-256・サイズ、03のJSON(48件・ID一意・source_id参照)、Markdown内のローカルリンク、
必須トピックの存在、06が参照するA番号の範囲。意味や実装の妥当性は見ない。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["00-START-HERE.md", "01-design.md", "02-implementation-prompt.md", "03-acceptance-cases.json",
        "04-reuse-decisions.md", "05-research-background.md", "06-acceptance-matrix.md", "07-feedback-and-storage.md"]
TOPICS = {"02-implementation-prompt.md": ["9A", "7A", "11", "Claude Code・Codex・Gemini Antigravity"],
          "07-feedback-and-storage.md": ["record", "feedback", "check", "export", "import", "propose", "evaluate"],
          "06-acceptance-matrix.md": ["A33〜A34", "A44", "A48"]}
LINK = re.compile(r"\]\(([^)#]+?)(?:#[^)]*)?\)")


def check(root: Path = ROOT) -> dict:
    problems, notes = [], []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    listed = {f["path"]: f for f in manifest["files"]}
    for name in DOCS:
        p = root / name
        if not p.exists():
            problems.append(f"missing:{name}")
            continue
        data = p.read_bytes()
        f = listed.get(name)
        if not f:
            problems.append(f"not_in_manifest:{name}")
        elif hashlib.sha256(data).hexdigest() != f["sha256"] or len(data) != f["bytes"]:
            problems.append(f"manifest_mismatch:{name}")
    cases = json.loads((root / "03-acceptance-cases.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases["cases"]]
    if len(ids) != 48 or len(set(ids)) != 48 or ids != [f"A{i:02d}" for i in range(1, 49)]:
        problems.append("case_ids_not_A01_to_A48_unique")
    src_ids = {s["id"] for s in cases["source_catalog"]}
    for c in cases["cases"]:
        for sid in c["given"].get("source_ids", []):
            if sid not in src_ids:
                problems.append(f"unknown_source_id_in_case:{c['id']}:{sid}")
        ref = c["given"].get("reference_to_check")
        if ref and ref["source_id"] not in src_ids and "A13" != c["id"]:
            problems.append(f"unknown_ref_source:{c['id']}")
    if cases.get("is_holdout") is not False:
        problems.append("is_holdout_must_be_false")
    links = 0
    for name in DOCS:
        if name.endswith(".md"):
            for target in LINK.findall((root / name).read_text(encoding="utf-8")):
                if re.match(r"^(https?:|mailto:|/|~)", target):  # 絶対パス・ホーム相対は利用者環境のパスで、公開リポジトリでは確認しない
                    continue
                links += 1
                if not (root / target).exists():
                    problems.append(f"broken_link:{name}->{target}")
    for name, words in TOPICS.items():
        text = (root / name).read_text(encoding="utf-8")
        for w in words:
            if w not in text:
                problems.append(f"missing_topic:{name}:{w}")
    notes.append(f"files={len(DOCS)} cases={len(ids)} local_links={links}")
    return {"ok": not problems, "problems": problems, "notes": notes,
            "scope": "資料間の整合性のみ。Skillの実装・意味・効果の検証ではない"}


if __name__ == "__main__":
    res = check()
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["ok"] else 1)
