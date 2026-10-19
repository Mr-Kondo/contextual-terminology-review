"""実行記録・フィードバック・書き出し/取り込み・削除。実行先ごとの runtime_data_root を扱う。

方針(07-feedback-and-storage.md):
  - 実行・イベント別のJSONを原子的に追記する。既存IDは上書きしない。保存後に再読込して照合する。
  - 保存先は利用者が明示する(--runtime-root か CTR_RUNTIME_ROOT)。既定の保存先は持たない。
  - 原文は policy.raw_text_retention が true のときだけ private/ に保存する。
  - 共有書き出しは、項目別の許可(share_fields)が設定されるまで停止する。許可項目は名前付きの列挙値・ID・数だけ。
  - 取り込みは一時領域で検査し、データとして読むだけで実行しない。
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ctr_common import (CHECKER_VERSION, ID_RE, SCHEMA_VERSION, CtrError, new_id, read_json, sha256_bytes,
                        sha256_file, skill_version, utcnow, valid_id, write_json)

HOSTS = ("claude-code", "codex", "antigravity", "chatgpt-work", "claude-cowork", "manual", "other")
ROUTES = ("local", "remote", "account", "unknown")
DOMAINS = ("業務用語", "システム設計・クラウド", "開発・API", "運用・ネットワーク", "セキュリティ", "データ・AI",
           "科学・工学一般", "ビジネス用語", "分野横断")
VALIDITY = ("ok", "ng", "unknown")
INTENT = ("kept", "changed", "unknown")
USAGE = ("as_is", "edited", "unused")
RECEIVER = ("confirmed", "mismatch", "unconfirmed")
FEEDBACK_SOURCE = ("human", "ai_suspicion", "automated_check")
EFFORT_CATEGORY = ("record", "evidence", "compare", "practice", "setup")
EFFORT_WHO = ("self", "collaborator")

# 共有許可の項目名 -> 書き出すイベントのキー。ここにないキー(原文・引用・理由・パス・名前・正解)は書き出さない。
GROUPS = {
    "run_status": ["error_class"],
    "environment": ["host_environment", "host_route", "model_id"],
    "versions": ["versions"],
    "domains": ["domains"],
    "problem_axes": ["findings"],
    "machine_checks": ["ref_counts", "error_classes", "independent_source_count"],
    "human_feedback": ["finding_id", "validity", "intent", "usage", "receiver", "source"],
    "project_opaque_id": ["project_opaque_id", "task_group"],
    "effort": ["category", "minutes", "who"],
}
PROVENANCE = ["schema_version", "event_id", "run_id", "type", "created_at", "corrects", "package_id", "origin_id"]
EVENT_TYPES = ("run_started", "completed", "failed", "feedback", "effort")

_TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_VER = re.compile(r"^[A-Za-z0-9._:+-]{1,64}$")
_ERR = re.compile(r"^[a-z_]{1,40}(:[A-Za-z0-9_.-]{1,40})?$")
_PATHY = re.compile(r"(^|[\s\"'(=])(/[A-Za-z0-9._-]+/|[A-Za-z]:[\\/]|~/|\.\./)")


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and 0 <= x < 10**9


def _enum(*vals):
    return lambda x: x in vals


def _opt(f):
    return lambda x: x is None or f(x)


def _id(x):
    return isinstance(x, str) and bool(ID_RE.match(x))


def _list_of(f, limit=200):
    return lambda x: isinstance(x, list) and len(x) <= limit and all(f(i) for i in x)


def _dict_of(keys: dict):
    return lambda x: isinstance(x, dict) and set(x) <= set(keys) and all(keys[k](v) for k, v in x.items())


_VERSIONS = _dict_of({k: (lambda v: isinstance(v, str) and bool(_VER.match(v)))
                      for k in ("skill", "terms", "index", "config", "checker")})
_FINDING = _dict_of({
    "id": _id, "judgment": _enum("confirmed", "provisional", "pending"),
    "effective": _enum("confirmed", "provisional", "pending", "needs_confirmation"),
    "professional_fit": _enum("conformant", "misuse_with_basis", "unknown", "out_of_scope"),
    "intent_clarity": _enum("explicit", "ambiguous", "insufficient_sources"),
    "business_premise": _enum("agreed", "not_agreed", "unverifiable"),
    "proposal_kind": _enum("meaning_preserving_fix", "needs_confirmation", "preference", "no_change")})
FIELD_RULES = {
    "schema_version": lambda x: x == SCHEMA_VERSION,
    "event_id": _id, "run_id": _id, "origin_id": _id,
    "type": _enum(*EVENT_TYPES),
    "created_at": lambda x: isinstance(x, str) and bool(_TS.match(x)),
    "corrects": _opt(_id), "package_id": _opt(_id),
    "error_class": _opt(lambda x: isinstance(x, str) and bool(_ERR.match(x))),
    "host_environment": _enum(*HOSTS), "host_route": _enum(*ROUTES),
    "model_id": lambda x: isinstance(x, str) and bool(_VER.match(x)),
    "versions": _VERSIONS,
    "domains": _list_of(lambda x: x in DOMAINS, 9),
    "findings": _list_of(_FINDING),
    "ref_counts": _dict_of({k: _is_int for k in ("checked", "pass", "fail", "needs_visual", "not_applicable")}),
    "error_classes": _list_of(lambda x: isinstance(x, str) and bool(_ERR.match(x))),
    "independent_source_count": _is_int,
    "finding_id": _id,
    "validity": _opt(_enum(*VALIDITY)), "intent": _opt(_enum(*INTENT)), "usage": _opt(_enum(*USAGE)),
    "receiver": _opt(_enum(*RECEIVER)), "source": _enum(*FEEDBACK_SOURCE),
    "project_opaque_id": _id, "task_group": _id,
    "category": _enum(*EFFORT_CATEGORY), "minutes": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 600,
    "who": _enum(*EFFORT_WHO),
}
ALL_SHAREABLE_KEYS = set(PROVENANCE) | {k for ks in GROUPS.values() for k in ks}


def validate_shared_event(ev) -> None:
    """共有パッケージのイベントを検査する。許可外のキー・型・値は拒否する(原文を含められない形)。"""
    if not isinstance(ev, dict):
        raise CtrError("event_not_object")
    for k, v in ev.items():
        if k not in ALL_SHAREABLE_KEYS:
            raise CtrError("field_not_allowed")  # キー名も表示しない(攻撃者が選べる文字列のため)
        if not FIELD_RULES[k](v):
            raise CtrError("field_value_invalid", k)
    for k in ("schema_version", "event_id", "run_id", "type", "created_at", "origin_id"):
        if k not in ev:
            raise CtrError("field_missing", k)
    if _PATHY.search(repr(ev)):
        raise CtrError("path_like_value")


# ---------------------------------------------------------------- 保存先と方針

def resolve_root(value: Optional[str], env: str, what: str) -> Path:
    value = value or os.environ.get(env)
    if not value:
        raise CtrError("storage_unconfigured",
                       f"{what} が未指定です。--{what.replace('_', '-')} か環境変数 {env} で絶対パスを指定してください。"
                       "未設定のまま自動で保存先を作りません(手動記録の経路: references/hosts.md)。")
    p = Path(value).expanduser()
    if not p.is_absolute():
        raise CtrError("storage_path_not_absolute", what)
    return p


def policy_path(root: Path) -> Path:
    return root / "policy.json"


def load_policy(root: Path) -> dict:
    if not policy_path(root).exists():
        raise CtrError("store_not_initialized", "ctr store init を先に実行してください")
    pol = read_json(policy_path(root))
    if pol.get("schema_version") != SCHEMA_VERSION:
        raise CtrError("unknown_schema", "policy")
    return pol


def store_init(root: Path, project_opaque_id: Optional[str] = None) -> dict:
    if policy_path(root).exists():
        raise CtrError("already_initialized", "既存の policy.json は変更しません")
    pol = {"schema_version": SCHEMA_VERSION, "origin_id": "org-" + secrets.token_hex(6),
           "project_opaque_id": valid_id(project_opaque_id, "project_opaque_id") if project_opaque_id else "prj-" + secrets.token_hex(4),
           "created_at": utcnow(), "raw_text_retention": False,
           "retention": {"mode": "undecided", "note": "保存期限は利用者が決める。根拠のない自動削除日数は設定しない"},
           "share_fields": None, "share_scope": None, "share_permission": None}
    res = write_json(policy_path(root), pol)
    return {"policy": pol, "write": res}


def set_policy(root: Path, *, raw_text: Optional[str] = None, share_fields: Optional[list] = None,
               share_scope: Optional[str] = None, granted_by: Optional[str] = None) -> dict:
    pol = load_policy(root)
    if raw_text is not None:
        if raw_text not in ("allow", "deny"):
            raise CtrError("invalid_option", "raw_text")
        pol["raw_text_retention"] = raw_text == "allow"
    if share_fields is not None:
        bad = [f for f in share_fields if f not in GROUPS]
        if bad or not share_fields:
            raise CtrError("invalid_share_fields", f"許可できる項目: {', '.join(GROUPS)}")
        if not (share_scope and granted_by):
            raise CtrError("share_permission_incomplete", "--share-scope と --granted-by が必要です")
        pol["share_fields"] = sorted(set(share_fields))
        pol["share_scope"] = share_scope
        pol["share_permission"] = {"status": "granted", "by": granted_by, "at": utcnow()}
    return write_json(policy_path(root), pol, overwrite=True) | {"policy": pol}


# ---------------------------------------------------------------- 実行の記録

def find_run_dir(root: Path, run_id: str) -> Path:
    valid_id(run_id, "run_id")
    hits = list((root / "runs").glob(f"*/{run_id}"))
    if not hits:
        raise CtrError("run_not_found")
    return hits[0]


def record_start(root: Path, *, host: str, route: str = "unknown", model_id: Optional[str] = None,
                 domains: Optional[list] = None, task_group: Optional[str] = None,
                 terms_file: Optional[Path] = None, index_meta: Optional[Path] = None,
                 target_text_file: Optional[Path] = None) -> dict:
    pol = load_policy(root)
    if host not in HOSTS or route not in ROUTES:
        raise CtrError("invalid_option", "host/route")
    domains = domains or []
    if any(d not in DOMAINS for d in domains):
        raise CtrError("invalid_option", "domains")
    model = model_id or os.environ.get("CTR_MODEL_ID")
    run_id = new_id("run")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    run_dir = root / "runs" / month / run_id
    target = {"ref": "tgt-" + secrets.token_hex(4), "raw_stored": False, "reason": None}
    private_text = None
    if target_text_file:
        raw = Path(target_text_file).read_bytes()
        target["sha256"] = sha256_bytes(raw)
        if pol["raw_text_retention"]:
            private_text = raw
            target["raw_stored"] = True
        else:
            target["reason"] = "policy: raw_text_retention=false。原文は複製せず、再現できる範囲は限定される"
            target["reproducibility"] = "limited"
    versions = {"skill": skill_version(), "checker": CHECKER_VERSION,
                "terms": sha256_file(terms_file)[:16] if terms_file else "unknown",
                "index": sha256_file(index_meta)[:16] if index_meta else "none",
                "config": sha256_bytes(repr(sorted((k, repr(v)) for k, v in pol.items()
                                                   if k in ("raw_text_retention", "share_fields"))).encode())[:16]}
    run = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "event_id": new_id("ev"), "type": "run_started",
           "created_at": utcnow(), "origin_id": pol["origin_id"], "project_opaque_id": pol["project_opaque_id"],
           "host_environment": host, "host_route": route,
           "model_id": model if model else "unknown", "model_id_unavailable_reason": None if model else "ホストから取得できなかった/未指定",
           "versions": versions, "domains": domains, "task_group": valid_id(task_group, "task_group") if task_group else run_id,
           "retention": {"raw_text_retention": pol["raw_text_retention"], "retention_mode": pol["retention"]["mode"]},
           "target": target, "corrects": None, "package_id": None}
    result = write_json(run_dir / "run.json", run)
    if private_text is not None:
        (run_dir / "private").mkdir(exist_ok=True)
        (run_dir / "private" / "target.txt").write_bytes(private_text)
    return {"run_id": run_id, "event_id": run["event_id"], "write": result, "target": target}


def _terminal_exists(run_dir: Path) -> bool:
    return any(read_json(p).get("type") in ("completed", "failed") for p in (run_dir / "events").glob("*.json"))


def record_finish(root: Path, run_id: str, *, review_summary: Optional[dict] = None, failed_with: Optional[str] = None,
                  private_output: Optional[dict] = None) -> dict:
    pol = load_policy(root)
    run_dir = find_run_dir(root, run_id)
    if _terminal_exists(run_dir):
        raise CtrError("already_terminated", "終了イベントは一つだけ。訂正は feedback --corrects を使う")
    ev = {"schema_version": SCHEMA_VERSION, "event_id": new_id("ev"), "run_id": run_id,
          "type": "failed" if failed_with else "completed", "created_at": utcnow(), "origin_id": pol["origin_id"],
          "corrects": None, "package_id": None}
    if failed_with:
        ev["error_class"] = failed_with
    if review_summary:
        ev.update(review_summary)
    if private_output is not None:
        if pol["raw_text_retention"]:
            write_json(run_dir / "private" / "output.json", {**private_output, "derived_from": [run_id]})
            ev["private_output_stored"] = True
        else:
            ev["private_output_stored"] = False
            ev["output_nonstorage_reason"] = "policy: raw_text_retention=false"
    return {"event_id": ev["event_id"], "write": write_json(run_dir / "events" / f"{ev['event_id']}.json", ev)}


def summarize_review(check_report: dict, review) -> dict:
    """review_check の結果から、共有できる形の要約(列挙値・件数・IDだけ)を作る。"""
    refs = check_report["refs"]
    counts = {"checked": len(refs)}
    for st in ("pass", "fail", "needs_visual", "not_applicable"):
        counts[st] = sum(1 for r in refs if r["mechanical"] == st)
    eff = {f["id"]: f["effective"] for f in check_report["findings"]}
    classes = check_report["error_classes"]
    return {"findings": [{"id": f.id, "judgment": f.judgment, "effective": eff[f.id], "professional_fit": f.professional_fit,
                          "intent_clarity": f.intent_clarity, "business_premise": f.business_premise,
                          "proposal_kind": f.proposal_kind} for f in review.findings],
            "ref_counts": counts, "error_classes": classes,
            "independent_source_count": check_report["independent_source_count"]}


# ---------------------------------------------------------------- フィードバック

def feedback_add(root: Path, run_id: str, finding_id: str, *, validity=None, intent=None, usage=None, receiver=None,
                 reason: Optional[str] = None, corrects: Optional[str] = None, source: str = "human",
                 reviewer: Optional[str] = None) -> dict:
    pol = load_policy(root)
    run_dir = find_run_dir(root, run_id)
    valid_id(finding_id, "finding_id")
    for val, allowed in ((validity, VALIDITY), (intent, INTENT), (usage, USAGE), (receiver, RECEIVER)):
        if val is not None and val not in allowed:
            raise CtrError("invalid_option", "feedback value")
    if source not in FEEDBACK_SOURCE:
        raise CtrError("invalid_option", "source")
    if corrects:
        valid_id(corrects, "corrects")
        if not (run_dir / "feedback" / f"{corrects}.json").exists():
            raise CtrError("corrects_target_not_found", "訂正対象は同じ実行の feedback イベントのみ")
    kept = reason if pol["raw_text_retention"] else None  # 理由に原文が混ざり得る。不許可なら保存しない
    ev = {"schema_version": SCHEMA_VERSION, "event_id": new_id("fb"), "run_id": run_id, "type": "feedback",
          "created_at": utcnow(), "origin_id": pol["origin_id"], "corrects": corrects, "package_id": None,
          "finding_id": finding_id, "validity": validity, "intent": intent, "usage": usage, "receiver": receiver,
          "source": source, "reviewer": reviewer, "reason": kept,
          "reason_withheld": bool(reason) and kept is None}  # reason/reviewer は書き出し対象外
    return {"event_id": ev["event_id"], "write": write_json(run_dir / "feedback" / f"{ev['event_id']}.json", ev)}


def effort_add(root: Path, *, category: str, minutes: float, who: str = "self", run_id: Optional[str] = None) -> dict:
    pol = load_policy(root)
    if category not in EFFORT_CATEGORY or who not in EFFORT_WHO:
        raise CtrError("invalid_option", "effort")
    base = (find_run_dir(root, run_id) if run_id else root / "runs" / "_effort") / "events"
    ev = {"schema_version": SCHEMA_VERSION, "event_id": new_id("ef"), "run_id": run_id or "effort-standalone",
          "type": "effort", "created_at": utcnow(), "origin_id": pol["origin_id"], "corrects": None, "package_id": None,
          "category": category, "minutes": minutes, "who": who}
    return {"event_id": ev["event_id"], "write": write_json(base / f"{ev['event_id']}.json", ev)}


def effective_feedback(feedback_events: list[dict]) -> dict:
    """(run_id, finding_id, source) ごとの有効な評価。訂正された評価は来歴として残し、集計には使わない。"""
    corrected = {e["corrects"] for e in feedback_events if e.get("corrects")}
    live: dict = {}
    for e in sorted(feedback_events, key=lambda e: (e["created_at"], e["event_id"])):
        if e["event_id"] in corrected:
            continue
        live[(e["run_id"], e["finding_id"], e.get("source", "human"))] = e
    return live


# ---------------------------------------------------------------- 点検

def iter_runs(root: Path):
    for d in sorted((root / "runs").glob("*/run-*")):
        yield d


def check_store(root: Path) -> dict:
    problems, files = [], 0
    for p in (root / "runs").rglob("*") if (root / "runs").exists() else []:
        if p.name.startswith(".tmp-"):
            problems.append({"kind": "temp_leftover", "file": p.name})
        elif p.suffix == ".json" and p.is_file():
            files += 1
            try:
                obj = read_json(p)
                if obj.get("schema_version") != SCHEMA_VERSION:
                    problems.append({"kind": "unknown_schema", "file": p.name})
            except CtrError:
                problems.append({"kind": "corrupt_json", "file": p.name})
    for d in iter_runs(root):
        if not (d / "run.json").exists():
            problems.append({"kind": "run_without_run_json", "file": d.name})
    return {"files_read": files, "problems": problems, "ok": not problems}


def check_runs(root: Path, in_progress_minutes: int = 60) -> list[dict]:
    now = datetime.now(timezone.utc)
    out = []
    for d in iter_runs(root):
        run = read_json(d / "run.json")
        terms = [read_json(p) for p in sorted((d / "events").glob("*.json"))] if (d / "events").exists() else []
        term = next((t for t in terms if t["type"] in ("completed", "failed")), None)
        if term:
            status = term["type"]
        else:
            age = now - datetime.strptime(run["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            status = "in_progress_or_unknown" if age < timedelta(minutes=in_progress_minutes) else "incomplete_suspected"
        out.append({"run_id": run["run_id"], "status": status, "started_at": run["created_at"],
                    "host": run["host_environment"], "reason_known": status in ("completed", "failed")})
    return out


# ---------------------------------------------------------------- 書き出し

def collect_events(root: Path, run_ids: Optional[list] = None) -> list[dict]:
    events = []
    for d in iter_runs(root):
        if run_ids and d.name not in run_ids:
            continue
        events.append(read_json(d / "run.json"))
        for sub in ("events", "feedback"):
            if (d / sub).exists():
                events.extend(read_json(p) for p in sorted((d / sub).glob("*.json")))
    eff = root / "runs" / "_effort" / "events"
    if eff.exists() and not run_ids:
        events.extend(read_json(p) for p in sorted(eff.glob("*.json")))
    return events


def project(ev: dict, fields: list, package_id: str) -> dict:
    keys = set(PROVENANCE)
    for g in fields:
        keys.update(GROUPS[g])
    out = {k: ev[k] for k in keys if k in ev}
    out["package_id"] = package_id
    return out


def _sensitive_strings(root: Path) -> set:
    found = set()
    for d in iter_runs(root):
        for p in (d / "private").glob("*") if (d / "private").exists() else []:
            if p.is_file():
                try:
                    found.update(s for s in re.split(r"[\s、。,.]+", p.read_text(encoding="utf-8")) if len(s) >= 4)
                except UnicodeDecodeError:
                    pass
        if (d / "feedback").exists():
            for p in (d / "feedback").glob("*.json"):
                r = read_json(p).get("reason")
                if r:
                    found.add(r)
    return found


def export_package(root: Path, *, run_ids: Optional[list] = None, include_exported: bool = False) -> dict:
    pol = load_policy(root)
    perm = pol.get("share_permission")
    if not pol.get("share_fields") or not perm or perm.get("status") != "granted":
        raise CtrError("sharing_not_configured",
                       "共有許可(項目・範囲・許可者)が未設定です。共有用の書き出しは確認待ちで停止しました。"
                       "ctr store set-policy --share-fields ... --share-scope ... --granted-by ... で設定してください。")
    ledger_path = root / "exports.json"
    ledger = read_json(ledger_path) if ledger_path.exists() else {"exports": []}
    done = {e for x in ledger["exports"] for e in x["event_ids"]}
    package_id = new_id("pkg")
    shared = []
    for ev in collect_events(root, run_ids):
        if not include_exported and ev["event_id"] in done:
            continue
        rec = project(ev, pol["share_fields"], package_id)
        validate_shared_event(rec)
        shared.append(rec)
    if not shared:
        raise CtrError("nothing_to_export")
    sensitive = _sensitive_strings(root)
    blob = repr(shared)
    if any(s in blob for s in sensitive):
        raise CtrError("leak_detected", "共有候補に非公開文字列が含まれたため中止しました(内容は表示しません)")
    out = root / "outbox" / package_id
    files = []
    try:
        for rec in shared:
            res = write_json(out / "events" / f"{rec['event_id']}.json", rec)
            files.append({"name": f"events/{rec['event_id']}.json", "sha256": res["sha256"], "bytes": res["bytes"]})
        manifest = {"schema_version": SCHEMA_VERSION, "package_id": package_id, "origin_id": pol["origin_id"],
                    "created_at": utcnow(), "fields": pol["share_fields"], "share_scope": pol["share_scope"],
                    "permission": perm, "event_ids": [r["event_id"] for r in shared], "files": files,
                    "note": "sha256 は移送中の同一性の検査であり、送信者の認証や内容の正しさを示さない"}
        write_json(out / "manifest.json", manifest)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    ledger["exports"].append({"package_id": package_id, "created_at": utcnow(), "share_scope": pol["share_scope"],
                              "event_ids": manifest["event_ids"], "shared_to": []})
    write_json(ledger_path, ledger, overwrite=True)
    return {"package_id": package_id, "path": str(out), "event_count": len(shared), "fields": pol["share_fields"],
            "excluded_always": ["入力全文", "出力全文", "引用・抜粋", "添付", "絶対パス", "氏名・案件名", "受け手の回答", "評価用正解", "理由の自由記述"]}


def mark_shared(root: Path, package_id: str, label: str) -> dict:
    """パッケージの共有先(利用者が申告した名前)を台帳に残す。削除時に確認待ちとして使う。"""
    p = root / "exports.json"
    ledger = read_json(p) if p.exists() else {"exports": []}
    ent = next((x for x in ledger["exports"] if x["package_id"] == package_id), None)
    if ent is None:
        raise CtrError("package_not_found")
    if label not in ent["shared_to"]:
        ent["shared_to"].append(label)
    return write_json(p, ledger, overwrite=True)


# ---------------------------------------------------------------- 取り込み

def _safe_read(base: Path, rel: str, max_bytes: int) -> bytes:
    if not re.fullmatch(r"(events/)?[A-Za-z0-9][A-Za-z0-9._-]*\.json", rel):
        raise CtrError("path_outside_boundary")
    path = base / rel
    expected = os.path.join(os.path.realpath(base), "events") if rel.startswith("events/") else os.path.realpath(base)
    if os.path.realpath(path.parent) != expected:
        raise CtrError("path_outside_boundary")
    try:
        if path.is_symlink():   # O_NOFOLLOW が無い環境(Windows)でも、リンクは読まない
            raise OSError("symlink")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise CtrError("link_or_unreadable_entry") from exc
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise CtrError("non_regular_entry")
        if st.st_size > max_bytes:
            raise CtrError("size_limit_exceeded")
        return f.read(max_bytes + 1)


def _tombstones(*roots: Path) -> set:
    ids = set()
    for r in roots:
        p = r / "deleted_ids.json"
        if p.exists():
            ids.update(e["id"] for e in read_json(p).get("deleted", []))
    return ids


def _inbox_index(imp: Path) -> dict:
    index = {}
    for p in (imp / "inbox").glob("*/events/*.json") if (imp / "inbox").exists() else []:
        index[p.stem] = sha256_file(p)
    return index


def import_package(improvement_root: Path, package_dir: Path, *, max_file_bytes: int = 1 << 20,
                   max_files: int = 5000, max_total_bytes: int = 64 << 20) -> dict:
    pkg = Path(package_dir)
    imp = improvement_root
    (imp / "receipts").mkdir(parents=True, exist_ok=True)

    def reject(code: str, manifest_sha: str = "unknown") -> CtrError:
        rid = "rej-" + (manifest_sha[:12] if manifest_sha != "unknown" else secrets.token_hex(6))
        try:
            write_json(imp / "receipts" / f"{rid}.json", {"status": "rejected", "code": code, "at": utcnow(),
                                                          "manifest_sha256": manifest_sha}, overwrite=True)
        except CtrError:
            pass
        return CtrError(code, "取り込みを拒否しました(内容は表示しません)。確定した記録はありません")

    manifest_sha = "unknown"
    try:
        if pkg.is_symlink() or not pkg.is_dir():
            raise CtrError("package_not_directory")
        raw_manifest = _safe_read(pkg, "manifest.json", max_file_bytes)
        manifest_sha = sha256_bytes(raw_manifest)
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise CtrError("invalid_json") from exc
        if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
            raise CtrError("unknown_schema")
        allowed = {"schema_version", "package_id", "origin_id", "created_at", "fields", "share_scope", "permission",
                   "event_ids", "files", "note"}
        if set(manifest) - allowed:
            raise CtrError("unknown_schema")
        if not _id(manifest.get("package_id")) or not _id(manifest.get("origin_id")):
            raise CtrError("manifest_invalid")
        if (manifest.get("permission") or {}).get("status") != "granted" or not manifest.get("fields"):
            raise CtrError("permission_not_granted")
        if any(f not in GROUPS for f in manifest["fields"]):
            raise CtrError("field_not_allowed")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > max_files:
            raise CtrError("size_limit_exceeded")
        # 実在するエントリが、manifest の一覧と完全に一致すること(リンク・余分なファイルを拒否)
        listed = {f["name"] for f in files if isinstance(f, dict) and isinstance(f.get("name"), str)}
        actual = set()
        with os.scandir(pkg) as top:
            for entry in list(top):
                if entry.name == "manifest.json" and entry.is_file(follow_symlinks=False):
                    continue
                if entry.name == "events" and entry.is_dir(follow_symlinks=False):
                    with os.scandir(pkg / "events") as sub:
                        for e2 in list(sub):
                            if not e2.is_file(follow_symlinks=False):
                                raise CtrError("link_or_unreadable_entry")
                            actual.add(f"events/{e2.name}")
                    continue
                raise CtrError("unlisted_file" if not entry.is_symlink() else "link_or_unreadable_entry")
        if actual != listed or len(listed) != len(files):
            raise CtrError("unlisted_file")
        total, events = 0, {}
        for f in files:
            if set(f) != {"name", "sha256", "bytes"}:
                raise CtrError("manifest_invalid")
            data = _safe_read(pkg, f["name"], max_file_bytes)
            total += len(data)
            if total > max_total_bytes:
                raise CtrError("size_limit_exceeded")
            if len(data) != f["bytes"] or sha256_bytes(data) != f["sha256"]:
                raise CtrError("hash_mismatch")
            try:
                ev = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise CtrError("invalid_json") from exc
            validate_shared_event(ev)
            if f["name"] != f"events/{ev['event_id']}.json" or ev["origin_id"] != manifest["origin_id"]:
                raise CtrError("manifest_invalid")
            if any(k not in set(PROVENANCE) | {k2 for g in manifest["fields"] for k2 in GROUPS[g]} for k in ev):
                raise CtrError("field_not_allowed")
            events[ev["event_id"]] = (ev, data)
        if set(manifest.get("event_ids", [])) != set(events):
            raise CtrError("manifest_invalid")
    except CtrError as exc:
        raise reject(exc.code, manifest_sha) from exc

    inbox = _inbox_index(imp)
    dead = _tombstones(imp)
    counts = {"accepted": 0, "duplicate": 0, "conflict_quarantined": 0, "tombstoned": 0}
    accepted = {}
    for eid, (ev, data) in events.items():
        digest = sha256_bytes(data)
        if eid in dead or ev["run_id"] in dead:
            counts["tombstoned"] += 1
        elif eid in inbox:
            if inbox[eid] == digest:
                counts["duplicate"] += 1
            else:
                counts["conflict_quarantined"] += 1
                q = imp / "quarantine" / f"conflict-{eid}-{digest[:8]}"
                (q / "events").mkdir(parents=True, exist_ok=True)
                (q / "events" / f"{eid}.json").write_bytes(data)
                write_json(q / "reason.json", {"code": "same_id_different_content", "at": utcnow(),
                                               "package_id": manifest["package_id"]}, overwrite=True)
        else:
            counts["accepted"] += 1
            accepted[eid] = data
    final = imp / "inbox" / manifest["package_id"]
    if final.exists():
        if (final / "source_manifest.json").exists() and sha256_file(final / "source_manifest.json") == manifest_sha:
            return {"status": "already_imported", "package_id": manifest["package_id"], **counts, "accepted": 0}
        counts["conflict_quarantined"] += counts["accepted"]
        counts["accepted"] = 0
        q = imp / "quarantine" / f"package-{manifest['package_id']}-{manifest_sha[:8]}"
        q.mkdir(parents=True, exist_ok=True)
        write_json(q / "reason.json", {"code": "package_id_conflict", "at": utcnow(), "manifest_sha256": manifest_sha}, overwrite=True)
        accepted = {}
    if accepted:
        stage = imp / ".staging" / f"{manifest['package_id']}-{secrets.token_hex(4)}"
        try:
            (stage / "events").mkdir(parents=True)
            for eid, data in accepted.items():
                (stage / "events" / f"{eid}.json").write_bytes(data)
            (stage / "source_manifest.json").write_bytes(raw_manifest)
            write_json(stage / "receipt.json", {"accepted_event_ids": sorted(accepted), **counts, "at": utcnow()})
            (imp / "inbox").mkdir(parents=True, exist_ok=True)
            os.rename(stage, final)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    write_json(imp / "receipts" / f"{manifest['package_id']}-{manifest_sha[:8]}.json",
               {"status": "imported", "package_id": manifest["package_id"], **counts, "at": utcnow(),
                "manifest_sha256": manifest_sha}, overwrite=True)
    return {"status": "imported", "package_id": manifest["package_id"], **counts}


# ---------------------------------------------------------------- 削除

def _scan_dependents(roots: list[Path], target: str) -> list[dict]:
    def files():
        for r in roots:
            if r.exists():
                for p in r.rglob("*"):
                    if p.is_file() and not p.name.startswith(".tmp-") and p.name != "deleted_ids.json":
                        yield r, p

    objs = {}
    ids = {target}
    for r, p in files():
        if p.suffix == ".json":
            try:
                objs[p] = read_json(p)
            except CtrError:
                continue
            o = objs[p]
            if isinstance(o, dict) and (o.get("run_id") == target or target in (o.get("derived_from") or [])) and o.get("event_id"):
                ids.add(o["event_id"])  # この実行に属するイベント。パッケージの manifest などから辿る
    hits = []
    for r, p in files():
        o = objs.get(p)
        matched = bool(ids & set(p.parts)) or p.stem in ids
        if not matched and isinstance(o, dict):
            matched = (o.get("run_id") == target or bool(ids & set(o.get("derived_from") or []))
                       or bool(ids & set(o.get("event_ids") or [])) or bool(ids & set(o.get("accepted_event_ids") or []))
                       or target in (o.get("source_ids") or []))
        if matched:
            hits.append({"path": str(p), "label": f"{r.name}/{p.relative_to(r)}"})
    return hits


def delete_plan(roots: list[Path], runtime_root: Path, target: str) -> dict:
    hits = _scan_dependents(roots, target)
    ledger = runtime_root / "exports.json"
    pending = []
    if ledger.exists():
        for x in read_json(ledger)["exports"]:
            if any(x["package_id"] in h["label"] or Path(h["path"]).stem in x["event_ids"] for h in hits):
                pending.append({"kind": "shared_copy", "package_id": x["package_id"], "share_scope": x["share_scope"],
                                "shared_to": x["shared_to"] or ["送付先は未記録"], "status": "削除確認待ち(権限外の可能性)"})
    return {"target": target, "local_dependents": hits, "pending_confirmation": pending,
            "unknown_copies": "バックアップ・利用者が別途コピーした場所は追跡できない。--known-copy で申告があれば確認待ちに加える"}


def delete_apply(roots: list[Path], runtime_root: Path, target: str, *, known_copies: Optional[list] = None) -> dict:
    plan = delete_plan(roots, runtime_root, target)
    removed = 0
    for h in plan["local_dependents"]:
        p = Path(h["path"])
        if p.is_file():
            p.unlink()
            removed += 1
            for parent in p.parents:
                if parent in roots or not parent.exists() or any(parent.iterdir()):
                    break
                parent.rmdir()
    pending = plan["pending_confirmation"] + [{"kind": "known_copy", "where": c, "status": "削除確認待ち"} for c in known_copies or []]
    for r in {runtime_root, *roots}:
        led = r / "deleted_ids.json"
        data = read_json(led) if led.exists() else {"deleted": []}
        if not any(e["id"] == target for e in data["deleted"]):
            data["deleted"].append({"id": target, "deleted_at": utcnow()})  # IDだけ。内容は残さない
            write_json(led, data, overwrite=True)
    report = {"target": target, "removed_local_files": removed, "pending_confirmation": pending,
              "status": "deleted_local_pending_external" if pending else "deleted_local_all_known",
              "note": "追跡できた範囲の削除。未追跡の複製がないことは確認できない" }
    write_json(runtime_root / "deletion_reports" / f"{target}-{utcnow().replace(':', '')}.json", report)
    return report
