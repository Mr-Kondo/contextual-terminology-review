"""匿名二候補比較と、単一版の理解問題。

japanese-readability-editor の compare_readability.py / comprehension_readability.py の設計
(方式名を隠す・左右の割付を主催者側に保存・一人に一つの版だけ配る)を、このSkillの記録形式に合わせて書き直したもの。
コードはコピーしていない。

隔離について: reader 用フォルダと organizer 用フォルダを分けるが、これはファイル配置の分離であり、
アクセス権限の隔離を達成したことにはならない。organizer を読み手・生成Agentから見えない場所で保管するのは運用である。
"""
from __future__ import annotations

import json
import random
import secrets
from pathlib import Path
from typing import Optional

from ctr_common import CtrError, read_json, sha256_file, sha256_obj, utcnow, write_json

RUBRIC = "ctr-blind-1"
FORBIDDEN_PUBLIC_KEYS = {"mapping", "candidate_name", "variant", "answer_key", "evidence", "gold", "expected", "reviewer_of_record"}
MEANING = ("pass", "fail", "unknown")


def _assert_public(public: dict, secrets_: list[str]) -> None:
    blob = json.dumps(public, ensure_ascii=False)
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in FORBIDDEN_PUBLIC_KEYS:
                    raise CtrError("label_leak", f"key:{k}")
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(public)
    low = blob.lower()
    for s in secrets_:
        if s and s.lower() in low:
            raise CtrError("label_leak", "candidate/version name appears in distribution")


def blind_prepare(pairs: list, reviewers: list, out: Path, seed: Optional[int] = None) -> dict:
    if len(set(reviewers)) != len(reviewers) or any(not r.strip() for r in reviewers):
        raise CtrError("invalid_reviewers")
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    seed_saved = seed if seed is not None else None
    names_all = []
    for p in pairs:
        if len(p.get("candidates", {})) != 2:
            raise CtrError("invalid_pair", "候補は2つ")
        names_all.extend(p["candidates"])
    if (out / "organizer").exists():
        raise CtrError("already_exists", "既存の配布物は上書きしない")
    documents = list(dict.fromkeys(p["document_id"] for p in pairs))
    organizer = {"schema_version": 1, "rubric": RUBRIC, "created_at": utcnow(), "seed": seed_saved,
                 "input_sha256": sha256_obj(pairs), "readers": {}}
    for idx, reader in enumerate(reviewers, 1):
        flip = {d: rng.randrange(2) for d in documents}  # 同じ文書の出力は同じ向き
        public_cases, mapping = [], {}
        for n, p in enumerate(pairs, 1):
            variants = sorted(p["candidates"])
            if flip[p["document_id"]]:
                variants.reverse()
            pid = f"pair-{n:03}"
            public_cases.append({"id": pid, "request": p["request"], "audience": p.get("audience"), "context": p.get("context"),
                                 "original": p["original"], "left": p["candidates"][variants[0]], "right": p["candidates"][variants[1]]})
            mapping[pid] = {"source_id": p["id"], "left": variants[0], "right": variants[1]}
        public = {"schema_version": 1, "rubric": RUBRIC, "reader": f"reader-{idx:03}", "cases": public_cases}
        _assert_public(public, names_all)
        rdir = out / "readers" / f"reader-{idx:03}"
        res = write_json(rdir / "tasks.json", public)
        organizer["readers"][f"reader-{idx:03}"] = {"pseudonym": reader, "mapping": mapping,
                                                    "distributed_file_sha256": res["sha256"]}  # 実配布物の記録
    write_json(out / "organizer" / "organizer.json", organizer)
    return {"readers": list(organizer["readers"]), "organizer_file": str(out / "organizer" / "organizer.json"),
            "note": "organizer/ は読み手と生成Agentに渡さない。フォルダ分離だけでアクセス隔離は成立しない"}


def blind_score(organizer: dict, responses: list) -> dict:
    """意味保持の合否は候補ごとに独立して数える。選好は、両候補が意味保持に合格した組だけで数える。"""
    per: dict = {}
    pref: dict = {}
    excluded = {"meaning_not_both_pass": 0, "preference_missing": 0}
    assigned = sum(len(r["mapping"]) for r in organizer["readers"].values())
    answered = 0
    for resp in responses:
        mp = organizer["readers"][resp["reader"]]["mapping"]
        for r in resp["responses"]:
            m = mp[r["pair_id"]]
            answered += 1
            both = []
            for side in ("left", "right"):
                v = (r.get("meaning") or {}).get(side)
                if v not in MEANING:
                    raise CtrError("invalid_meaning_value")
                name = m[side]
                c = per.setdefault(name, {"pass": 0, "fail": 0, "unknown": 0})
                c[v] += 1
                both.append(v)
            if both != ["pass", "pass"]:
                excluded["meaning_not_both_pass"] += 1  # 意味保持に落ちた候補を、読みやすさ等の評点で救済しない
                continue
            choice = r.get("preference")
            if choice in ("left", "right"):
                w = m[choice]
                pref[w] = pref.get(w, 0) + 1
            elif choice in ("tie", "uncertain"):
                pref[choice] = pref.get(choice, 0) + 1
            else:
                excluded["preference_missing"] += 1
    return {"meaning_by_candidate": per, "preference_among_both_pass": pref, "excluded": excluded,
            "assigned_pairs": assigned, "answered_pairs": answered, "missing_pairs": assigned - answered,
            "eligible": {n: c["fail"] == 0 and c["unknown"] == 0 for n, c in per.items()},
            "note": "readability 等の評点は集計に使わない。意味保持の fail/unknown が一つでもある候補は採用候補にしない"}


def comprehension_prepare(items: list, readers: list, out: Path, seed: Optional[int] = None) -> dict:
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    if (out / "organizer").exists():
        raise CtrError("already_exists")
    organizer = {"schema_version": 1, "rubric": RUBRIC, "created_at": utcnow(), "seed": seed,
                 "input_sha256": sha256_obj(items), "readers": {},
                 "answer_keys": {}, "required": {}, "ai_free_delayed": {}}
    for it in items:
        if len(it["versions"]) < 2:
            raise CtrError("invalid_item", "版が2つ以上必要")
        organizer["answer_keys"][it["id"]] = {q["qid"]: {"key": q.get("answer_key"), "evidence": q.get("evidence"),
                                                         "format": q["format"]} for q in it["questions"]}
        organizer["required"][it["id"]] = [q["qid"] for q in it["questions"] if q.get("required", True)]
        organizer["ai_free_delayed"][it["id"]] = bool(it.get("ai_free_delayed", False))
    names_all = [n for it in items for n in it["versions"]]
    # 版の割付: 項目ごとに版を並べ替え、読み手へ順番に回す(一人は一項目につき一つの版)
    order = {it["id"]: rng.sample(sorted(it["versions"]), len(it["versions"])) for it in items}
    for idx, reader in enumerate(readers):
        cases, mapping = [], {}
        for n, it in enumerate(items, 1):
            version = order[it["id"]][idx % len(order[it["id"]])]
            pub_id = f"item-{n:03}"
            cases.append({"id": pub_id, "text": it["versions"][version],
                          "questions": [{"qid": q["qid"], "prompt": q["prompt"], "format": q["format"],
                                         "choices": q.get("choices")} for q in it["questions"]]})
            mapping[pub_id] = {"source_id": it["id"], "version": version}
        public = {"schema_version": 1, "rubric": RUBRIC, "reader": f"reader-{idx + 1:03}", "items": cases,
                  "instruction": "各項目の文章を読み、質問に自分の言葉(または選択)で答える。同じ課題の別の版は渡されていない。"}
        _assert_public(public, names_all)
        res = write_json(out / "readers" / f"reader-{idx + 1:03}" / "tasks.json", public)
        organizer["readers"][f"reader-{idx + 1:03}"] = {"pseudonym": reader, "mapping": mapping, "distributed_file_sha256": res["sha256"]}
    write_json(out / "organizer" / "organizer.json", organizer)
    return {"readers": list(organizer["readers"]), "organizer_file": str(out / "organizer" / "organizer.json")}


def check_single_version(distribution_dir: Path) -> dict:
    """配布済みフォルダを読み、一人が同じ課題の複数の版を持っていないかを機械的に確認する。"""
    problems = []
    for f in sorted(Path(distribution_dir).glob("reader-*/tasks.json")):
        data = read_json(f)
        ids = [i["id"] for i in data["items"]]
        if len(ids) != len(set(ids)):
            problems.append(f"{f.parent.name}:duplicate_item")
        try:
            _assert_public(data, [])
        except CtrError as exc:
            problems.append(f"{f.parent.name}:{exc.code}")
    return {"ok": not problems, "problems": problems}


def comprehension_score(organizer: dict, responses: list, human_scores: list) -> dict:
    """必須項目の分母は、未回答を除かない。自由記述は人の採点(理由付き)だけを使う。"""
    scores = {(s["reader"], s["item"], s["qid"]): s for s in human_scores}
    agg: dict = {}
    invalid = 0
    for rd, info in organizer["readers"].items():
        resp = next((r for r in responses if r["reader"] == rd), {"answers": []})
        ans = {(a["item"], a["qid"]): a for a in resp["answers"]}
        for pub_id, m in info["mapping"].items():
            sid = m["source_id"]
            for qid in organizer["required"][sid]:
                a = ans.get((pub_id, qid))
                fmt = organizer["answer_keys"][sid][qid]["format"]
                key = (m["version"], fmt, "ai_free_delayed" if organizer["ai_free_delayed"][sid] else "same_session")
                b = agg.setdefault(key, {"matched": 0, "required": 0, "unanswered": 0, "unscored": 0, "invalid_excluded": 0})
                if a and a.get("saw_other_version"):
                    b["invalid_excluded"] += 1  # 別の版を先に読んだ回答は単一版の結果にしない
                    invalid += 1
                    continue
                b["required"] += 1
                if not a or a.get("answer") in (None, ""):
                    b["unanswered"] += 1
                elif fmt == "choice":
                    b["matched"] += int(a["answer"] == organizer["answer_keys"][sid][qid]["key"])
                else:
                    s = scores.get((rd, pub_id, qid))
                    if s is None or s.get("match") is None:
                        b["unscored"] += 1  # 人の採点がない自由記述は、正誤に押し込まない
                    elif not s.get("reason"):
                        raise CtrError("score_reason_required")
                    else:
                        b["matched"] += int(bool(s["match"]))
    rows = [{"version": k[0], "format": k[1], "timing": k[2], **v, "rate": (v["matched"] / v["required"]) if v["required"] else None,
             "status": "evaluated" if v["required"] else "unevaluated(分母0)"} for k, v in sorted(agg.items())]
    return {"rows": rows, "invalid_excluded_total": invalid,
            "note": "選択式の理解と口頭での自力説明は別。受け手不在の評価をAIの理解で代用しない。LLMだけで理解を証明しない"}
