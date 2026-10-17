"""検索(一致検索・任意のRuri)とPDF抽出。Ruri・pdfplumber が無い環境では、該当テストは skip(未実施)になり、合格に数えない。"""
import json
import os
import sys
import unittest
from unittest import mock

from helpers import ACCEPT, FIXTURES, HAS_PDFPLUMBER, HAS_ST, TmpCase

import ctr_search as se
from ctr_common import CtrError, read_json, sha256_obj, write_json
from ctr_refs import load_registry

TERMS = {"schema_version": 1, "terms": [
    {"id": "t-own", "term": "取りまとめ", "aliases": ["とりまとめ"], "sense": "主担当として論点整理・調整・成果物作成を行う", "status": "adopted",
     "scope": {"kind": "project", "project": "prj-a"}, "source": {"source_id": "owner", "version": "1", "start_line": 1, "end_line": 1}},
    {"id": "t-own-b", "term": "取りまとめ", "sense": "資料を集約する意味(別案件)", "status": "adopted", "scope": {"kind": "project", "project": "prj-b"}},
    {"id": "t-idem", "term": "冪等", "sense": "繰り返しても同じ対象状態になる性質", "status": "candidate", "scope": {"kind": "professional"},
     "source": {"source_id": "api", "version": "1", "start_line": 1, "end_line": 1}, "valid_to": "2026-12-31"},
    {"id": "t-like", "term": "引き渡し", "sense": "個人の好みの表記", "status": "adopted", "scope": {"kind": "personal"}},
    {"id": "t-hash", "term": "ハッシュ値", "sense": "復号して元の入力へ戻すための値ではない", "status": "adopted", "scope": {"kind": "professional"},
     "source": {"source_id": "security", "version": "1", "start_line": 2, "end_line": 2}},
    {"id": "t-avail", "term": "可用性", "sense": "必要なときに利用可能である性質", "status": "adopted", "scope": {"kind": "professional"},
     "source": {"source_id": "cloud", "version": "1", "start_line": 1, "end_line": 1}},
]}


class Exact(TmpCase):
    def test_project_scope_alias_time_and_personal_are_handled(self):
        r = se.exact_search(TERMS, "私がとりまとめます。冪等です。", project="prj-a", as_of="2026-10-17")
        ids = {h["term_id"]: h for h in r["hits"]}
        self.assertEqual(set(ids), {"t-own", "t-idem"})
        self.assertEqual(ids["t-own"]["via"], "alias")
        self.assertEqual(ids["t-idem"]["status"], "candidate")                       # 確認候補。採用済みとは別に表示
        b = se.exact_search(TERMS, "取りまとめ", project="prj-b")
        self.assertEqual([h["term_id"] for h in b["hits"]], ["t-own-b"])               # 同じ語の複数の語義が案件で分かれる
        self.assertEqual(se.exact_search(TERMS, "冪等", as_of="2027-01-01")["hits"], [])  # 有効期間外
        p = se.exact_search(TERMS, "引き渡します")
        self.assertTrue(p["hits"][0]["personal_preference"])                          # 個人の好みは専門定義と区別

    def test_hit_at_k_uses_only_tasks_with_gold_and_zero_denominator_is_unevaluated(self):
        res = {"q1": ["a", "b"], "q2": ["c"], "q3": ["z"]}
        gold = {"q1": "b", "q2": "x", "q3": None}                                     # q3 は正解資料なし
        self.assertEqual(se.hit_at_k(res, gold, 1), {"k": 1, "numerator": 0, "denominator": 2, "value": 0.0, "status": "evaluated", "tasks_without_gold": 1})
        self.assertEqual(se.hit_at_k(res, gold, 2)["numerator"], 1)
        none = se.hit_at_k(res, {"q3": None}, 3)
        self.assertEqual((none["denominator"], none["value"], none["status"]), (0, None, "unevaluated(分母0)"))


class RuriWithoutDependency(TmpCase):
    def test_missing_dependency_is_reported_not_recorded_as_success(self):
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            with self.assertRaises(CtrError) as cm:
                se.build_index(TERMS, None, self.tmp / "idx")
        self.assertEqual(cm.exception.code, "ruri_unavailable")
        self.assertIn("成功として記録しない", cm.exception.message)

    def test_A27_stale_index_is_refused_before_loading_any_model(self):
        idx = self.mk("idx")
        reg = load_registry(ACCEPT)
        meta = {"index_format": 1, "terms_sha256": sha256_obj(TERMS), "sources_sha256": se._registry_hash(reg), "term_ids": [],
                "model_id": "m", "model_revision": "unknown", "created_at": "t", "libs": {}, "query_prefix": "q", "chunking": "c"}
        write_json(idx / "index_meta.json", meta)
        changed = json.loads(json.dumps(TERMS))
        changed["terms"][0]["sense"] = "変更後の語義"
        res = se.ruri_search("取りまとめ", changed, reg, idx)
        self.assertEqual((res["status"], res["reasons"], res["hits"]), ("stale_index", ["terms_changed"], []))   # 旧索引を最新として使わない
        src = json.loads(ACCEPT.read_text(encoding="utf-8"))["source_catalog"]
        src[0]["lines"] = [src[0]["lines"][0], "最終承認は担当者が行う。"]
        from ctr_refs import Registry, Source
        reg2 = Registry([Source.model_validate(s) for s in src])
        self.assertEqual(se.ruri_search("x", TERMS, reg2, idx)["reasons"], ["sources_changed"])
        with self.assertRaises(CtrError) as cm:
            se.ruri_search("x", TERMS, reg, self.tmp / "none")
        self.assertEqual(cm.exception.code, "index_missing")


@unittest.skipUnless(HAS_ST and os.environ.get("CTR_RUN_RURI") == "1", "Ruri実検索は未実施(sentence-transformers と CTR_RUN_RURI=1 が必要)")
class RuriReal(TmpCase):
    """実モデルでの検索。模擬ではない。モデル取得にネットワーク権限が必要。"""

    def test_real_ruri_index_and_search_with_recorded_versions_and_staleness(self):
        reg = load_registry(ACCEPT)
        idx = self.mk("idx")
        info = se.build_index(TERMS, reg, idx, model_id=os.environ.get("CTR_RURI_MODEL", se.DEFAULT_MODEL),
                              local_files_only=os.environ.get("CTR_RURI_OFFLINE") == "1")
        meta = info["meta"]
        for k in ("model_id", "model_revision", "tokenizer_revision", "libs", "query_prefix", "doc_prefix", "chunking", "terms_sha256"):
            self.assertIn(k, meta)
        self.assertEqual(meta["libs"].keys(), {"sentence_transformers", "torch", "transformers", "numpy"})
        res = se.ruri_search("暗号を復号してハッシュ値から元の文字列に戻したい", TERMS, reg, idx, top_k=3,
                             local_files_only=os.environ.get("CTR_RURI_OFFLINE") == "1")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(res["hits"]), 3)
        self.assertTrue(all(0 <= abs(h["score"]) <= 1.0001 for h in res["hits"]))
        self.assertIn("確率ではない", res["note"])
        self.assertEqual(res["log"]["top_k"], 3)
        changed = json.loads(json.dumps(TERMS))
        changed["terms"].append({"id": "t-new", "term": "新語", "sense": "追加"})
        self.assertEqual(se.ruri_search("x", changed, reg, idx)["status"], "stale_index")


@unittest.skipUnless(HAS_PDFPLUMBER, "pdfplumber 未導入: PDF抽出は未実施")
class Pdf(TmpCase):
    def test_extract_returns_pages_text_layout_and_does_not_invent_printed_page_numbers(self):
        import ctr_pdf
        r = ctr_pdf.extract_pdf(FIXTURES / "figure1.pdf", "fig", "1", "t", with_layout=True)
        self.assertEqual((r["pages"], r["kind"], r["page_text"]["1"]), (1, "pdf", "破線：未承認"))
        self.assertIn("layout", r)
        self.assertNotIn("printed_page", json.dumps(r))                                # 誌面ページ番号は補わない
        self.assertEqual(r["extraction"]["pages_without_text"], [])

    def test_pdf_without_text_layer_is_flagged_for_visual_or_ocr(self):
        import ctr_pdf
        from PIL import Image
        img = Image.new("RGB", (200, 100), "white")
        p = self.tmp / "scan.pdf"
        img.save(p, "PDF")                                                             # 画像だけのPDF(スキャン相当)
        r = ctr_pdf.extract_pdf(p, "scan", "1", "t")
        self.assertEqual(r["extraction"]["pages_without_text"], [1])


if __name__ == "__main__":
    unittest.main()
