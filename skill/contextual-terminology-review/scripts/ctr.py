#!/usr/bin/env python3
"""contextual-terminology-review の共通管理スクリプト。出力はJSON。

  ctr.py check refs --review review.json --sources sources.json     引用・参照の機械検査と出典一覧の生成
  ctr.py store init|set-policy|status --runtime-root ABS
  ctr.py record start|finish|fail ...                               実行の記録(保存後に再読込して確認)
  ctr.py feedback add|time ...                                      人のフィードバック・本人の負担時間
  ctr.py check store|runs|sample|isolation|data ...
  ctr.py export / import                                            許可項目だけのファイル書き出し・取り込み
  ctr.py propose create|list / evaluate compare|adopt|restore|metrics|regression|holdout
  ctr.py search exact|build-index|ruri / pdf extract
  ctr.py blind prepare|score / comprehension prepare|check|score
  ctr.py delete plan|apply

保存先は --runtime-root / --improvement-root / --gold-root(または CTR_RUNTIME_ROOT など)で絶対パスを指定する。
既定の保存先は持たない。終了コード: 0 成功 / 1 検査で不備 / 2 使い方 / 3 保存不能・未設定 / 4 共有許可なし。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctr_common import CtrError, read_json, skill_version, write_json  # noqa: E402

EXIT = {"storage_unwritable": 3, "verify_failed": 3, "storage_unconfigured": 3, "storage_path_not_absolute": 3,
        "sharing_not_configured": 4, "permission_not_granted": 4, "approval_required": 4}


def out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return code


def roots(a, need=("runtime",)):
    from ctr_log import resolve_root
    r = {}
    if "runtime" in need:
        r["runtime"] = resolve_root(getattr(a, "runtime_root", None), "CTR_RUNTIME_ROOT", "runtime_root")
    if "improvement" in need:
        r["improvement"] = resolve_root(getattr(a, "improvement_root", None), "CTR_IMPROVEMENT_ROOT", "improvement_root")
    if "gold" in need:
        r["gold"] = resolve_root(getattr(a, "gold_root", None), "CTR_GOLD_ROOT", "evaluation_gold_root")
    return r


def load_review(args):
    from ctr_refs import Review, load_registry
    from pydantic import ValidationError
    try:
        review = Review.model_validate(read_json(Path(args.review)))
    except ValidationError as exc:
        raise CtrError("invalid_review", f"{exc.error_count()} 件のスキーマ違反") from exc
    return review, load_registry(args.sources)


def cmd_check(a):
    if a.what == "refs":
        from ctr_refs import review_check
        review, reg = load_review(a)
        rep = review_check(review, reg)
        if a.footer_only:
            print("\n".join(rep["footer"]))
            return 1 if rep["errors"] else 0
        return out(rep, 1 if rep["errors"] else 0)
    if a.what == "store":
        from ctr_log import check_store
        res = check_store(roots(a)["runtime"])
        return out(res, 0 if res["ok"] else 1)
    if a.what == "runs":
        from ctr_log import check_runs
        return out(check_runs(roots(a)["runtime"], a.in_progress_minutes))
    if a.what == "sample":
        from ctr_improve import sample_candidates
        r = roots(a, ("runtime", "improvement"))
        return out(sample_candidates(r["runtime"], r["improvement"], seed=a.seed, n_no_finding=a.n_no_finding,
                                     n_high_risk=a.n_high_risk, n_random=a.n_random))
    if a.what == "isolation":
        from ctr_improve import check_isolation
        return out(check_isolation(roots(a, ("gold",))["gold"], a.agent_root or []))
    if a.what == "data":
        from ctr_improve import data_compat
        return out(data_compat(roots(a, ("improvement",))["improvement"], a.index_meta))
    raise CtrError("invalid_option")


def cmd_store(a):
    from ctr_log import load_policy, set_policy, store_init
    root = roots(a)["runtime"]
    if a.what == "init":
        return out(store_init(root, a.project_opaque_id))
    if a.what == "set-policy":
        fields = a.share_fields.split(",") if a.share_fields else None
        return out(set_policy(root, raw_text=a.raw_text, share_fields=fields, share_scope=a.share_scope, granted_by=a.granted_by))
    return out(load_policy(root))


def cmd_record(a):
    from ctr_log import record_finish, record_start, summarize_review
    root = roots(a)["runtime"]
    if a.what == "start":
        return out(record_start(root, host=a.host, route=a.route, model_id=a.model_id,
                                domains=a.domains.split(",") if a.domains else [], task_group=a.task_group,
                                terms_file=a.terms_file, index_meta=a.index_meta, target_text_file=a.target_text_file))
    if a.what == "fail":
        return out(record_finish(root, a.run_id, failed_with=a.error_class))
    summary, private = None, None
    if a.review:
        from ctr_refs import review_check
        review, reg = load_review(a)
        rep = review_check(review, reg)
        summary = summarize_review(rep, review)
        private = {"footer": rep["footer"], "findings": [f.model_dump() for f in review.findings]}
    return out(record_finish(root, a.run_id, review_summary=summary, private_output=private))


def cmd_feedback(a):
    from ctr_log import effort_add, feedback_add
    root = roots(a)["runtime"]
    if a.what == "time":
        return out(effort_add(root, category=a.category, minutes=a.minutes, who=a.who, run_id=a.run_id))
    return out(feedback_add(root, a.run_id, a.finding_id, validity=a.validity, intent=a.intent, usage=a.usage,
                            receiver=a.receiver, reason=a.reason, corrects=a.corrects, source=a.source, reviewer=a.reviewer))


def cmd_export(a):
    from ctr_log import export_package, mark_shared
    if a.mark_shared:
        return out(mark_shared(roots(a)["runtime"], a.mark_shared, a.shared_to))
    return out(export_package(roots(a)["runtime"], run_ids=a.run_id, include_exported=a.again))


def cmd_import(a):
    from ctr_log import import_package
    return out(import_package(roots(a, ("improvement",))["improvement"], Path(a.package)))


def cmd_propose(a):
    from ctr_improve import proposal_status, propose_create
    imp = roots(a, ("improvement",))["improvement"]
    if a.what == "list":
        return out([{**{k: p[k] for k in ("proposal_id", "cause", "summary", "hypothesis", "target")}, "status": proposal_status(imp, p["proposal_id"])}
                    for p in (read_json(f) for f in sorted((imp / "proposals").glob("*.json")))])
    spec = read_json(Path(a.spec))
    return out(propose_create(imp, **spec))


def cmd_evaluate(a):
    import ctr_improve as im
    r = roots(a, ("improvement",))
    imp = r["improvement"]
    if a.what == "compare":
        return out(im.evaluate_compare(imp, read_json(Path(a.results)), a.proposal))
    if a.what == "adopt":
        return out(im.adopt(imp, a.proposal, a.evaluation, approved_by=a.approved_by, reason=a.reason, confirmed=a.i_approve))
    if a.what == "restore":
        return out(im.restore(imp, a.to_version, approved_by=a.approved_by, reason=a.reason, confirmed=a.i_approve))
    if a.what == "init-standard":
        return out(im.init_standard(imp, read_json(Path(a.terms)) if a.terms else None))
    if a.what == "metrics":
        runtime = roots(a)["runtime"] if (a.runtime_root or __import__("os").environ.get("CTR_RUNTIME_ROOT")) else None
        return out(im.metrics(runtime, imp, a.known_total_usage))
    if a.what == "regression":
        gold = roots(a, ("gold",))["gold"] if a.gold_root else None
        return out(im.regression_add(imp, read_json(Path(a.case)), gold))
    if a.what == "holdout":
        gold = roots(a, ("gold",))["gold"]
        if a.register:
            return out(im.holdout_register(gold, a.register.split(",")))
        return out(im.holdout_status(gold))
    raise CtrError("invalid_option")


def cmd_search(a):
    from ctr_refs import load_registry
    import ctr_search as se
    terms = read_json(Path(a.terms))
    reg = load_registry(a.sources) if a.sources else None
    if a.what == "exact":
        return out(se.exact_search(terms, a.query, project=a.project, as_of=a.as_of))
    if a.what == "build-index":
        return out(se.build_index(terms, reg, Path(a.index_dir), model_id=a.model or se.DEFAULT_MODEL, revision=a.revision, local_files_only=a.offline))
    return out(se.ruri_search(a.query, terms, reg, Path(a.index_dir), top_k=a.top_k, local_files_only=a.offline))


def cmd_pdf(a):
    from ctr_pdf import extract_pdf
    res = extract_pdf(Path(a.pdf), a.source_id, a.version, a.title, with_layout=a.layout)
    if a.out:
        write_json(Path(a.out), res, overwrite=True)
        return out({"written": a.out, "pages": res["pages"], "pages_without_text": res["extraction"]["pages_without_text"]})
    return out(res)


def cmd_blind(a):
    import ctr_blind as bl
    if a.group == "blind":
        if a.what == "prepare":
            return out(bl.blind_prepare(read_json(Path(a.pairs)), a.readers.split(","), Path(a.out), a.seed))
        return out(bl.blind_score(read_json(Path(a.organizer)), read_json(Path(a.responses))))
    if a.what == "prepare":
        return out(bl.comprehension_prepare(read_json(Path(a.items)), a.readers.split(","), Path(a.out), a.seed))
    if a.what == "check":
        res = bl.check_single_version(Path(a.dir))
        return out(res, 0 if res["ok"] else 1)
    return out(bl.comprehension_score(read_json(Path(a.organizer)), read_json(Path(a.responses)),
                                      read_json(Path(a.scores)) if a.scores else []))


def cmd_delete(a):
    from ctr_log import delete_apply, delete_plan
    r = roots(a)
    all_roots = [r["runtime"]]
    for extra in (a.improvement_root, *(a.extra_root or [])):
        if extra:
            all_roots.append(Path(extra))
    if a.what == "plan":
        return out(delete_plan(all_roots, r["runtime"], a.id))
    if not a.confirm:
        raise CtrError("approval_required", "--confirm が必要です。まず plan で対象を確認してください")
    return out(delete_apply(all_roots, r["runtime"], a.id, known_copies=a.known_copy))


def build():
    p = argparse.ArgumentParser(prog="ctr.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=skill_version())
    sub = p.add_subparsers(dest="cmd", required=True)

    def roots_args(sp, rt=True, imp=False, gold=False):
        if rt:
            sp.add_argument("--runtime-root")
        if imp:
            sp.add_argument("--improvement-root")
        if gold:
            sp.add_argument("--gold-root")

    c = sub.add_parser("check")
    c.add_argument("what", choices=["refs", "store", "runs", "sample", "isolation", "data"])
    c.add_argument("--review"); c.add_argument("--sources"); c.add_argument("--footer-only", action="store_true")
    c.add_argument("--in-progress-minutes", type=int, default=60)
    c.add_argument("--seed", type=int, default=0); c.add_argument("--n-no-finding", type=int, default=2)
    c.add_argument("--n-high-risk", type=int, default=3); c.add_argument("--n-random", type=int, default=2)
    c.add_argument("--agent-root", action="append"); c.add_argument("--index-meta")
    roots_args(c, imp=True, gold=True); c.set_defaults(fn=cmd_check)

    s = sub.add_parser("store"); s.add_argument("what", choices=["init", "set-policy", "status"])
    s.add_argument("--project-opaque-id"); s.add_argument("--raw-text", choices=["allow", "deny"])
    s.add_argument("--share-fields"); s.add_argument("--share-scope"); s.add_argument("--granted-by")
    roots_args(s); s.set_defaults(fn=cmd_store)

    r = sub.add_parser("record"); r.add_argument("what", choices=["start", "finish", "fail"])
    r.add_argument("--host", default="other"); r.add_argument("--route", default="unknown"); r.add_argument("--model-id")
    r.add_argument("--domains"); r.add_argument("--task-group"); r.add_argument("--terms-file", type=Path)
    r.add_argument("--index-meta", type=Path); r.add_argument("--target-text-file", type=Path)
    r.add_argument("--run-id"); r.add_argument("--review"); r.add_argument("--sources"); r.add_argument("--error-class", default="unspecified")
    roots_args(r); r.set_defaults(fn=cmd_record)

    f = sub.add_parser("feedback"); f.add_argument("what", choices=["add", "time"])
    f.add_argument("--run-id"); f.add_argument("--finding-id")
    f.add_argument("--validity"); f.add_argument("--intent"); f.add_argument("--usage"); f.add_argument("--receiver")
    f.add_argument("--reason"); f.add_argument("--corrects"); f.add_argument("--source", default="human"); f.add_argument("--reviewer")
    f.add_argument("--category"); f.add_argument("--minutes", type=float); f.add_argument("--who", default="self")
    roots_args(f); f.set_defaults(fn=cmd_feedback)

    e = sub.add_parser("export"); e.add_argument("--run-id", action="append"); e.add_argument("--again", action="store_true")
    e.add_argument("--mark-shared"); e.add_argument("--shared-to")
    roots_args(e); e.set_defaults(fn=cmd_export)
    i = sub.add_parser("import"); i.add_argument("package"); roots_args(i, rt=False, imp=True); i.set_defaults(fn=cmd_import)

    pr = sub.add_parser("propose"); pr.add_argument("what", choices=["create", "list"]); pr.add_argument("--spec")
    roots_args(pr, rt=False, imp=True); pr.set_defaults(fn=cmd_propose)

    ev = sub.add_parser("evaluate")
    ev.add_argument("what", choices=["compare", "adopt", "restore", "metrics", "regression", "holdout", "init-standard"])
    ev.add_argument("--results"); ev.add_argument("--proposal"); ev.add_argument("--evaluation"); ev.add_argument("--approved-by")
    ev.add_argument("--reason"); ev.add_argument("--i-approve", action="store_true"); ev.add_argument("--to-version")
    ev.add_argument("--known-total-usage", type=int); ev.add_argument("--case"); ev.add_argument("--register"); ev.add_argument("--terms")
    roots_args(ev, imp=True, gold=True); ev.set_defaults(fn=cmd_evaluate)

    se = sub.add_parser("search"); se.add_argument("what", choices=["exact", "build-index", "ruri"])
    se.add_argument("--terms", required=True); se.add_argument("--sources"); se.add_argument("--query", default="")
    se.add_argument("--project"); se.add_argument("--as-of"); se.add_argument("--index-dir")
    se.add_argument("--model", help="既定: cl-nagoya/ruri-v3-310m(版固定)"); se.add_argument("--revision"); se.add_argument("--top-k", type=int, default=5)
    se.add_argument("--offline", action="store_true"); se.set_defaults(fn=cmd_search)

    pf = sub.add_parser("pdf"); pf.add_argument("what", choices=["extract"]); pf.add_argument("pdf")
    pf.add_argument("--source-id", required=True); pf.add_argument("--version", required=True); pf.add_argument("--title", required=True)
    pf.add_argument("--layout", action="store_true"); pf.add_argument("--out"); pf.set_defaults(fn=cmd_pdf)

    for g, choices in (("blind", ["prepare", "score"]), ("comprehension", ["prepare", "check", "score"])):
        b = sub.add_parser(g); b.add_argument("what", choices=choices); b.set_defaults(fn=cmd_blind, group=g)
        b.add_argument("--pairs"); b.add_argument("--items"); b.add_argument("--readers"); b.add_argument("--out"); b.add_argument("--seed", type=int)
        b.add_argument("--organizer"); b.add_argument("--responses"); b.add_argument("--scores"); b.add_argument("--dir")

    d = sub.add_parser("delete"); d.add_argument("what", choices=["plan", "apply"]); d.add_argument("--id", required=True)
    d.add_argument("--confirm", action="store_true"); d.add_argument("--known-copy", action="append")
    d.add_argument("--extra-root", action="append"); roots_args(d, imp=True); d.set_defaults(fn=cmd_delete)
    return p


def main(argv=None) -> int:
    args = build().parse_args(argv)
    try:
        return args.fn(args)
    except CtrError as exc:
        msg = {"ok": False, "error": exc.code, "message": exc.message}
        if exc.code in ("storage_unwritable", "verify_failed"):
            msg["status"] = "保存未確認(記録済み件数に加えない)。未許可の場所への自動退避はしない"
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        return EXIT.get(exc.code, 1)


if __name__ == "__main__":
    sys.exit(main())
