#!/usr/bin/env python3
"""一致検索とRuri検索を、同じ課題・同じ資料・同じ採点で比較する(hit@k の分子/分母)。

課題は公開された開発用ケース(03)の入力文。正解は、そのケースの根拠資料に対応する用語エントリ。
件数が少なく、公開された開発例なので、未使用評価でも実務性能でもない。Ruriは venv などに
sentence-transformers が入っているときだけ実行する(無ければ未実施と出力する)。

  python3 tools/bench_search.py --out docs/evidence/search-bench.json [--offline]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))

import ctr_search as se  # noqa: E402
from ctr_common import CtrError, utcnow  # noqa: E402
from ctr_refs import load_registry  # noqa: E402

TERM_FOR_SOURCE = {"owner": "取りまとめ", "architecture": "引き渡し", "whole-service": "納品", "api": "冪等", "cloud": "可用性",
                   "network": "タイムアウト", "security": "ハッシュ値", "embedding": "得点", "engineering": "加速度", "business": "利益"}
SENSE = {"owner": "主担当の責務", "architecture": "成果物の受け渡し", "whole-service": "成果物の納品完了", "api": "繰り返し操作の性質",
         "cloud": "必要なときに利用可能である性質", "network": "期限切れ", "security": "ハッシュと復号の扱い", "embedding": "検索得点の解釈",
         "engineering": "記号と単位", "business": "指標の定義"}


def build_terms():
    return {"schema_version": 1, "terms": [
        {"id": f"t-{sid}", "term": term, "sense": SENSE[sid], "status": "adopted", "scope": {"kind": "professional"},
         "source": {"source_id": sid, "version": "1", "start_line": 1, "end_line": 3}} for sid, term in TERM_FOR_SOURCE.items()]}


def tasks(cases):
    seen, out = set(), []
    for c in cases:
        ids = c["given"].get("source_ids") or []
        text = c["given"]["text"]
        if c["kind"] == "semantic" and ids and text not in seen:
            seen.add(text)
            out.append({"case": c["id"], "query": text, "gold": f"t-{ids[0]}"})
    return out


def hit(results, tasks_, k):
    den = len(tasks_)
    num = sum(1 for t in tasks_ if t["gold"] in results[t["case"]][:k])
    return {"k": k, "numerator": num, "denominator": den, "value": num / den if den else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--model", default=se.DEFAULT_MODEL)
    ap.add_argument("--revision", help="モデルのコミットを固定する(再現用)")
    a = ap.parse_args(argv)
    spec = json.loads((ROOT / "03-acceptance-cases.json").read_text(encoding="utf-8"))
    reg = load_registry(ROOT / "03-acceptance-cases.json")
    terms, ts = build_terms(), tasks(spec["cases"])
    report = {"as_of": utcnow(), "scope": "公開された開発用ケースの入力文。件数が少なく、未使用評価でも実務性能でもない",
              "task_count": len(ts), "independent_tasks": len({t["query"] for t in ts}), "k": [1, 3], "engines": {}}
    exact = {t["case"]: [h["term_id"] for h in se.exact_search(terms, t["query"])["hits"]] for t in ts}
    report["engines"]["exact"] = {"status": "ok", "hit": [hit(exact, ts, k) for k in (1, 3)], "per_task": exact}
    try:
        with tempfile.TemporaryDirectory() as td:
            t0 = time.time()
            info = se.build_index(terms, reg, Path(td), model_id=a.model, revision=a.revision, local_files_only=a.offline)
            build_s = time.time() - t0
            ruri = {}
            logs = []
            for t in ts:
                r = se.ruri_search(t["query"], terms, reg, Path(td), top_k=3, local_files_only=a.offline)
                ruri[t["case"]] = [h["term_id"] for h in r["hits"]]
                logs.append({"case": t["case"], "scores": [h["score"] for h in r["hits"]]})
            report["engines"]["ruri"] = {"status": "ok", "hit": [hit(ruri, ts, k) for k in (1, 3)], "per_task": ruri,
                                         "scores": logs, "index_meta": {k: info["meta"][k] for k in (
                                             "model_id", "model_revision", "tokenizer_revision", "libs", "query_prefix", "doc_prefix", "chunking", "terms_sha256", "sources_sha256")},
                                         "build_seconds": round(build_s, 2)}
    except CtrError as exc:
        report["engines"]["ruri"] = {"status": "not_run", "reason": exc.code, "detail": exc.message}
    except Exception as exc:  # ネットワーク・モデル取得の失敗など。成功として記録しない
        report["engines"]["ruri"] = {"status": "failed", "reason": type(exc).__name__, "detail": str(exc)[:300]}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
