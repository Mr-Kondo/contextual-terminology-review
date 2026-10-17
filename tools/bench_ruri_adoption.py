#!/usr/bin/env python3
"""Ruri検索の採否判断用の比較。一致検索・文字2-gram(標準ライブラリのみ)・Ruri・併用を、同じ課題・同じ採点で比べる。

課題セット(tools/data/ruri-adoption-set.json)は作成者がSkillの設計者と同じAIで、独立していない。件数も少ない。
採否基準は実行前にここへ固定した(結果を見て変えない)。結論は「この証拠では」という範囲で、実務での採用は人が決める。

採点: 正解が複数の課題は、どれか1つがtop-kに入れば命中。negative は「何も返さない」が正しい。
閾値: devのnegativeの1位得点の最大値を閾値とし、閾値を『超える』結果だけを返す(devのnegativeの誤検出は定義上0)。positive側の成績は閾値の決定に使わない。
報告の主: testの結果(devは透明性のために併記)。

採否基準(testのvariant+paraphrase, n=22 と test negative, n=10。すべて満たすとき『任意の補助として推奨できる』):
  A. Ruriの閾値つきhit@3 >= 0.60
  B. Ruriの閾値つきhit@3 が、文字2-gramの閾値つきhit@3 を 0.15 以上上回る
  C. Ruriの閾値つきnegative誤検出率 <= 0.20
満たさない項目があれば『この証拠では推奨しない』とし、満たさなかった項目を示す。

  python3 tools/bench_ruri_adoption.py --out docs/evidence/ruri-adoption-bench.json [--models 70m,310m]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))

import ctr_search as se  # noqa: E402
from ctr_common import CtrError, utcnow  # noqa: E402
from ctr_improve import wilson  # noqa: E402
from ctr_refs import load_registry  # noqa: E402

DATA = ROOT / "tools" / "data" / "ruri-adoption-set.json"
MODELS = {"70m": ("cl-nagoya/ruri-v3-70m", "07a8b0aba47d29d2ca21f89b915c1efe2c23d1cc"),
          "310m": ("cl-nagoya/ruri-v3-310m", "18b60fb8c2b9df296fb4212bb7d23ef94e579cd3")}
CATS = ["verbatim", "variant", "paraphrase", "negative"]
HARD = ("variant", "paraphrase")


def terms_and_registry(data, td: Path):
    terms = {"schema_version": 1, "terms": [
        {"id": t["id"], "term": t["term"], "aliases": t["aliases"], "sense": t["sense"], "status": "adopted",
         "scope": {"kind": "professional"}, "source": {"source_id": t["source_id"], "version": "1", "start_line": 1, "end_line": 1}}
        for t in data["terms"]]}
    reg_path = td / "sources.json"
    reg_path.write_text(json.dumps({"sources": [{"id": t["source_id"], "title": t["term"], "version": "1", "kind": "text",
                                                  "lines": [t["line"]], "text_origin": "original"} for t in data["terms"]]}, ensure_ascii=False), encoding="utf-8")
    return terms, load_registry(reg_path)


def bigrams(s: str) -> Counter:
    s = "".join(s.split())
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


class Bigram:
    """文字2-gramのTF-IDFコサイン。依存なし。得点は並べ替え用で確率ではない。"""

    def __init__(self, terms, reg):
        self.ids = [t["id"] for t in terms["terms"]]
        docs = [bigrams(se._doc_text(t, reg)) for t in terms["terms"]]
        df = Counter(g for d in docs for g in d)
        self.idf = {g: math.log((1 + len(docs)) / (1 + n)) + 1 for g, n in df.items()}
        self.vecs = [self._norm(d) for d in docs]

    def _norm(self, c):
        v = {g: n * self.idf.get(g, 1.0) for g, n in c.items()}
        z = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / z for g, x in v.items()}

    def search(self, q):
        qv = self._norm(bigrams(q))
        sc = [(sum(w * d.get(g, 0.0) for g, w in qv.items()), i) for i, d in enumerate(self.vecs)]
        sc.sort(key=lambda x: (-x[0], x[1]))
        return [(self.ids[i], round(s, 6)) for s, i in sc[:5]]


def overlap(queries, data, reg_docs):
    """問い合わせの2-gramのうち、正解の用語エントリ文書にも現れる割合の平均(言い換え課題が文書の文言に近すぎないかの目安)。"""
    out = {}
    for cat in CATS[:3]:
        v = []
        for q in queries:
            if q["category"] == cat:
                qb = bigrams(q["text"])
                best = max(sum(1 for g in qb if g in reg_docs[t]) / max(len(qb), 1) for t in q["gold"])
                v.append(best)
        out[cat] = round(sum(v) / len(v), 3)
    return out


def pct(k, n):
    return {"numerator": k, "denominator": n, "value": round(k / n, 4) if n else None, "wilson_95": wilson(k, n)}


def score_engine(ranked, queries, threshold):
    """ranked: {qid: [(term_id, score)...]}。threshold=None なら閾値なし。"""
    out = {}
    for split in ("dev", "test"):
        for cat in CATS:
            qs = [q for q in queries if q["category"] == cat and q["split"] == split]
            if cat == "negative":
                fp = sum(1 for q in qs if any(s > threshold for _, s in ranked[q["id"]])) if threshold is not None else None
                out[f"{split}/{cat}"] = {"false_positive": pct(fp, len(qs)) if fp is not None else None}
                continue
            def h(k, thr):
                n = 0
                for q in qs:
                    got = [t for t, s in ranked[q["id"]] if thr is None or s > thr][:k]
                    n += bool(set(got) & set(q["gold"]))
                return pct(n, len(qs))
            out[f"{split}/{cat}"] = {"hit@1": h(1, None), "hit@3": h(3, None), "hit@3_at_threshold": h(3, threshold) if threshold is not None else None}
        hard = [q for q in queries if q["category"] in HARD and q["split"] == split]
        def hh(k, thr):
            n = sum(bool(set([t for t, s in ranked[q["id"]] if thr is None or s > thr][:k]) & set(q["gold"])) for q in hard)
            return pct(n, len(hard))
        out[f"{split}/variant+paraphrase"] = {"hit@1": hh(1, None), "hit@3": hh(3, None),
                                              "hit@3_at_threshold": hh(3, threshold) if threshold is not None else None}
    return out


def exact_rank(terms, queries):
    # exact_search は一致した語を長さ順に返す。得点は一致=1.0
    return {q["id"]: [(h["term_id"], 1.0) for h in se.exact_search(terms, q["text"])["hits"]] for q in queries}


def threshold_from_dev(ranked, queries):
    top = [ranked[q["id"]][0][1] for q in queries if q["category"] == "negative" and q["split"] == "dev" and ranked[q["id"]]]
    return max(top) if top else 0.0


def hybrid(exact, other, queries, thr):
    """一致の結果を先頭に置き、閾値以上の補助検索の結果で後ろを埋める。"""
    out = {}
    for q in queries:
        seen, lst = set(), []
        for t, s in exact[q["id"]] + [x for x in other[q["id"]] if x[1] > thr]:
            if t not in seen:
                seen.add(t)
                lst.append((t, 1.0 if t in {x for x, _ in exact[q["id"]]} else s))
        out[q["id"]] = lst
    return out


def judge(res):
    h = res["test/variant+paraphrase"]["hit@3_at_threshold"]["value"]
    hb = res["_bigram"]["test/variant+paraphrase"]["hit@3_at_threshold"]["value"]
    fp = res["test/negative"]["false_positive"]["value"]
    checks = {"A_hit3>=0.60": h is not None and h >= 0.60, "B_over_bigram>=0.15": h is not None and hb is not None and h - hb >= 0.15 - 1e-9,
              "C_fp<=0.20": fp is not None and fp <= 0.20}
    return {"checks": checks, "values": {"ruri_hit@3_at_threshold": h, "bigram_hit@3_at_threshold": hb, "ruri_negative_fp": fp},
            "verdict": "任意の補助として推奨できる(この証拠の範囲)" if all(checks.values()) else "この証拠では推奨しない: " + ", ".join(k for k, v in checks.items() if not v)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--models", default="70m")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    raw = DATA.read_bytes()
    data = json.loads(raw)
    queries = data["queries"]
    report = {"as_of": utcnow(), "dataset_sha256": hashlib.sha256(raw).hexdigest(), "scope": data["description"],
              "counts": {f"{s}/{c}": sum(1 for q in queries if q["split"] == s and q["category"] == c) for s in ("dev", "test") for c in CATS},
              "engines": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        terms, reg = terms_and_registry(data, td)
        ex = exact_rank(terms, queries)
        report["engines"]["exact"] = score_engine(ex, queries, None)
        bg = Bigram(terms, reg)
        report["lexical_overlap_query_bigrams_in_gold_doc_mean"] = overlap(queries, data, {i: set(d) for i, d in zip(bg.ids, [bigrams(se._doc_text(t, reg)) for t in terms["terms"]])})
        bg_rank = {q["id"]: bg.search(q["text"]) for q in queries}
        thr_b = threshold_from_dev(bg_rank, queries)
        bres = score_engine(bg_rank, queries, thr_b)
        report["engines"]["bigram"] = {"threshold": thr_b, **bres}
        report["engines"]["exact+bigram"] = score_engine(hybrid(ex, bg_rank, queries, thr_b), queries, thr_b)
        for key in a.models.split(","):
            mid, rev = MODELS[key]
            name = f"ruri-{key}"
            try:
                t0 = time.time()
                info = se.build_index(terms, reg, td / f"idx-{key}", model_id=mid, revision=rev, local_files_only=a.offline)
                build_s = time.time() - t0
                rank, lat = {}, []
                for q in queries:
                    t1 = time.time()
                    r = se.ruri_search(q["text"], terms, reg, td / f"idx-{key}", top_k=5, local_files_only=a.offline)
                    lat.append((time.time() - t1) * 1000)
                    rank[q["id"]] = [(h["term_id"], h["score"]) for h in r["hits"]]
                rank2 = {q["id"]: [(h["term_id"], h["score"]) for h in se.ruri_search(q["text"], terms, reg, td / f"idx-{key}", top_k=5, local_files_only=a.offline)["hits"]] for q in queries[:10]}
                thr = threshold_from_dev(rank, queries)
                res = score_engine(rank, queries, thr)
                res["_bigram"] = bres
                report["engines"][name] = {"threshold": thr, "build_seconds": round(build_s, 2),
                                           "per_query_ms_median": round(sorted(lat)[len(lat) // 2], 1),
                                           "deterministic_first10": all(rank2[q["id"]] == rank[q["id"]] for q in queries[:10]),
                                           "index_meta": {k: info["meta"][k] for k in ("model_id", "model_revision", "libs")},
                                           "decision": judge(res), **{k: v for k, v in res.items() if k != "_bigram"}}
                report["engines"][f"exact+{name}"] = score_engine(hybrid(ex, rank, queries, thr), queries, thr)
                report["engines"][name]["per_query_top1"] = {q["id"]: rank[q["id"]][0] for q in queries}
            except CtrError as exc:
                report["engines"][name] = {"status": "not_run", "reason": exc.code, "detail": exc.message}
            except Exception as exc:  # モデル取得の失敗など。成功として記録しない
                report["engines"][name] = {"status": "failed", "reason": type(exc).__name__, "detail": str(exc)[:300]}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(json.dumps({k: (v.get("decision", {}).get("verdict") if isinstance(v, dict) else None) for k, v in report["engines"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
