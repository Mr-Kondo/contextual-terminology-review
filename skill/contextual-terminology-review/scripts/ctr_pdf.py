"""機械生成PDFの文字・表・ページ・位置の抽出(pdfplumber)。スキャンPDFや図の意味理解は行わない。

誌面ページ番号は抽出できないので記録しない(補って作らない)。図は、Agent の画像・PDF読解で実際に見て、
レビュー記録の ref.visual_check(agent_viewed / human_viewed)に視覚確認を残す。文字抽出だけで図を確認済みにしない。
"""
from __future__ import annotations

from pathlib import Path

from ctr_common import CtrError, sha256_file


def extract_pdf(path: Path, source_id: str, version: str, title: str, *, with_layout: bool = False) -> dict:
    try:
        import pdfplumber
    except ImportError as exc:
        raise CtrError("pdfplumber_unavailable", "pdfplumber が未導入。PDFの文字抽出は未実施(目視確認は別経路)") from exc
    page_text, layout, tables, empty = {}, {}, {}, []
    with pdfplumber.open(str(path)) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            page_text[str(i)] = text
            if not text.strip():
                empty.append(i)
            tbs = page.extract_tables()
            if tbs:
                tables[str(i)] = tbs
            if with_layout:
                layout[str(i)] = [{"text": w["text"], "x0": round(w["x0"], 1), "top": round(w["top"], 1),
                                   "x1": round(w["x1"], 1), "bottom": round(w["bottom"], 1)} for w in page.extract_words()]
    src = {"id": source_id, "title": title, "version": version, "kind": "pdf", "pages": n, "page_text": page_text,
           "text_origin": "machine_text", "figures": {}, "origin": "pdf_file", "file_sha256": sha256_file(path),
           "link": Path(path).resolve().as_uri(),
           "extraction": {"library": "pdfplumber", "pages_without_text": empty,
                          "note": "文字のないページ(スキャン等)は抽出できない。図の内容・矢印・凡例の関係は視覚確認が必要"}}
    if tables:
        src["tables"] = tables
    if layout:
        src["layout"] = layout
    return src
