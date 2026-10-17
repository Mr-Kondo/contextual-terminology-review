#!/usr/bin/env python3
"""利用環境ごとの証拠台帳(docs/HOST-EVIDENCE.json)の検査と表の生成。

規則(A32・A48):
  - 段階: placement(仮配置) / register(登録) / invoke(呼び出し) / source_read(資料参照) / scripts_run(スクリプト実行) /
          footer_output(参照付き出力) / record_saved(記録の保存と再読込) / export_import(書き出し・取り込み)
  - 状態は success / failure / not_run。not_run には理由と再開に必要な操作を必須とする。success には証拠(種別・内容)を必須とする。
  - placement の success は register / invoke の根拠にならない。invoke の success は種別 real_invocation の証拠が要る。
  - 総合は「全段階 success」のときだけ verified。仮配置だけなら incomplete のまま。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "HOST-EVIDENCE.json"
STAGES = ["placement", "register", "invoke", "source_read", "scripts_run", "footer_output", "record_saved", "export_import"]
STATES = {"success", "failure", "not_run"}
KINDS = {"file_placement_in_temp_home", "host_listing", "real_invocation", "host_shell", "temp_runtime_roundtrip", "package_built"}
NEED_KIND = {"invoke": {"real_invocation"}, "register": {"host_listing", "real_invocation"}}


def validate(ledger: dict) -> list:
    problems = []
    for e in ledger["entries"]:
        name = f"{e['host']}/{e['route']}"
        for st in STAGES:
            s = e["stages"].get(st)
            if s is None or s.get("state") not in STATES:
                problems.append(f"{name}:{st}:state_missing_or_invalid")
                continue
            if s["state"] == "not_run" and not (s.get("reason") and s.get("next_step")):
                problems.append(f"{name}:{st}:not_run_without_reason_or_next_step")
            if s["state"] == "success":
                ev = s.get("evidence") or {}
                if not (ev.get("kind") in KINDS and ev.get("detail")):
                    problems.append(f"{name}:{st}:success_without_evidence")
                elif st in NEED_KIND and ev["kind"] not in NEED_KIND[st]:
                    problems.append(f"{name}:{st}:evidence_kind_not_sufficient({ev['kind']})")
            if s["state"] == "failure" and not s.get("detail"):
                problems.append(f"{name}:{st}:failure_without_detail")
    return problems


def overall(entry: dict) -> str:
    return "verified" if all(entry["stages"][s]["state"] == "success" for s in STAGES) else "incomplete"


def render(ledger: dict) -> str:
    mark = {"success": "成功", "failure": "失敗", "not_run": "未実施"}
    rows = ["| 環境／経路 | " + " | ".join(STAGES) + " | 総合 |", "|---|" + "---|" * (len(STAGES) + 1)]
    for e in ledger["entries"]:
        rows.append(f"| {e['host']} / {e['route']} | " + " | ".join(mark[e["stages"][s]["state"]] for s in STAGES) + f" | {overall(e)} |")
    return "\n".join(rows)


if __name__ == "__main__":
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    probs = validate(data)
    print(json.dumps({"ok": not probs, "problems": probs}, ensure_ascii=False, indent=2))
    if "--render" in sys.argv:
        print(render(data))
    sys.exit(1 if probs else 0)
