#!/usr/bin/env python3
"""Skillのdescriptionの発動精度を、Claude Code の `claude -p` で測る。

使うべき依頼(should_trigger=true)で発動するか(再現率)、近いが別の依頼で誤って発動しないか(誤発動率)、
別のSkillに取られていないか(どのSkillが呼ばれたか)を数える。出力はIDと数値で、依頼文は含まない。

測り方: 各依頼を、中立の一時ディレクトリで `claude -p` に1回ずつ渡し、最初に呼ばれた Skill を読んだ時点で打ち切る(Skillの本文は実行しない)。
既定は利用者の実環境の ~/.claude/skills をそのまま使うので、競合するSkillがあれば結果に出る(実環境のフック等も効く)。
--skill-dir を付けると、指定したSkillのフォルダだけを一時ディレクトリの .claude/skills に置き、実環境の設定(他のSkill・フック・CLAUDE.md)を読まない。
導入前の版(作業ツリーや git の過去版)を測るときに使う。競合を入れたいときは、そのフォルダも --skill-dir で足す。

基準(結果を見る前に固定。test の split だけで判定する):
  - 再現率 = test の肯定の実行のうち、このSkillが呼ばれた割合 >= 0.75
  - 誤発動率 = test の否定(borderline を除く)の実行のうち、このSkillが呼ばれた割合 <= 0.10
  - dev で description を直してよい。直した後の test は1回だけ測り、結果をそのまま報告する(test を見て直さない)
  - test を見て直した場合、その test は使い終わり。直した後に新しく書いた未使用のセット(test2)を1回だけ測る

  python3 tools/trigger_eval.py run --split test --runs 3 --out .work/trigger-test.json
  python3 tools/trigger_eval.py score --results .work/trigger-test.json --split test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))

from ctr_improve import wilson as _wilson  # noqa: E402

SKILL = "contextual-terminology-review"


def wilson(k: int, n: int):
    ci = _wilson(k, n)
    return ci and [max(0.0, ci[0]), min(1.0, ci[1])]   # 丸めで -0.0 や 1.0000x が出るのを避ける


DATA = ROOT / "tools" / "data" / "trigger-eval.json"
RECALL_MIN, FALSE_FIRE_MAX = 0.75, 0.10
SPLITS = ("dev", "test", "test2")   # test2 = descriptionを直した後に新しく書いた未使用の評価セット


def validate(data: dict) -> list:
    """書式の検査。問題の一覧を返す(空なら問題なし)。"""
    errs, seen = [], set()
    for q in data.get("queries", []):
        i = q.get("id")
        if not i or i in seen:
            errs.append(f"idが無い・重複: {i}")
        seen.add(i)
        if not isinstance(q.get("query"), str) or not q["query"].strip():
            errs.append(f"{i}: queryが空")
        if not isinstance(q.get("should_trigger"), bool):
            errs.append(f"{i}: should_trigger が真偽値でない")
        if q.get("split") not in SPLITS:
            errs.append(f"{i}: split は {'/'.join(SPLITS)} のどれか")
    for split in sorted({q.get("split") for q in data.get("queries", [])} & set(SPLITS)):
        for flag in (True, False):
            if not any(q["split"] == split and q["should_trigger"] is flag for q in data.get("queries", []) if "split" in q and "should_trigger" in q):
                errs.append(f"{split}/{'肯定' if flag else '否定'} が0件")
    return errs


def skill_from_event(ev: dict):
    """stream-json の1イベントから、呼ばれた Skill 名を返す(無ければ None)。"""
    if ev.get("type") != "assistant":
        return None
    for c in ev.get("message", {}).get("content", []) or []:
        if c.get("type") == "tool_use" and c.get("name") == "Skill":
            return (c.get("input") or {}).get("skill") or ""
    return None


def parse_stream(lines) -> dict:
    """最初に呼ばれた Skill 名と、結果イベントまで読めたか。"""
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        name = skill_from_event(ev)
        if name is not None:
            return {"fired": name, "finished": False}
        if ev.get("type") == "result":
            return {"fired": None, "finished": True, "is_error": bool(ev.get("is_error"))}
    return {"fired": None, "finished": False}


SKILL_PATH = re.compile(r"skills/([^/\s'\"\\]+)/SKILL\.md")
HOSTS = ("claude", "codex", "agy")
DEFAULT_MODEL = {"claude": None, "codex": "gpt-6-sol", "agy": "gemini-4-argon-medium"}


def skill_from_codex_event(ev: dict):
    """codex exec --json: 読んだ SKILL.md の持ち主(skills/<名前>/SKILL.md)。シェルで cat/sed などをした command_execution から取る。"""
    item = ev.get("item") or {}
    if ev.get("type") in ("item.started", "item.completed") and item.get("type") == "command_execution":
        m = SKILL_PATH.search(item.get("command") or "")
        return m.group(1) if m else None
    return None


def skill_from_agy_event(ev: dict):
    """agy --output-format stream-json: 道具の呼び出し(view_file の AbsolutePath など)に出る SKILL.md のパス。"""
    su = ev.get("step_update") or {}
    if ev.get("event") == "step_update" and su.get("step_type") == "tool":
        m = SKILL_PATH.search(json.dumps(su.get("tool_info") or {}, ensure_ascii=False))
        return m.group(1) if m else None
    return None


def parse_host_stream(lines, host: str) -> dict:
    """codex / agy のストリームから、最初に読まれた SKILL.md の名前。codex は turn.completed、agy は出力の終端で『終わった』とする。"""
    fn = skill_from_codex_event if host == "codex" else skill_from_agy_event
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        name = fn(ev)
        if name:
            return {"fired": name, "finished": False}
        if host == "codex" and ev.get("type") == "turn.completed":
            return {"fired": None, "finished": True}
    return {"fired": None, "finished": host == "agy"}      # agy: 終端まで読めて、SKILL.md を読んでいない


def _command(host: str, query: str, model, skill_dirs, extra_args):
    model = model or DEFAULT_MODEL[host]
    if host == "claude":
        cmd = ["claude", "-p", query, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
               "--strict-mcp-config", "--allowedTools", "Skill"]
        if skill_dirs:
            cmd += ["--setting-sources", "project"]
    elif host == "codex":
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "--ephemeral", "--json"]
        if skill_dirs:      # 隔離: 偽のHOMEに対象と競合だけを置き、利用者の設定・規則・記憶を読まない
            cmd += ["--ignore-user-config", "--ignore-rules", "--disable", "memories"]
        cmd += [query]
    else:
        cmd = ["agy", "--sandbox", "--dangerously-skip-permissions", "--output-format", "stream-json", "-p", query]
    if model:
        cmd += ["--model" if host != "codex" else "-m", model]
    return cmd + list(extra_args)


def run_one(query: str, model, timeout: int, skill_dirs=(), extra_args=(), host: str = "claude") -> dict:
    if host == "agy" and skill_dirs:
        raise SystemExit("agy は Skill を隔離できない(--skill-dir 不可)。実環境だけで測る")
    cmd = _command(host, query, model, skill_dirs, extra_args)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ctr-trigger-") as cwd:
        env = dict(os.environ)
        if host == "claude":
            for d in skill_dirs:
                shutil.copytree(d, Path(cwd) / ".claude" / "skills" / Path(d).resolve().name, ignore=shutil.ignore_patterns("__pycache__"))
        elif host == "codex" and skill_dirs:
            home = Path(cwd) / "home"
            for d in skill_dirs:
                shutil.copytree(d, home / ".agents" / "skills" / Path(d).resolve().name, ignore=shutil.ignore_patterns("__pycache__"))
            env["CODEX_HOME"] = env.get("CODEX_HOME") or str(Path.home() / ".codex")     # 認証は本物のまま
            env["HOME"] = str(home)
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        try:
            lines = iter(p.stdout.readline, "")
            out = parse_stream(lines) if host == "claude" else parse_host_stream(lines, host)
        finally:
            timer.cancel()
            p.kill()
            p.wait()
    out["timed_out"] = time.time() - t0 >= timeout
    out["seconds"] = round(time.time() - t0, 1)
    return out


def run(data: dict, split: str, runs: int, model, workers: int, timeout: int, skill_dirs=(), extra_args=(), host: str = "claude") -> list:
    jobs = [(q["id"], r, q["query"]) for q in data["queries"] if split in ("all", q["split"]) for r in range(1, runs + 1)]

    def one(job):
        qid, r, text = job
        res = run_one(text, model, timeout, skill_dirs, extra_args, host)
        return {"id": qid, "run": r, **res}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, jobs))


def is_ours(name) -> bool:
    return bool(name) and (name == SKILL or name.endswith(":" + SKILL))


def score(data: dict, results: list, split: str) -> dict:
    qs = {q["id"]: q for q in data["queries"]}
    pos = [r for r in results if r["id"] in qs and qs[r["id"]]["should_trigger"] and split in ("all", qs[r["id"]]["split"])]
    neg = [r for r in results if r["id"] in qs and not qs[r["id"]]["should_trigger"] and not qs[r["id"]].get("borderline")
           and split in ("all", qs[r["id"]]["split"])]
    border = [r for r in results if r["id"] in qs and qs[r["id"]].get("borderline") and split in ("all", qs[r["id"]]["split"])]
    invalid = [r for r in results if r.get("timed_out") or (not r.get("finished") and r.get("fired") is None)]
    hit = sum(is_ours(r["fired"]) for r in pos)
    ff = sum(is_ours(r["fired"]) for r in neg)

    def others(rows):
        c = {}
        for r in rows:
            if r["fired"] and not is_ours(r["fired"]):
                c[r["fired"]] = c.get(r["fired"], 0) + 1
        return c
    per_query = {}
    for r in results:
        if r["id"] in qs and split in ("all", qs[r["id"]]["split"]):
            d = per_query.setdefault(r["id"], {"runs": 0, "ours": 0, "other": {}})
            d["runs"] += 1
            d["ours"] += is_ours(r["fired"])
            if r["fired"] and not is_ours(r["fired"]):
                d["other"][r["fired"]] = d["other"].get(r["fired"], 0) + 1
    recall = hit / len(pos) if pos else None
    false_fire = ff / len(neg) if neg else None
    return {"split": split, "positive_runs": len(pos), "negative_runs": len(neg), "borderline_runs": len(border),
            "recall": {"hit": hit, "n": len(pos), "rate": recall and round(recall, 3), "wilson_95": wilson(hit, len(pos))},
            "false_fire": {"fired": ff, "n": len(neg), "rate": false_fire if false_fire is None else round(false_fire, 3), "wilson_95": wilson(ff, len(neg))},
            "borderline_fired": {"fired": sum(is_ours(r["fired"]) for r in border), "n": len(border)},
            "other_skill_on_positive": others(pos), "other_skill_on_negative": others(neg),
            "no_skill_on_positive": sum(1 for r in pos if not r["fired"]),
            "runs_without_clean_finish": len(invalid), "per_query": per_query,
            "criteria": {"recall_min": RECALL_MIN, "false_fire_max": FALSE_FIRE_MAX},
            "pass": None if invalid else {"recall": bool(recall is not None and recall >= RECALL_MIN),
                                          "false_fire": bool(false_fire is not None and false_fire <= FALSE_FIRE_MAX)},
            "warning": f"{len(invalid)}件の実行が正常に終わっていない(即時の失敗・時間切れ)。基準の判定をしない" if invalid else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--data", type=Path, default=DATA)
    r = sub.add_parser("run")
    r.add_argument("--data", type=Path, default=DATA)
    r.add_argument("--split", choices=[*SPLITS, "all"], required=True)
    r.add_argument("--runs", type=int, default=3)
    r.add_argument("--host", choices=HOSTS, default="claude", help="測る環境。codex は --skill-dir で隔離、agy は実環境のみ")
    r.add_argument("--model")
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--timeout", type=int, default=150)
    r.add_argument("--claude-arg", action="append", default=[], help="claude にそのまま足す引数を1つずつ(例: --claude-arg=--settings --claude-arg='{\"skillListingBudgetFraction\":0.05}')")
    r.add_argument("--skill-dir", type=Path, action="append", default=[], help="このフォルダだけを使う(実環境のSkill・設定は読まない)。複数可")
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--data", type=Path, default=DATA)
    s.add_argument("--results", type=Path, required=True)
    s.add_argument("--split", choices=[*SPLITS, "all"], required=True)
    s.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    data = json.loads(a.data.read_text(encoding="utf-8"))
    if a.cmd == "validate":
        errs = validate(data)
        print(json.dumps({"ok": not errs, "errors": errs, "queries": len(data["queries"])}, ensure_ascii=False))
        return 1 if errs else 0
    if a.cmd == "run":
        errs = validate(data)
        if errs:
            print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False))
            return 1
        res = run(data, a.split, a.runs, a.model, a.workers, a.timeout, [str(d) for d in a.skill_dir], a.claude_arg, a.host)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"host": a.host, "model": a.model or DEFAULT_MODEL[a.host] or "default", "split": a.split, "runs": a.runs,
                                     "skill_dirs": [d.resolve().name for d in a.skill_dir] or "実環境", "claude_args": a.claude_arg, "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"ok": True, "results": len(res), "out": str(a.out)}, ensure_ascii=False))
        return 0
    results = json.loads(a.results.read_text(encoding="utf-8"))["results"]
    rep = score(data, results, a.split)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in rep if k != "per_query"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
