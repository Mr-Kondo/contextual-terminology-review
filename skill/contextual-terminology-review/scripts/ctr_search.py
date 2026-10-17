"""用語・別名の一致検索(標準ライブラリのみ)と、任意のRuri検索(SentenceTransformers)。

Ruri は比較可能な任意の検索方式。得点は関連度の並びを作るためのもので、正しさの確率ではない。
重い依存はRuri検索を使うときだけ読み込む。使えなかった場合は成功として記録しない。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ctr_common import CtrError, read_json, sha256_obj, skill_version, utcnow, write_json
from ctr_refs import Registry

DEFAULT_MODEL = "cl-nagoya/ruri-v3-310m"   # 70m は docs/RURI-ADOPTION.md の基準に届かなかったため既定にしない(--model で指定可)
DEFAULT_REVISION = "18b60fb8c2b9df296fb4212bb7d23ef94e579cd3"   # 検証に使ったsnapshot。既定モデルのときだけ固定する
QUERY_PREFIX = "検索クエリ: "   # Ruri v3 モデルカードの検索用接頭辞(実装時に取得したモデルカードで再確認すること)
DOC_PREFIX = "検索文書: "
INDEX_FORMAT = 1


def exact_search(terms_obj: dict, text: str, *, project: Optional[str] = None, as_of: Optional[str] = None) -> dict:
    hits = []
    for t in terms_obj.get("terms", []):
        scope = t.get("scope") or {"kind": "professional"}
        if scope.get("kind") == "project" and scope.get("project") != project:
            continue  # 案件限定の語義は、その案件でだけ使う
        if as_of and ((t.get("valid_from") and as_of < t["valid_from"]) or (t.get("valid_to") and as_of > t["valid_to"])):
            continue
        forms = [t["term"], *t.get("aliases", [])]
        matched = [f for f in forms if f and f in text]
        if matched:
            hits.append({"term_id": t["id"], "matched_form": max(matched, key=len),
                         "via": "term" if t["term"] in matched else "alias", "sense": t.get("sense"),
                         "scope": scope, "status": t.get("status", "candidate"),
                         "personal_preference": scope.get("kind") == "personal",
                         "source": t.get("source")})
    hits.sort(key=lambda h: (-len(h["matched_form"]), h["term_id"]))
    return {"engine": "exact", "hits": hits,
            "note": "同じ語の複数の有効な語義は併存する。candidate は確認候補であり採用済みではない"}


def _doc_text(t: dict, reg: Optional[Registry]) -> str:
    parts = [t["term"], " ".join(t.get("aliases", [])), t.get("sense", "")]
    src = t.get("source")
    if src and reg:
        s, err = reg.lookup(src["source_id"], src["version"])
        if s and s.lines:
            parts.append(" ".join(s.lines[max(src.get("start_line", 1) - 1, 0):src.get("end_line", len(s.lines))]))
    return " ".join(p for p in parts if p)


def _registry_hash(reg: Optional[Registry]) -> str:
    from ctr_refs import source_text_hash
    if not reg:
        return "none"
    return sha256_obj(sorted((i, v, source_text_hash(s)) for i, vs in reg.by_id.items() for v, s in vs.items()))


def _load_st():
    try:
        import sentence_transformers as st
        from sentence_transformers import SentenceTransformer, util
        return st, SentenceTransformer, util
    except ImportError as exc:
        raise CtrError("ruri_unavailable", "sentence-transformers が未導入。Ruri検索は実行していない(成功として記録しない)") from exc


def build_index(terms_obj: dict, reg: Optional[Registry], index_dir: Path, *, model_id: str = DEFAULT_MODEL,
                revision: Optional[str] = None, local_files_only: bool = False) -> dict:
    st, SentenceTransformer, util = _load_st()
    import numpy as np
    import torch
    import transformers
    revision = revision or (DEFAULT_REVISION if model_id == DEFAULT_MODEL else None)
    kwargs = {"revision": revision} if revision else {}
    model = SentenceTransformer(model_id, local_files_only=local_files_only, **kwargs)
    terms = terms_obj.get("terms", [])
    docs = [_doc_text(t, reg) for t in terms]
    emb = model.encode([DOC_PREFIX + d for d in docs], convert_to_numpy=True, normalize_embeddings=True)
    commit = getattr(getattr(model[0].auto_model, "config", None), "_commit_hash", None)
    meta = {"index_format": INDEX_FORMAT, "created_at": utcnow(), "skill_version": skill_version(),
            "model_id": model_id, "model_revision": revision or commit or "unknown",
            "tokenizer_revision": revision or commit or "unknown",
            "libs": {"sentence_transformers": st.__version__, "torch": torch.__version__, "transformers": transformers.__version__,
                     "numpy": np.__version__},
            "query_prefix": QUERY_PREFIX, "doc_prefix": DOC_PREFIX, "chunking": "term entry 1件=文書1件(語・別名・語義・根拠行)",
            "terms_sha256": sha256_obj(terms_obj), "sources_sha256": _registry_hash(reg),
            "term_ids": [t["id"] for t in terms], "doc_sha256": [sha256_obj(d) for d in docs]}
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "embeddings.npy", emb)
    write_json(index_dir / "index_meta.json", meta, overwrite=True)
    return {"index_dir": str(index_dir), "docs": len(docs), "meta": meta}


def ruri_search(query: str, terms_obj: dict, reg: Optional[Registry], index_dir: Path, *, top_k: int = 5,
                local_files_only: bool = False) -> dict:
    meta_path = index_dir / "index_meta.json"
    if not meta_path.exists():
        raise CtrError("index_missing", "build-index を先に実行してください")
    meta = read_json(meta_path)
    stale = []
    if meta["terms_sha256"] != sha256_obj(terms_obj):
        stale.append("terms_changed")
    if meta["sources_sha256"] != _registry_hash(reg):
        stale.append("sources_changed")
    if stale:
        return {"engine": "ruri", "status": "stale_index", "reasons": stale, "hits": [],
                "note": "旧い索引を最新として使わない。build-index で作り直す"}
    st, SentenceTransformer, util = _load_st()
    import numpy as np
    model = SentenceTransformer(meta["model_id"], local_files_only=local_files_only,
                                **({"revision": meta["model_revision"]} if meta["model_revision"] != "unknown" else {}))
    q = model.encode([meta["query_prefix"] + query], convert_to_numpy=True, normalize_embeddings=True)
    corpus = np.load(index_dir / "embeddings.npy")
    res = util.semantic_search(q, corpus, top_k=top_k)[0]
    hits = [{"rank": i + 1, "term_id": meta["term_ids"][r["corpus_id"]], "score": round(float(r["score"]), 6)}
            for i, r in enumerate(res)]
    return {"engine": "ruri", "status": "ok", "hits": hits, "log": {"model_id": meta["model_id"], "model_revision": meta["model_revision"],
            "tokenizer_revision": meta["tokenizer_revision"], "libs": meta["libs"], "query": query, "top_k": top_k,
            "chunking": meta["chunking"], "index_built_at": meta["created_at"]},
            "note": "score は関連度の並びを作るための値。正しさの確率ではない"}


def hit_at_k(results: dict, gold: dict, k: int) -> dict:
    """results: {task_id: [term_id...]}, gold: {task_id: term_id|None}。正解資料がない課題は分母に入れない。"""
    den = [t for t, g in gold.items() if g]
    num = [t for t in den if gold[t] in results.get(t, [])[:k]]
    return {"k": k, "numerator": len(num), "denominator": len(den),
            "value": len(num) / len(den) if den else None, "status": "evaluated" if den else "unevaluated(分母0)",
            "tasks_without_gold": len(gold) - len(den)}
