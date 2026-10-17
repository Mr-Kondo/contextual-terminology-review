#!/usr/bin/env python3
"""初見の課題で、Skillあり/なしの最終出力を比べる(Claude Code の `claude -p`)。

測ること: Skillが、(1)資料に照らした誤用を直せるか (2)正しい用法を直さないか (3)資料が決め手にならないとき、責務や完了状態を作らずに保留できるか
(4)別案件・旧版・草案・他社の資料を、この文に当てはめず保留できるか。**人の受け手の理解は測らない**(それは effect_pilot.py と人による測定)。

条件: どちらも同じ課題・同じ資料(sources/ のファイル)・同じ追加指示(最後にJSONで verdict と修正案を付ける)。違いはSkillの有無だけ。
  - baseline: Skillなし(--disable-slash-commands)
  - skill   : 指定したSkillのフォルダだけを一時ディレクトリの .claude/skills に置く(実環境の他のSkill・フック・CLAUDE.md は読まない)。プロンプトで Skill名を指す
採点は機械的(JSONの verdict・修正案の語句)。意味保持の審査ではない。『誤用を直した』の判定は修正案の語句(gold.accept)で近似しているため、
言い換えを取りこぼす(Skillありに不利にもなりうる)。作成者はSkillの設計者と同じAIで、独立していない。

基準(結果を見る前に固定。test の split だけで判定する):
  - 全体の正答率の差(skill − baseline、課題ごとの平均)が +0.10 以上、かつ改善した課題数 > 悪化した課題数
  - 修正不要(correct)の課題で、対象語を『直した・保留した』割合が、baseline より +0.10 を超えて増えない(対象語以外への指摘は別に数える)
  - 責務や完了状態の無断追加(gold.forbidden の語句)が、baseline より増えない
  - dev で Skill を直してよい。直した後の test は1回だけ測り、結果をそのまま報告する

  python3 tools/e2e_eval.py run --split dev --runs 1 --skill-dir skill/contextual-terminology-review --out .work/e2e-dev.json
  python3 tools/e2e_eval.py score --results .work/e2e-dev.json --split dev --out docs/evidence/e2e-dev.json
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

from ctr_improve import wilson  # noqa: E402
from effect_pilot import binom_two_sided  # noqa: E402

DATA = ROOT / "tools" / "data" / "e2e-cases.json"
SKILL = "contextual-terminology-review"
SPLITS = ("dev", "test")
VERDICTS = ("misuse", "ambiguous", "ok", "insufficient")

INSTRUCTION = (
    "次の文について、用語の用法と文脈の観点でレビューしてください。\n"
    "対象文:「{text}」\n"
    "目的・読み手: {purpose}\n"
    "資料(読み取り専用): カレントディレクトリの sources/ 以下のファイル(先頭行に資料名と版)。\n"
    "{skill_line}"
    "\n【評価用の追加指示】回答の最後に、次の形式のJSONを必ず1つだけ付けてください(```json のコードフェンスで囲む)。\n"
    '{{"findings":[{{"target":"対象文中の語句","verdict":"misuse|ambiguous|ok|insufficient","proposal":"修正案(不要なら空文字)"}}]}}\n'
    "verdict の意味: misuse=資料に照らして誤用と言える / ambiguous=誤用とは言えないが、意味が定まらない / ok=直す必要がない / "
    "insufficient=資料がこの文に当てはまらない、または資料だけでは判断できない。\n"
    "findings は、対象文の論点ごとに書き、問題がなければ verdict を ok にしてください。\n")


def prompt_for(case: dict, condition: str) -> str:
    skill_line = f"{SKILL} のSkillを使ってください。\n" if condition == "skill" else ""
    return INSTRUCTION.format(text=case["text"], purpose=case["purpose"], skill_line=skill_line)


def write_sources(case: dict, cwd: Path) -> None:
    d = cwd / "sources"
    d.mkdir()
    for i, s in enumerate(case["sources"], 1):
        (d / f"doc-{i:02d}.txt").write_text(f"【資料名】{s['name']}【版】{s['version']}\n" + "\n".join(s["lines"]) + "\n", encoding="utf-8")


def extract_json(text: str):
    """最後の ```json ブロック(無ければ最後の {...})のうち、findings を持つものを返す。"""
    cands = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", flags=re.S)
    if not cands:
        cands = re.findall(r"(\{\s*\"findings\".*\})", text or "", flags=re.S)
    for c in reversed(cands):
        try:
            d = json.loads(c)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("findings"), list):
            return d
    return None


def judge(case: dict, parsed) -> dict:
    """1回の実行を採点する。parsed が None(JSONが取れない)なら不合格。

    correct の課題は『対象語(gold.target)を含む finding が全て ok』を合格とする(課題集の規則どおり)。対象語以外への指摘は合否に数えず、
    extra_flags として別に数える。初版の採点コードは全 finding を対象にしていて、この規則と食い違っていた(dev の結果を見て直した。
    厳しい方の数え方は extra_flags と false_flag_any で残してある)。
    """
    fs = [f for f in (parsed or {}).get("findings", []) if isinstance(f, dict) and f.get("verdict") in VERDICTS]
    if parsed is None or (parsed["findings"] and not fs):
        return {"pass": False, "pass_alt": False, "format_ok": False, "invention": False, "false_flag": False, "false_flag_any": False,
                "extra_flags": 0, "len_ratio": None}
    gold, kind = case["gold"], case["kind"]
    props = " ".join(str(f.get("proposal") or "") for f in fs)
    invention = any(re.search(p, props) for p in gold["forbidden"])
    on_target = [f for f in fs if any(t in str(f.get("target") or "") for t in gold["target"])]
    rel = on_target or fs
    if kind == "misuse":
        accept = "|".join(f"(?:{a})" for a in gold["accept"])
        ok = any(f["verdict"] == "misuse" and (not accept or re.search(accept, str(f.get("proposal") or ""))) for f in rel)
    elif kind in ("ambiguity", "mismatch"):
        ok = any(f["verdict"] in gold["verdict_in"] for f in rel) and not any(f["verdict"] == "misuse" for f in rel)
    else:   # correct: 対象語についての finding が全て ok(対象語についての finding が無いのも合格)
        ok = all(f["verdict"] == "ok" for f in on_target)
    plen = sum(len(str(f.get("proposal") or "")) for f in fs)
    # 感度分析(事後): 対象語の文字列の一致に頼らず、ambiguity/mismatch は全 finding を対象にする。結果を見た後に加えた
    ok_alt = (any(f["verdict"] in gold["verdict_in"] for f in fs) and not any(f["verdict"] == "misuse" for f in fs)) if kind in ("ambiguity", "mismatch") else ok
    return {"pass": bool(ok and not invention), "pass_alt": bool(ok_alt and not invention), "format_ok": True, "invention": invention,
            "false_flag": kind == "correct" and not ok,
            "false_flag_any": kind == "correct" and any(f["verdict"] != "ok" for f in fs),
            "extra_flags": sum(f["verdict"] != "ok" for f in fs if f not in on_target) if kind == "correct" else 0,
            "len_ratio": round(plen / len(case["text"]), 2) if plen else None}


def parse_stream(lines) -> dict:
    """stream-json から、最終テキスト・Skill呼び出し・費用等を取る。"""
    out = {"text": "", "skills": [], "turns": None, "cost_usd": None, "duration_ms": None, "is_error": None}
    for ln in lines:
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for c in ev.get("message", {}).get("content", []) or []:
                if c.get("type") == "tool_use" and c.get("name") == "Skill":
                    out["skills"].append((c.get("input") or {}).get("skill"))
        elif ev.get("type") == "result":
            out.update(text=ev.get("result") or "", turns=ev.get("num_turns"), cost_usd=ev.get("total_cost_usd"),
                       duration_ms=ev.get("duration_ms"), is_error=ev.get("is_error"))
    return out


def run_one(case: dict, condition: str, skill_dir, model, timeout: int) -> dict:
    cmd = ["claude", "-p", prompt_for(case, condition), "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--strict-mcp-config", "--setting-sources", "project", "--allowedTools", "Skill Read Write Bash(python3:*)"]
    if condition == "baseline":
        cmd += ["--disable-slash-commands"]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="ctr-e2e-") as td:
        cwd = Path(td)
        write_sources(case, cwd)
        if condition == "skill":
            shutil.copytree(skill_dir, cwd / ".claude" / "skills" / Path(skill_dir).resolve().name, ignore=shutil.ignore_patterns("__pycache__"))
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        timer = threading.Timer(timeout, p.kill)
        timer.start()
        try:
            stream = parse_stream(iter(p.stdout.readline, ""))
        finally:
            timer.cancel()
            p.kill()
            p.wait()
    parsed = extract_json(stream["text"])
    return {"parsed": parsed, "skill_called": any(s and (s == SKILL or s.endswith(":" + SKILL)) for s in stream["skills"]),
            "turns": stream["turns"], "cost_usd": stream["cost_usd"], "duration_ms": stream["duration_ms"], "is_error": stream["is_error"],
            "timed_out": time.time() - t0 >= timeout, "seconds": round(time.time() - t0, 1), "text_chars": len(stream["text"])}


def validate(data: dict) -> list:
    errs, seen = [], set()
    for c in data.get("cases", []):
        i = c.get("id")
        if not i or i in seen:
            errs.append(f"idが無い・重複: {i}")
        seen.add(i)
        if c.get("kind") not in ("misuse", "ambiguity", "correct", "mismatch"):
            errs.append(f"{i}: kind")
        if c.get("split") not in SPLITS:
            errs.append(f"{i}: split")
        if not c.get("text") or not c.get("sources") or not all(s.get("lines") for s in c["sources"]):
            errs.append(f"{i}: text/sources が空")
        g = c.get("gold", {})
        if not g.get("verdict_in") or not g.get("target") or "forbidden" not in g or "accept" not in g:
            errs.append(f"{i}: gold の項目が足りない")
        else:
            for pat in g["accept"] + g["forbidden"]:
                try:
                    re.compile(pat)
                except re.error:
                    errs.append(f"{i}: 正規表現が不正 {pat!r}")
    return errs


def run(data: dict, split: str, runs: int, conditions, skill_dir, model, workers: int, timeout: int) -> list:
    jobs = [(c, cond, r) for c in data["cases"] if split in ("all", c["split"]) for cond in conditions for r in range(1, runs + 1)]

    def one(job):
        c, cond, r = job
        return {"id": c["id"], "condition": cond, "run": r, **run_one(c, cond, skill_dir, model, timeout)}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, jobs))


def score(data: dict, results: list, split: str) -> dict:
    cases = {c["id"]: c for c in data["cases"] if split in ("all", c["split"])}
    per = {}
    for r in results:
        if r["id"] not in cases:
            continue
        j = judge(cases[r["id"]], r.get("parsed"))
        per.setdefault((r["id"], r["condition"]), []).append({**j, "skill_called": r.get("skill_called"), "seconds": r.get("seconds"),
                                                             "cost_usd": r.get("cost_usd"), "turns": r.get("turns")})
    conds = sorted({c for _, c in per})
    by_cond = {}
    for cond in conds:
        rows = [(cid, v) for (cid, c), v in per.items() if c == cond]
        runs_ = [x for _, v in rows for x in v]
        kinds = {}
        for cid, v in rows:
            k = cases[cid]["kind"]
            d = kinds.setdefault(k, [0, 0])
            d[0] += sum(x["pass"] for x in v)
            d[1] += len(v)
        lr = [x["len_ratio"] for x in runs_ if x["len_ratio"] is not None]
        costs = [x["cost_usd"] for x in runs_ if x["cost_usd"] is not None]
        by_cond[cond] = {
            "runs": len(runs_), "pass": {"k": sum(x["pass"] for x in runs_), "n": len(runs_), "wilson_95": wilson(sum(x["pass"] for x in runs_), len(runs_))},
            "pass_alt_post_hoc": sum(x["pass_alt"] for x in runs_),
            "by_kind": {k: {"pass": v[0], "n": v[1]} for k, v in sorted(kinds.items())},
            "format_failures": sum(not x["format_ok"] for x in runs_),
            "invention": sum(x["invention"] for x in runs_),
            "false_flag_on_correct": {"k": sum(x["false_flag"] for x in runs_), "n": sum(1 for cid, v in rows for x in v if cases[cid]["kind"] == "correct")},
            "false_flag_any_on_correct": sum(x["false_flag_any"] for x in runs_),
            "extra_flags_on_correct": sum(x["extra_flags"] for x in runs_),
            "len_ratio_median": round(statistics.median(lr), 2) if lr else None,
            "skill_called": sum(bool(x["skill_called"]) for x in runs_), "mean_seconds": round(statistics.mean(x["seconds"] for x in runs_), 1) if runs_ else None,
            "mean_cost_usd": round(statistics.mean(costs), 3) if costs else None}
    out = {"split": split, "cases": len(cases), "conditions": by_cond}
    if "baseline" in by_cond and "skill" in by_cond:
        diffs, imp, wor = {}, 0, 0
        for cid in cases:
            a, b = per.get((cid, "baseline")), per.get((cid, "skill"))
            if not a or not b:
                continue
            d = sum(x["pass"] for x in b) / len(b) - sum(x["pass"] for x in a) / len(a)
            diffs[cid] = round(d, 3)
            imp += d > 0
            wor += d < 0
        mean = round(sum(diffs.values()) / len(diffs), 3) if diffs else None
        base, skl = by_cond["baseline"], by_cond["skill"]
        ff_b = base["false_flag_on_correct"]["k"] / base["false_flag_on_correct"]["n"] if base["false_flag_on_correct"]["n"] else 0
        ff_s = skl["false_flag_on_correct"]["k"] / skl["false_flag_on_correct"]["n"] if skl["false_flag_on_correct"]["n"] else 0
        alt = []
        for cid in cases:
            a, b = per.get((cid, "baseline")), per.get((cid, "skill"))
            if a and b:
                alt.append(sum(x["pass_alt"] for x in b) / len(b) - sum(x["pass_alt"] for x in a) / len(a))
        out["paired_alt_post_hoc"] = {"mean_diff": round(sum(alt) / len(alt), 3) if alt else None, "improved": sum(d > 0 for d in alt), "worsened": sum(d < 0 for d in alt)}
        out["paired"] = {"mean_diff": mean, "improved": imp, "worsened": wor, "unchanged": len(diffs) - imp - wor,
                         "sign_test_p_two_sided": round(binom_two_sided(imp, imp + wor), 4), "per_case_diff": diffs}
        out["criteria"] = {"mean_diff_min": 0.10, "false_flag_increase_max": 0.10, "invention_not_more_than_baseline": True}
        out["pass"] = {"accuracy": bool(mean is not None and mean >= 0.10 and imp > wor),
                       "false_flag": ff_s - ff_b <= 0.10, "invention": skl["invention"] <= base["invention"]}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--data", type=Path, default=DATA)
    r = sub.add_parser("run")
    r.add_argument("--data", type=Path, default=DATA)
    r.add_argument("--split", choices=[*SPLITS, "all"], required=True)
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--conditions", default="baseline,skill")
    r.add_argument("--skill-dir", type=Path, default=ROOT / "skill" / SKILL)
    r.add_argument("--model")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--timeout", type=int, default=600)
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--data", type=Path, default=DATA)
    s.add_argument("--results", type=Path, action="append", required=True)
    s.add_argument("--split", choices=[*SPLITS, "all"], required=True)
    s.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    data = json.loads(a.data.read_text(encoding="utf-8"))
    errs = validate(data)
    if a.cmd == "validate" or errs:
        print(json.dumps({"ok": not errs, "errors": errs, "cases": len(data.get("cases", []))}, ensure_ascii=False))
        return 1 if errs else 0
    if a.cmd == "run":
        res = run(data, a.split, a.runs, a.conditions.split(","), a.skill_dir, a.model, a.workers, a.timeout)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"model": a.model or "default", "split": a.split, "runs": a.runs, "skill_dir": Path(a.skill_dir).resolve().name,
                                     "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({"ok": True, "results": len(res), "out": str(a.out)}, ensure_ascii=False))
        return 0
    results = [x for p in a.results for x in json.loads(p.read_text(encoding="utf-8"))["results"]]
    rep = score(data, results, a.split)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "paired"} | ({"paired": {k: v for k, v in rep["paired"].items() if k != "per_case_diff"}} if "paired" in rep else {}), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
