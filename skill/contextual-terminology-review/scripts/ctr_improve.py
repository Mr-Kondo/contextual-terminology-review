"""更新案・新旧比較・明示的採用・復元・集計・抽出・回帰例化・未使用評価の管理。

AIの提案や採点は採用承認にならない。採用は、人の名前・理由・評価・直前の版の照合がそろった場合だけ。
集計は分子・分母・欠測を分け、分母0は未評価にする。
"""
from __future__ import annotations

import math
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from ctr_common import CtrError, new_id, read_json, sha256_obj, utcnow, valid_id, write_json
from ctr_log import (collect_events, effective_feedback, iter_runs, load_policy)

CAUSES = ("definition_gap", "retrieval", "judgment", "audience", "unagreed")
ITEM_KINDS = ("known_failure", "previously_ok", "no_fix_needed", "new")
UNDER_TEST = {"terms_version", "skill_version"}  # 比較で変えてよい条件。ほかが違えば交絡


def standard_dir(imp: Path) -> Path:
    return imp / "standard"


def current_version(imp: Path) -> dict:
    p = standard_dir(imp) / "terms.json"
    if not p.exists():
        return {"hash": "none", "terms": {"schema_version": 1, "terms": []}}
    obj = read_json(p)
    return {"hash": sha256_obj(obj), "terms": obj}


def init_standard(imp: Path, terms: Optional[dict] = None) -> dict:
    p = standard_dir(imp) / "terms.json"
    obj = terms or {"schema_version": 1, "terms": []}
    res = write_json(p, obj)
    h = sha256_obj(obj)
    write_json(standard_dir(imp) / "versions" / f"{h[:16]}.json", obj)
    return {"version": h, "write": res}


# ---------------------------------------------------------------- 更新案

def propose_create(imp: Path, *, cause: str, scope: dict, summary: str, evidence: list, diff: list,
                   base_version: str, keep_conditions: list, forbidden_changes: list, evaluation_plan: str,
                   hypothesis: bool = False) -> dict:
    if cause not in CAUSES:
        raise CtrError("invalid_option", "cause")
    if cause == "unagreed" and diff:
        raise CtrError("unagreed_cannot_change_terms",
                       "責任・成果物が未合意の場合は確認事項にする。一般用語の定義は変更しない")
    if cause != "unagreed" and not diff:
        raise CtrError("empty_diff")
    if not (keep_conditions and forbidden_changes):
        raise CtrError("missing_keep_conditions", "保持条件と禁止変更が必要です")
    for d in diff:
        if d.get("op") not in ("add", "update", "remove") or not isinstance(d.get("term"), dict) or "id" not in d["term"]:
            raise CtrError("invalid_diff")
    pid = new_id("prop")
    rec = {"schema_version": 1, "proposal_id": pid, "created_at": utcnow(), "cause": cause, "scope": scope,
           "summary": summary, "evidence": evidence, "diff": diff, "diff_sha256": sha256_obj(diff),
           "expected_base_version": base_version, "keep_conditions": keep_conditions,
           "forbidden_changes": forbidden_changes, "evaluation_plan": evaluation_plan,
           "hypothesis": hypothesis, "target": "confirmation_item" if cause == "unagreed" else "terms",
           "status": "proposed", "derived_from": [e["run_id"] for e in evidence if isinstance(e, dict) and "run_id" in e]}
    return {"proposal_id": pid, "write": write_json(imp / "proposals" / f"{pid}.json", rec)}


def proposal_status(imp: Path, pid: str) -> str:
    for p in (imp / "decisions").glob("*.json") if (imp / "decisions").exists() else []:
        d = read_json(p)
        if d.get("proposal_id") == pid and d.get("type") == "adopt":
            return "adopted"
    return "proposed"


# ---------------------------------------------------------------- 新旧比較

def evaluate_compare(imp: Path, results: dict, proposal_id: str) -> dict:
    prop = read_json(imp / "proposals" / f"{valid_id(proposal_id)}.json")
    cond = results.get("conditions") or {}
    cur, cand = cond.get("current") or {}, cond.get("candidate") or {}
    diffs = sorted(k for k in (set(cur) | set(cand)) - UNDER_TEST if cur.get(k) != cand.get(k))
    items = results.get("items") or []
    blocked, reasons = False, []
    if diffs:
        blocked = True
        reasons.append({"code": "confounded", "keys": diffs,
                        "detail": "モデル・資料・生成設定・採点条件が違う。Skillだけの効果とは言えない。同条件で再評価する"})
    fails = [i["id"] for i in items if (i.get("candidate") or {}).get("meaning") == "fail"]
    unknown = [i["id"] for i in items if (i.get("candidate") or {}).get("meaning") == "unknown"]
    if fails:
        blocked = True
        reasons.append({"code": "meaning_change_fail", "items": fails, "detail": "意味保持の不合格は読みやすさ等の点数で相殺しない"})
    if unknown:
        blocked = True
        reasons.append({"code": "meaning_unknown", "items": unknown})
    kinds = {k: [i for i in items if i.get("kind") == k] for k in ITEM_KINDS}
    for i in items:
        if i.get("kind") not in ITEM_KINDS:
            raise CtrError("invalid_item_kind")
    fixed = [i["id"] for i in kinds["known_failure"]
             if (i["current"].get("meaning") == "fail") and i["candidate"].get("meaning") == "pass"]
    still = [i["id"] for i in kinds["known_failure"] if i["candidate"].get("meaning") != "pass"]
    over = [i["id"] for i in kinds["no_fix_needed"] if (i["candidate"].get("over_flag") is True)]
    if over:
        blocked = True
        reasons.append({"code": "over_correction", "items": over})
    if not kinds["no_fix_needed"] or not kinds["previously_ok"]:
        reasons.append({"code": "coverage_gap", "detail": "修正不要例と正しく処理できていた例を含める"})
        blocked = True
    verdict = "blocked" if blocked else ("improved" if fixed and not still else ("unchanged" if not fixed else "partial"))
    rec = {"schema_version": 1, "evaluation_id": new_id("eval"), "proposal_id": proposal_id, "created_at": utcnow(),
           "proposal_sha256": prop["diff_sha256"], "base_version": cond.get("base_version"),
           "conditions": cond, "order": results.get("order"), "repeats": results.get("repeats"),
           "verdict": verdict, "block_reasons": reasons,
           "counts": {"known_failure": len(kinds["known_failure"]), "fixed": len(fixed), "still_failing": len(still),
                      "previously_ok": len(kinds["previously_ok"]), "no_fix_needed": len(kinds["no_fix_needed"])},
           "readability_note": "読みやすさ・自然さの評点は参考表示。意味保持の合否とは別で、合否に加算しない",
           "holdout_evaluation": results.get("holdout_evaluation", "not_run"),
           "scope_of_claim": "既知例の回帰検査。未使用評価が not_run の間は、実務性能・一般化を示さない"}
    return {"evaluation_id": rec["evaluation_id"], "verdict": verdict, "reasons": reasons,
            "write": write_json(imp / "evaluations" / f"{rec['evaluation_id']}.json", rec)}


# ---------------------------------------------------------------- 採用・復元

def _apply_diff(terms: dict, diff: list) -> dict:
    items = {t["id"]: t for t in terms["terms"]}
    for d in diff:
        tid = d["term"]["id"]
        if d["op"] == "add":
            if tid in items:
                raise CtrError("diff_conflict", "add 対象が既に存在")
            items[tid] = d["term"]
        elif d["op"] == "update":
            if tid not in items:
                raise CtrError("diff_conflict", "update 対象がない")
            items[tid] = d["term"]
        else:
            if tid not in items:
                raise CtrError("diff_conflict", "remove 対象がない")
            del items[tid]
    return {**terms, "terms": [items[k] for k in sorted(items)]}


def adopt(imp: Path, proposal_id: str, evaluation_id: str, *, approved_by: str, reason: str, confirmed: bool) -> dict:
    """人の明示的な採用。AIや自動採点の結果だけでは呼べない(confirmed と approved_by が要る)。"""
    if not confirmed or not approved_by.strip() or not reason.strip():
        raise CtrError("approval_required", "採用には人の名前・理由・--i-approve が必要です")
    prop = read_json(imp / "proposals" / f"{valid_id(proposal_id)}.json")
    ev = read_json(imp / "evaluations" / f"{valid_id(evaluation_id)}.json")
    if prop["hypothesis"] or prop["cause"] == "unagreed":
        raise CtrError("not_adoptable", "仮説・未合意の候補は採用できない")
    if proposal_status(imp, proposal_id) == "adopted":
        raise CtrError("already_adopted")
    if ev["proposal_id"] != proposal_id or ev["proposal_sha256"] != prop["diff_sha256"]:
        raise CtrError("approval_not_for_this_diff", "評価・承認は別の差分に使い回せない")
    if ev["verdict"] != "improved":
        raise CtrError("evaluation_not_passing", f"verdict={ev['verdict']}")
    cur = current_version(imp)
    if prop["expected_base_version"] != cur["hash"] or ev.get("base_version") != cur["hash"]:
        raise CtrError("base_version_conflict", "評価後に基準の版が変わった。再確認・再評価が必要")
    new_terms = _apply_diff(cur["terms"], prop["diff"])
    new_hash = sha256_obj(new_terms)
    write_json(standard_dir(imp) / "versions" / f"{new_hash[:16]}.json", new_terms, overwrite=True)
    write_json(standard_dir(imp) / "versions" / f"{cur['hash'][:16]}.json", cur["terms"], overwrite=True)
    term_path = standard_dir(imp) / "terms.json"
    write_json(term_path, new_terms, overwrite=True)
    dec = {"schema_version": 1, "decision_id": new_id("dec"), "type": "adopt", "proposal_id": proposal_id,
           "evaluation_id": evaluation_id, "approved_by": approved_by, "reason": reason, "at": utcnow(),
           "from_version": cur["hash"], "to_version": new_hash, "diff_sha256": prop["diff_sha256"],
           "index_rebuild_required": True}
    try:
        write_json(imp / "decisions" / f"{dec['decision_id']}.json", dec)
    except CtrError:
        write_json(term_path, cur["terms"], overwrite=True)  # 判断記録が残せなければ元に戻す
        raise
    return dec


def restore(imp: Path, to_version: str, *, approved_by: str, reason: str, confirmed: bool) -> dict:
    if not confirmed or not approved_by.strip() or not reason.strip():
        raise CtrError("approval_required")
    snaps = list((standard_dir(imp) / "versions").glob(f"{to_version[:16]}*.json"))
    if len(snaps) != 1:
        raise CtrError("version_not_found")
    target = read_json(snaps[0])
    cur = current_version(imp)
    write_json(standard_dir(imp) / "versions" / f"{cur['hash'][:16]}.json", cur["terms"], overwrite=True)
    write_json(standard_dir(imp) / "terms.json", target, overwrite=True)
    dec = {"schema_version": 1, "decision_id": new_id("dec"), "type": "restore", "approved_by": approved_by,
           "reason": reason, "at": utcnow(), "from_version": cur["hash"], "to_version": sha256_obj(target),
           "index_rebuild_required": True}
    write_json(imp / "decisions" / f"{dec['decision_id']}.json", dec)  # 履歴は改変せず追記する
    return dec


# ---------------------------------------------------------------- 回帰例化・未使用評価

def _registry_path(gold: Path) -> Path:
    return gold / "registry.json"


def holdout_register(gold: Path, case_ids: list) -> dict:
    p = _registry_path(gold)
    reg = read_json(p) if p.exists() else {"cases": {}}
    for c in case_ids:
        reg["cases"].setdefault(valid_id(c), {"status": "unused"})
    return write_json(p, reg, overwrite=True)


def holdout_status(gold: Path) -> dict:
    p = _registry_path(gold)
    reg = read_json(p) if p.exists() else {"cases": {}}
    counts: dict = {}
    for v in reg["cases"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    return {"counts": counts, "note": "used_for_improvement は以後、未使用評価に数えない"}


def mark_used_for_improvement(gold: Path, case_id: str, why: str) -> None:
    p = _registry_path(gold)
    reg = read_json(p) if p.exists() else {"cases": {}}
    ent = reg["cases"].setdefault(case_id, {"status": "unused"})
    ent.update({"status": "used_for_improvement", "moved_at": utcnow(), "why": why})
    write_json(p, reg, overwrite=True)


def regression_add(imp: Path, case: dict, gold: Optional[Path] = None) -> dict:
    """確認済みの問題だけを開発用の回帰例にする。保留・好み・未合意は拒否する。"""
    need = ("case_id", "classification", "reviewer", "reason", "original_input_sha256", "location", "keep_conditions",
            "forbidden_changes", "scope", "derived_from")
    missing = [k for k in need if not case.get(k)]
    if missing:
        raise CtrError("regression_fields_missing", ",".join(missing))
    if case["classification"] != "confirmed_problem":
        raise CtrError("regression_requires_confirmed", "確定した問題だけを回帰例にする(保留・好み・未合意・未確認は不可)")
    cid = valid_id(case["case_id"])
    rec = {**case, "schema_version": 1, "added_at": utcnow(), "ex_holdout": False, "evaluation_eligibility": "development_only"}
    if gold:
        reg = read_json(_registry_path(gold)) if _registry_path(gold).exists() else {"cases": {}}
        if cid in reg["cases"] and reg["cases"][cid]["status"] == "unused":
            mark_used_for_improvement(gold, cid, "regression_added")
            rec["ex_holdout"] = True
    return {"write": write_json(imp / "regressions" / f"{cid}.json", rec), "ex_holdout": rec["ex_holdout"]}


def check_isolation(gold: Path, agent_roots: list) -> dict:
    g = gold.resolve()
    overlap = [str(a) for a in agent_roots if str(g).startswith(str(Path(a).resolve())) or str(Path(a).resolve()).startswith(str(g))]
    mode = oct(g.stat().st_mode & 0o777) if g.exists() else None
    return {"separate_path": not overlap, "overlapping_agent_roots": overlap, "gold_mode": mode,
            "access_isolated": "not_demonstrated",
            "note": "フォルダを分けただけではアクセス隔離を達成したことにならない。レビューを生成・改善するAgentの"
                    "セッションから正解へ到達できないこと(別アカウント・別セッション・読み取り権限の制限)を運用で確認する"}


# ---------------------------------------------------------------- 集計

def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def _metric(mid: str, num: int, den: int, indep: int, note: str = "", min_n: int = 20) -> dict:
    m = {"id": mid, "numerator": num, "denominator": den, "value": (num / den) if den else None,
         "status": "evaluated" if den else "unevaluated(分母0)", "independent_tasks": indep, "note": note}
    # 区間は、分母が独立課題数と一致し、十分な件数がある場合だけ。反復を独立例にしない
    m["wilson_95"] = wilson(num, den) if den and den == indep and den >= min_n else None
    return m


def metrics(runtime: Optional[Path], imp: Optional[Path], known_total_usage: Optional[int] = None) -> dict:
    events: dict = {}
    sources = {}
    if imp and (imp / "inbox").exists():
        for p in sorted((imp / "inbox").glob("*/events/*.json")):
            events[p.stem] = read_json(p)
            sources[p.stem] = "shared"
    if runtime:
        for ev in collect_events(runtime):
            events[ev["event_id"]] = ev  # 実行先の原本を優先
            sources[ev["event_id"]] = "local"
    evs = list(events.values())
    starts = [e for e in evs if e["type"] == "run_started"]
    group = {e["run_id"]: e.get("task_group", e["run_id"]) for e in starts}
    env = {e["run_id"]: e.get("host_environment", "unknown") for e in starts}
    terminals = {e["run_id"]: e for e in evs if e["type"] in ("completed", "failed")}
    fb = effective_feedback([e for e in evs if e["type"] == "feedback"])
    human = {k: v for k, v in fb.items() if k[2] == "human"}
    ai_susp = [v for k, v in fb.items() if k[2] == "ai_suspicion"]

    def tasks(items):
        return len({group.get(k[0], k[0]) for k in items})

    def answered(field):
        return {k: v for k, v in human.items() if v.get(field) is not None}

    out_metrics = []
    comp = [e for e in terminals.values() if e["type"] == "completed" and "ref_counts" in e]
    checked = sum(e["ref_counts"].get("checked", 0) for e in comp)
    bad = sum(e["ref_counts"].get("fail", 0) for e in comp)
    out_metrics.append(_metric("ref_defect", bad, checked, len({group.get(e["run_id"], e["run_id"]) for e in comp}),
                               "機械検査で不備のあった参照/検査した参照。意味適合とは別"))
    v = answered("validity")
    out_metrics.append(_metric("unnecessary_fix", sum(1 for x in v.values() if x["validity"] == "ng"), len(v), tasks(v),
                               "人が不適切と確認した指摘/人が確認した指摘。unknownは分母に含め、欠測は別掲"))
    i = answered("intent")
    out_metrics.append(_metric("harmful_meaning_change", sum(1 for x in i.values() if x["intent"] == "changed"), len(i), tasks(i),
                               "意図が変わった案/人が検証した案"))
    r = answered("receiver")
    out_metrics.append(_metric("receiver_confirmation", sum(1 for x in r.values() if x["receiver"] == "confirmed"), len(r), tasks(r),
                               "受け手との確認ができた指摘/確認結果のある指摘。理解を実測した値ではない(別途、質問・採点が必要)"))
    out_metrics.append({"id": "recurrence", "status": "unevaluated(評価入力なし)", "numerator": 0, "denominator": 0, "value": None})
    findings_total = sum(len(e.get("findings", [])) for e in comp)
    answered_total = len(v)
    run_ids = set(group)
    shared_runs = {e["run_id"] for k, e in events.items() if sources[k] == "shared"}
    effort: dict = {}
    for e in evs:
        if e["type"] == "effort":
            wk = datetime.strptime(e["created_at"], "%Y-%m-%dT%H:%M:%SZ").strftime("%G-W%V")
            b = effort.setdefault(wk, {"self_minutes": 0, "collaborator_minutes": 0, "by_category": {}})
            b[f"{e['who']}_minutes"] += e["minutes"]
            if e["who"] == "self":
                b["by_category"][e["category"]] = b["by_category"].get(e["category"], 0) + e["minutes"]
    for b in effort.values():
        b["over_30min_budget"] = b["self_minutes"] > 30
    by_env: dict = {}
    for rid in run_ids:
        by_env[env[rid]] = by_env.get(env[rid], 0) + 1
    return {
        "populations": {"runs_started_collected": len(run_ids), "runs_terminated": len(terminals),
                        "shared_runs": len(shared_runs), "human_confirmed_findings": len(human),
                        "independent_tasks_with_human_confirmation": tasks(human)},
        "metrics": out_metrics,
        "missingness": {"findings_recorded": findings_total, "findings_with_validity_answer": answered_total,
                        "unanswered_validity": max(findings_total - answered_total, 0),
                        "ai_suspicion_events": len(ai_susp), "note": "未回答を肯定にしない。AI疑義と人の確認は別集計"},
        "collection_rate": ({"value": len(run_ids) / known_total_usage, "denominator": known_total_usage}
                            if known_total_usage else {"value": None, "reason": "利用総数が未知のため収集率は算出しない"}),
        "runs_by_environment": by_env,
        "effort": effort,
        "notes": ["訂正イベントと再取り込みは独立例数に加えない(有効な最新評価のみ集計)", "採用率は正確性の指標ではない"],
    }


def sample_candidates(runtime: Path, imp: Optional[Path], *, seed: int, n_no_finding: int, n_high_risk: int, n_random: int) -> dict:
    """人の確認候補を、記録した条件とseedで抽出する。指摘なし例も含め、抽出されなかった例を正しいとみなさない。"""
    evs = collect_events(runtime)
    fb_runs = {e["run_id"] for e in evs if e["type"] == "feedback"}
    done = {e["run_id"]: e for e in evs if e["type"] == "completed"}
    pools = {"no_finding": [], "high_risk": [], "random": []}
    for rid, e in sorted(done.items()):
        if rid in fb_runs:
            continue
        fs = e.get("findings", [])
        risky = e.get("ref_counts", {}).get("fail", 0) > 0 or any(f["effective"] == "needs_confirmation" for f in fs)
        pools["no_finding" if not fs else "high_risk" if risky else "random"].append(rid)
    rng = random.Random(seed)
    want = {"no_finding": n_no_finding, "high_risk": n_high_risk, "random": n_random}
    chosen = {k: rng.sample(v, min(want[k], len(v))) for k, v in pools.items()}
    rec = {"schema_version": 1, "sample_id": new_id("smp"), "created_at": utcnow(), "seed": seed,
           "criteria": {"exclude": "既に人のフィードバックがある実行", "no_finding": "指摘0件の完了実行",
                        "high_risk": "参照の不備、または要確認に下げた判断を含む", "random": "それ以外"},
           "pool_sizes": {k: len(v) for k, v in pools.items()}, "requested": want, "chosen": chosen,
           "unselected_are_not_assumed_correct": True,
           "note": "高リスク優先抽出と無作為抽出は別集計。収集済みの記録は全利用の代表とは言えない"}
    if imp:
        write_json(imp / "evaluations" / "samples" / f"{rec['sample_id']}.json", rec)
    return rec


def data_compat(imp: Path, index_meta: Optional[Path]) -> dict:
    from ctr_common import skill_version
    cur = current_version(imp)
    out = {"skill_version": skill_version(), "standard_terms_version": cur["hash"][:16], "index": None}
    if index_meta and Path(index_meta).exists():
        meta = read_json(Path(index_meta))
        stale = meta.get("terms_sha256") != cur["hash"]
        out["index"] = {"built_with_skill": meta.get("skill_version"), "terms_sha256": (meta.get("terms_sha256") or "")[:16],
                        "stale": stale,
                        "skill_changed_since_build": meta.get("skill_version") != skill_version(),
                        "message": "索引が古い。最新の索引として使わず再作成する" if stale else "索引は現在の基準データと一致"}
    else:
        out["index"] = {"present": False, "message": "索引なし(一致検索のみ)"}
    return out
