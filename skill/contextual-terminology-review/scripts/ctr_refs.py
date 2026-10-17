"""資料登録簿・参照記録・引用の機械検査・末尾の出典一覧の生成。

機械検査(参照が実在し、範囲内で、引用が原文と一致する)と、意味適合(その引用が判断を支えるか)は別の状態。
このモジュールは前者だけを決める。後者は semantic_reviews に人が書いた記録を、そのまま表示する。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Optional

from ctr_common import CtrError, need_pydantic, read_json, sha256_bytes

need_pydantic()
from pydantic import BaseModel, ConfigDict, ValidationError  # noqa: E402


class Base(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Figure(Base):
    page: Optional[int] = None
    regions: list[str] = []


class Source(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")  # 来歴などの追加項目は保持する
    id: str
    title: str
    version: str
    kind: Literal["text", "pdf", "image"] = "text"
    lines: Optional[list[str]] = None
    pages: Optional[int] = None
    page_text: Optional[dict[str, str]] = None
    text_origin: Literal["original", "machine_text", "ocr", "manual"] = "original"
    figures: dict[str, Figure] = {}
    origin: str = "unknown"
    copy_of: Optional[str] = None
    relation: Optional[Literal["copy", "translation", "summary"]] = None
    link: Optional[str] = None
    sha256: Optional[str] = None


class Location(Base):
    kind: Literal["lines", "pdf_page", "figure"] = "lines"
    start: Optional[int] = None
    end: Optional[int] = None
    page: Optional[int] = None
    printed_page: Optional[str] = None
    figure: Optional[str] = None
    region: Optional[str] = None
    bbox: Optional[list[float]] = None


class Ref(Base):
    ref_id: str
    finding_ids: list[str]
    basis: Literal["source", "user_statement"] = "source"
    source_id: Optional[str] = None
    version: Optional[str] = None
    mode: Literal["direct_quote", "summary", "inference"]
    location: Optional[Location] = None
    quote: Optional[str] = None
    used_content: Optional[str] = None
    elided: bool = False
    link: Optional[str] = None
    visual_check: Literal["not_run", "agent_viewed", "human_viewed"] = "not_run"
    visual_note: Optional[str] = None


class Correction(Base):
    corrected_item: str
    basis_ref_id: str
    meaning_before: str
    meaning_after: str
    unrelated_additions: list[str] = []


class Finding(Base):
    id: str
    target: str
    judgment: Literal["confirmed", "provisional", "pending"]
    professional_fit: Literal["conformant", "misuse_with_basis", "unknown", "out_of_scope"]
    intent_clarity: Literal["explicit", "ambiguous", "insufficient_sources"]
    business_premise: Literal["agreed", "not_agreed", "unverifiable"]
    proposal_kind: Literal["meaning_preserving_fix", "needs_confirmation", "preference", "no_change"]
    reason: str
    proposal_text: Optional[str] = None
    oral_rephrase: Optional[str] = None
    ref_ids: list[str] = []
    correction: Optional[Correction] = None


class SemanticReview(Base):
    ref_id: str
    reviewer: str
    independent: bool
    verdict: Literal["supports", "does_not_support", "unclear"]
    reason: str
    date: str
    # review_finding: この参照がレビューの指摘を支えるか / user_claim: この参照が利用者の結論を支えるか(A17のような場合)
    about: Literal["review_finding", "user_claim"] = "review_finding"


class Review(Base):
    review_id: str
    purpose: str
    audience: Optional[str] = None
    medium: Optional[str] = None
    domains: list[str] = []
    intent: Optional[str] = None
    confirmed_facts: list[str] = []
    findings: list[Finding]
    refs: list[Ref]
    semantic_reviews: list[SemanticReview] = []


# ---------------------------------------------------------------- 登録簿

class Registry:
    def __init__(self, sources: list[Source]):
        self.by_id: dict[str, dict[str, Source]] = {}
        for s in sources:
            self.by_id.setdefault(s.id, {})[s.version] = s

    def lookup(self, source_id: str, version: str):
        """(source|None, error_class|None)。版違いと未登録を区別する。"""
        versions = self.by_id.get(source_id)
        if not versions:
            return None, "unknown_source_id"
        if version not in versions:
            return None, "source_version_mismatch"
        return versions[version], None

    def root(self, source: Source) -> str:
        seen, cur = set(), source
        while cur.copy_of and cur.id not in seen:
            seen.add(cur.id)
            nxt = self.by_id.get(cur.copy_of)
            if not nxt:
                return cur.copy_of
            cur = next(iter(nxt.values()))
        return cur.id


def load_registry(path) -> Registry:
    data = read_json(Path(path))
    if isinstance(data, dict):
        data = data.get("source_catalog") or data.get("sources")
    if not isinstance(data, list):
        raise CtrError("invalid_registry")
    try:
        return Registry([Source.model_validate(d) for d in data])
    except ValidationError as exc:
        raise CtrError("invalid_registry", f"{exc.error_count()} errors") from exc


def source_text_hash(s: Source) -> str:
    if s.lines is not None:
        return sha256_bytes("\n".join(s.lines).encode("utf-8"))
    return sha256_bytes(repr(sorted((s.page_text or {}).items())).encode("utf-8"))


# ---------------------------------------------------------------- 引用の一致

_NON_ASCII = r"[^\x00-\x7f]"


def normalize(text: str) -> str:
    """空白の扱いだけを緩める。全角・半角の統一(NFKC)はしない: ² が 2 になるなど意味が変わるため。
    - 非ASCII文字どうしの間の改行(と前後の空白)は取り除く。
    - それ以外の連続する空白・改行は半角空白1つにする。"""
    text = text.replace("\u3000", " ").replace("\r\n", "\n")
    text = re.sub(rf"(?<={_NON_ASCII})[ \t]*\n[ \t]*(?={_NON_ASCII})", "", text)
    return re.sub(r"\s+", " ", text).strip()


_ELLIPSIS = re.compile(r"\s*(?:…+|\[\.\.\.\]|\.{3})\s*")


def quote_matches(quote: str, original: str, elided: bool) -> bool:
    if not quote.strip():
        return False
    hay = normalize(original)
    if not elided:
        return normalize(quote) in hay
    segments = [normalize(p) for p in _ELLIPSIS.split(quote) if p.strip()]
    if len(segments) < 2:
        return False
    pos = 0
    for seg in segments:
        i = hay.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


def _range_text(src: Source, loc: Location) -> tuple[Optional[str], Optional[str]]:
    if loc.kind == "lines":
        if src.lines is None or loc.start is None:
            return None, "location_out_of_range"
        end = loc.end if loc.end is not None else loc.start
        if loc.start < 1 or end < loc.start or end > len(src.lines):
            return None, "location_out_of_range"
        return "\n".join(src.lines[loc.start - 1:end]), None
    if loc.kind == "pdf_page":
        if src.kind != "pdf" or loc.page is None or loc.page < 1 or (src.pages is not None and loc.page > src.pages):
            return None, "location_out_of_range"
        return (src.page_text or {}).get(str(loc.page), ""), None
    if loc.kind == "figure":
        fig = src.figures.get(loc.figure or "")
        if fig is None or (loc.page is not None and fig.page is not None and fig.page != loc.page):
            return None, "location_out_of_range"
        if loc.region and fig.regions and loc.region not in fig.regions:
            return None, "location_out_of_range"
        return (src.page_text or {}).get(str(fig.page), "") if fig.page else "", None
    return None, "location_out_of_range"


def check_ref(ref: Ref, reg: Registry) -> dict:
    """機械検査だけ。戻り: {status: pass|fail|needs_visual|not_applicable, errors: [...]}"""
    if ref.basis == "user_statement":
        errs = [] if ref.used_content else ["mode_content_missing"]
        return {"status": "fail" if errs else "not_applicable", "errors": errs}
    if not ref.source_id or ref.version is None:
        return {"status": "fail", "errors": ["unknown_source_id"]}
    src, err = reg.lookup(ref.source_id, ref.version)
    if err:
        return {"status": "fail", "errors": [err]}
    errors: list[str] = []
    if src.sha256 and src.sha256 != source_text_hash(src):
        errors.append("source_hash_mismatch")  # 登録後に本文が変わった(再確認候補)
    if ref.location is None:
        errors.append("location_missing")
        return {"status": "fail", "errors": errors}
    original, lerr = _range_text(src, ref.location)
    if lerr:
        errors.append(lerr)
        return {"status": "fail", "errors": errors}
    if ref.mode == "direct_quote":
        if not ref.quote:
            errors.append("quote_missing")
        elif not quote_matches(ref.quote, original, ref.elided):
            errors.append("quote_mismatch")  # 要約・言い換えを直接引用として記録した場合もここで落ちる
    elif not ref.used_content:
        errors.append("mode_content_missing")
    if errors:
        return {"status": "fail", "errors": errors}
    needs_visual = src.kind == "image" or ref.location.kind == "figure" or src.text_origin == "ocr"
    if needs_visual and ref.visual_check == "not_run":
        return {"status": "needs_visual", "errors": ["visual_check_missing"]}
    return {"status": "pass", "errors": []}


# ---------------------------------------------------------------- 警告(エラーにしない。人とAgentが確認する候補)

# 修正案が、原文・目的・本人の意図・確認済み事実・紐づく引用のどこにも無いのに足してはいけない語(責務・承認・完了状態)
PROTECTED_TERMS = ("承認", "決裁", "合意", "確定", "保証", "責任", "完了", "最終判断")
# 引用箇所の近くにあると、適用範囲や文書の状態が変わる語
CONDITION_WORDS = ("草案", "ドラフト", "旧版", "廃止", "失効", "未合意", "未承認", "未決", "暫定", "改定", "ただし", "但し", "除く", "例外")
_HEADING = ("#", "【", "■", "●", "第")


def _proposal_warnings(review: Review, ref_by_id: dict) -> list:
    out = []
    for f in review.findings:
        texts = [t for t in (f.proposal_text, f.oral_rephrase) if t]
        if not texts:
            continue
        allowed = "".join([f.target, review.purpose, review.intent or "", *review.confirmed_facts,
                           *[(ref_by_id[r].quote or "") + (ref_by_id[r].used_content or "") for r in f.ref_ids if r in ref_by_id]])
        added = [t for t in PROTECTED_TERMS if any(t in x for x in texts) and t not in allowed]
        if added:
            out.append({"class": "proposal_adds_protected_term", "finding": f.id, "terms": added,
                        "note": "修正案に、原文・本人の説明・確認済み事実・引用のどこにもない責務/承認/完了の語がある。資料にあるか確認し、無ければ外す"})
    return out


def _condition_warnings(review: Review, reg: Registry, results: dict) -> list:
    out = []
    finding_by_id = {f.id: f for f in review.findings}
    for r in review.refs:
        if r.basis != "source" or r.location is None or r.location.kind != "lines" or results[r.ref_id]["status"] != "pass":
            continue
        src, _ = reg.lookup(r.source_id or "", r.version or "")
        if not src or not src.lines:
            continue
        start, end = r.location.start, r.location.end if r.location.end is not None else r.location.start
        outside = {i: src.lines[i - 1] for i in (*range(max(1, start - 2), start), *range(end + 1, min(len(src.lines), end + 2) + 1))}
        for i in range(start - 1, 0, -1):          # 直近の見出し行
            if src.lines[i - 1].lstrip().startswith(_HEADING):
                outside.setdefault(i, src.lines[i - 1])
                break
        stated = "".join([r.quote or "", r.used_content or ""] + [
            (finding_by_id[fid].reason or "") + (finding_by_id[fid].proposal_text or "") + (finding_by_id[fid].oral_rephrase or "")
            for fid in r.finding_ids if fid in finding_by_id])
        for i, line in sorted(outside.items()):
            hit = [w for w in CONDITION_WORDS if w in line and w not in stated]
            if hit:
                out.append({"class": "surrounding_condition_unaddressed", "ref": r.ref_id, "line": i, "words": hit,
                            "note": "引用の近く(前後2行・直近の見出し)に適用範囲や文書の状態を示す語がある。指摘の理由か確認点に反映したか確認する"})
    return out


# ---------------------------------------------------------------- レビュー全体

KIND_LABEL = {"direct_quote": "直接引用", "summary": "要約", "inference": "推論"}


def _loc_text(ref: Ref) -> str:
    loc = ref.location
    if loc is None:
        return "位置なし"
    if loc.kind == "lines":
        return f"行{loc.start}" if loc.end in (None, loc.start) else f"行{loc.start}-{loc.end}"
    parts = []
    if loc.page is not None:
        parts.append(f"PDF p.{loc.page}" + (f"(誌面p.{loc.printed_page})" if loc.printed_page else ""))
    if loc.figure:
        parts.append(loc.figure)
    if loc.region:
        parts.append(loc.region)
    if loc.bbox:
        parts.append(f"座標{loc.bbox}")
    return "・".join(parts) or "位置なし"


def _short(text: str, limit: int = 50) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…(以下省略)"


def review_check(review: Review, reg: Registry) -> dict:
    ref_by_id = {r.ref_id: r for r in review.refs}
    finding_ids = {f.id for f in review.findings}
    errors: list[str] = []
    classes: set[str] = set()

    def add(cls: str, detail: str = "") -> None:
        errors.append(f"{cls}:{detail}" if detail else cls)
        classes.add(cls)

    if len(ref_by_id) != len(review.refs):
        add("duplicate_ref_id")
    if len(finding_ids) != len(review.findings):
        add("duplicate_finding_id")
    results = {r.ref_id: check_ref(r, reg) for r in review.refs}
    sem, sem_claim = {}, {}
    for s in review.semantic_reviews:  # 最後の記録が有効
        (sem if s.about == "review_finding" else sem_claim)[s.ref_id] = s
    ref_report = []
    for r in review.refs:
        res = results[r.ref_id]
        s = sem.get(r.ref_id)
        ref_report.append({"ref_id": r.ref_id, "mechanical": res["status"], "errors": res["errors"],
                           "semantic": s.verdict if s else "not_run",
                           "semantic_independent": s.independent if s else None,
                           "semantic_user_claim": sem_claim[r.ref_id].verdict if r.ref_id in sem_claim else "not_run",
                           "visual_check": r.visual_check})
        if res["status"] in ("fail", "needs_visual"):
            add("ref_check_failed" if res["status"] == "fail" else "ref_needs_visual", r.ref_id)
        for fid in r.finding_ids:
            if fid not in finding_ids:
                add("ref_points_to_unknown_finding", r.ref_id)
            elif r.ref_id not in next(f for f in review.findings if f.id == fid).ref_ids:
                add("ref_finding_mismatch", r.ref_id)
    finding_report = []
    for f in review.findings:
        ferrs = []
        for rid in f.ref_ids:
            if rid not in ref_by_id:
                ferrs.append(f"dangling_ref:{rid}")
            elif f.id not in ref_by_id[rid].finding_ids:
                ferrs.append(f"ref_finding_mismatch:{rid}")
        passing = [rid for rid in f.ref_ids if rid in results and results[rid]["status"] == "pass"
                   and ref_by_id[rid].basis == "source"]
        user_only = [rid for rid in f.ref_ids if rid in ref_by_id and ref_by_id[rid].basis == "user_statement"]
        effective = f.judgment
        if f.judgment == "confirmed" and not passing:
            # 本人の説明は意図の根拠にはなるが、専門的適合・業務上の前提の確定根拠にはしない
            ferrs.append("unsupported_confirmed_judgment" if not user_only else "confirmed_on_user_statement_only")
            effective = "needs_confirmation"
        if f.correction:
            cref = results.get(f.correction.basis_ref_id)
            if cref is None or cref["status"] != "pass":
                ferrs.append("correction_without_passing_basis")
            if f.correction.unrelated_additions:
                ferrs.append("unrelated_addition_in_correction")
        for e in ferrs:
            add(e.split(":")[0], f.id)
        finding_report.append({"id": f.id, "declared": f.judgment, "effective": effective, "errors": ferrs,
                               "passing_refs": passing})
    warnings = _proposal_warnings(review, ref_by_id) + _condition_warnings(review, reg, results)
    footer = footer_lines(review, reg, results)
    roots = {reg.root(reg.lookup(r.source_id, r.version)[0]) for r in review.refs
             if r.basis == "source" and results[r.ref_id]["status"] == "pass" and reg.lookup(r.source_id, r.version)[0]}
    return {
        "review_id": review.review_id,
        "refs": ref_report,
        "findings": finding_report,
        "errors": errors,
        "warnings": warnings,
        "error_classes": sorted(classes | {e for r in ref_report for e in r["errors"]}),
        "footer": footer,
        "independent_source_roots": sorted(roots),
        "independent_source_count": len(roots),
        "note": "warnings はエラーではない確認候補(修正案が足した責務語、引用の近くの適用条件)。mechanical は参照の存在・範囲・原文一致の検査。semantic(意味適合)は人の記録がある場合だけ表示し、機械検査の合格では埋めない。",
    }


def footer_lines(review: Review, reg: Registry, results: dict) -> list[str]:
    """出典一覧。検査済みの参照記録だけから作り、資料名・位置・引用を補わない。1参照1行。"""
    lines = []
    cited = set()
    for r in review.refs:
        res = results[r.ref_id]
        ids = "・".join(r.finding_ids) or "—"
        cited.update(r.finding_ids)
        kind = "本人の説明" if r.basis == "user_statement" else KIND_LABEL[r.mode]
        if r.basis == "user_statement":
            lines.append(f"［{ids}／{kind}］本人の説明｜—｜{_short(r.used_content or r.quote or '')}｜リンクなし(外部資料で確認済みではない)")
            continue
        src, _ = reg.lookup(r.source_id or "", r.version or "") if r.source_id else (None, None)
        title = f"{src.title}（版{src.version}）" if src else f"{r.source_id or '不明'}（版{r.version}）"
        content = _short(r.quote) if r.mode == "direct_quote" and r.quote else _short(r.used_content or "")
        link = r.link or (src.link if src and src.link else None)
        link_text = link if link else "リンク未確認"
        if res["status"] == "pass":
            lines.append(f"［{ids}／{kind}］{title}｜{_loc_text(r)}｜{content}｜{link_text}")
        else:
            lines.append(f"［{ids}／{kind}］{title}｜{_loc_text(r)}｜要確認(機械検査: {res['status']} {','.join(res['errors'])}。"
                         f"断定の根拠に使わない)｜{link_text}")
    for f in review.findings:
        if f.id not in cited:
            lines.append(f"［{f.id}／推論］参照元なし・未確認｜—｜—｜—")
    return lines
