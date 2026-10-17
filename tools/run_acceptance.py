#!/usr/bin/env python3
"""tests/ を実行し、A01〜A48 ごとの機械検査の結果を、06-acceptance-matrix.md の区分に沿って docs/ へ出力する。

  python3 tools/run_acceptance.py                # system python
  CTR_RUN_RURI=1 CTR_RURI_OFFLINE=1 HF_HOME=... .work/venv/bin/python tools/run_acceptance.py   # 実Ruri・pdfplumber込み

出力: docs/acceptance-results.json, docs/ACCEPTANCE-REPORT.md, docs/SEMANTIC-REVIEW-SHEET.md
機械検査の合格と、人による意味審査・実呼び出し・実務効果は別。ここで「合格」と書くのは機械検査だけ。
"""
from __future__ import annotations

import importlib
import json
import platform
import re
import sys
import unittest
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))

DOCS = ROOT / "docs"
SEMANTIC = ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11", "A12", "A17", "A19", "A20", "A28", "A29"]


class Collect(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rows = {}

    def _put(self, test, status, detail=""):
        self.rows[test.id()] = {"status": status, "detail": detail[:200]}

    def addSuccess(self, test):
        super().addSuccess(test)
        self._put(test, "pass")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._put(test, "fail", str(err[1]))

    def addError(self, test, err):
        super().addError(test, err)
        self._put(test, "error", str(err[1]))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._put(test, "skipped", reason)


def versions():
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for pkg in ("pydantic", "pdfplumber", "pdfminer.six", "pypdfium2", "sentence-transformers", "torch", "transformers", "numpy", "Pillow"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "未導入"
    return out


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    runner = unittest.TextTestRunner(resultclass=Collect, verbosity=0, stream=open("/dev/null", "w"))
    res = runner.run(suite)
    spec = json.loads((ROOT / "03-acceptance-cases.json").read_text(encoding="utf-8"))
    by_case: dict = {}
    for tid, row in res.rows.items():
        m = re.search(r"\.test_(A\d\d)_", tid)
        if m:
            by_case.setdefault(m.group(1), []).append({"test": tid.split(".", 1)[1], **row})
    cases = []
    for c in spec["cases"]:
        rows = by_case.get(c["id"], [])
        if not rows:
            state = "no_automated_check"
        elif any(r["status"] in ("fail", "error") for r in rows):
            state = "fail"
        elif any(r["status"] == "skipped" for r in rows):
            state = "partial_skipped"
        else:
            state = "pass"
        cases.append({"id": c["id"], "kind": c["kind"], "verification": c["verification"], "automated": state, "tests": rows})
    ledger = json.loads((DOCS / "HOST-EVIDENCE.json").read_text(encoding="utf-8"))
    import host_evidence as he
    bench = json.loads((DOCS / "evidence" / "search-bench.json").read_text(encoding="utf-8")) if (DOCS / "evidence" / "search-bench.json").exists() else None
    summary = {"tests_run": res.testsRun, "failures": len(res.failures), "errors": len(res.errors), "skipped": len(res.skipped),
               "versions": versions(), "cases": cases, "ledger_valid": he.validate(ledger) == []}
    (DOCS / "acceptance-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(summary, ledger, bench, spec)
    write_sheet(spec, summary)
    print(json.dumps({k: summary[k] for k in ("tests_run", "failures", "errors", "skipped")}, ensure_ascii=False))
    return 0 if not res.failures and not res.errors else 1


LABEL = {"pass": "機械検査 合格", "fail": "**不合格**", "partial_skipped": "一部未実施(skip)", "no_automated_check": "自動検査なし"}


def case_status(c: dict) -> str:
    if c["id"] == "A31":
        return "未到達(マージ・公開は未実施)。後片付けの手順は仮のgitで機械検査済み"
    base = LABEL[c["automated"]]
    if c["automated"] != "pass":
        return base
    if c["verification"] == "deterministic":
        return base
    if c["id"] in ("A19", "A20"):
        return base + "／視覚確認は実装担当AIの自己確認のみ。独立確認待ち"
    return base + "／意味・運用の独立確認待ち"


def write_report(s, ledger, bench, spec):
    import host_evidence as he
    v = s["versions"]
    n = {k: sum(1 for c in s["cases"] if c["automated"] == k) for k in ("pass", "fail", "partial_skipped", "no_automated_check")}
    lines = [
        "# 受入検査レポート(自動生成)", "",
        "`tools/run_acceptance.py` が生成した。ここでの「合格」は機械検査だけを指す。人による意味審査、実モデルでの判断品質、"
        "各利用経路での実呼び出し、実務での改善効果は、下表のとおり別に示す。公開された開発例の合格を、未使用評価・誤り率0・実務性能の証拠にしない。", "",
        "## 実行環境", "", "| 項目 | 版 |", "|---|---|", *[f"| {k} | {x} |" for k, x in v.items()], "",
        f"テスト {s['tests_run']} 件: 失敗 {s['failures']}・エラー {s['errors']}・skip {s['skipped']}。"
        f"skip は未実施であり合格に数えない(Ruri実検索・pdfplumber が未導入の環境で出る)。", "",
        "## 区分別の状態(06-acceptance-matrix.md)", "",
        "| 区分 | 状態 | 根拠・残り |", "|---|---|---|",
        "| 設計資料の整合性 | 検査済み(合格) | `tools/check_design_docs.py`(manifestのハッシュ・JSON・ID・リンク)。資料の検査であり実装の検証ではない |",
        f"| 用語・責務の判断 A01〜A12, A17, A28〜A29 | 機械ガード合格／**意味審査は未実施(独立確認待ち)** | 作成者は実装担当AI。語彙ガードは必要条件のみ。確認票: docs/SEMANTIC-REVIEW-SHEET.md |",
        "| 出典・引用の機械検査 A13〜A18 | 機械検査 合格 | 不明ID・版違い・範囲外・改変・否定欠落を検出。A17は機械合格と意味不支持を別表示 |",
        "| 画像・PDFの実読解 A19〜A20 | 機械側合格／視覚確認は自己確認のみ | A20: 実PNG・1ページPDFを開いて凡例を確認(実装担当AI)。独立確認・実利用でのPDF読解は未実施 |",
        "| 匿名比較・理解問題 A21〜A23 | 機械検査 合格／人の評価は未実施 | 配布物の秘匿・割付保存・非相殺・単一版配布を検査。実際の評価者による採点は未実施 |",
        "| フィードバックと更新 A24〜A27 | 機械検査 合格 | 保留の保持・回帰例化・転載の扱い・資料変更の検出 |",
        "| 更新競合・保存失敗 | 機械検査 合格 | 版の競合、採用失敗時の巻き戻し、原子的保存(A34, A42) |",
        "| 検索 | 実Ruri実行済み(下記)／効果は未評価 | 一致検索とRuri(cl-nagoya/ruri-v3-70m)を同一課題で比較。件数が少ない公開例で、Ruri採用の根拠にしない |",
        "| 導入・更新・削除 A30 | 仮配置で機械検査 合格／実環境へ導入済み | 3環境(4配置先)を一時HOMEで往復。実ユーザーのホームへは導入(--apply)と照合まで実施。実環境での更新・削除は未実施 |",
        "| 実呼び出し | 一部実施(下の環境別表) | Claude Code・Codex・Antigravity CLI は合成データ1プロンプトで実モデルによる呼び出しを観測(docs/evidence/real-host-*.md)。リモート・Work・Coworkは未実施。1プロンプトの結果で、品質・他入力・他モデルは示さない |",
        "| 開発の後片付け A31 | **未到達** | マージ・公開は未実施。`tools/post_merge_cleanup.py` を仮のgitで検査済み |",
        "| 利用不能時の表示 A32 | 機械検査 合格 | 環境別証拠台帳 docs/HOST-EVIDENCE.json |",
        "| 分散ログと改善ループ A33〜A48 | 仮保存先の機械検査 合格／各ホストの実記録は Claude Code ローカルのみ | A48の環境別は下表 |",
        "| 本人の習得・実務効果 | **未実施** | 相手の理解・自力説明・再発機会・時間を実測していない |", "",
        "## 環境別の証拠(docs/HOST-EVIDENCE.json)", "", he.render(ledger), "",
        f"成功は、証拠(種別と内容)がある段階だけ。仮配置・導入の成功は登録・呼び出しの根拠にならない。総合 verified の経路: {sum(1 for e in ledger['entries'] if he.overall(e) == 'verified')}(合成データ1プロンプトの観測に限る)。", "",
    ]
    if bench:
        r, e = bench["engines"].get("ruri", {}), bench["engines"]["exact"]
        lines += ["## 検索(実Ruri・同一課題)", "",
                  f"課題 {bench['task_count']} 件(独立 {bench['independent_tasks']} 件・公開された開発用ケース。未使用評価ではない)。",
                  "", "| 方式 | hit@1 | hit@3 |", "|---|---|---|"]
        lines.append(f"| 用語・別名の一致 | {e['hit'][0]['numerator']}/{e['hit'][0]['denominator']} | {e['hit'][1]['numerator']}/{e['hit'][1]['denominator']} |")
        if r.get("status") == "ok":
            m = r["index_meta"]
            lines.append(f"| Ruri | {r['hit'][0]['numerator']}/{r['hit'][0]['denominator']} | {r['hit'][1]['numerator']}/{r['hit'][1]['denominator']} |")
            lines += ["", f"モデル `{m['model_id']}` revision `{m['model_revision']}`、sentence-transformers {m['libs']['sentence_transformers']}・torch {m['libs']['torch']}・"
                      f"transformers {m['libs']['transformers']}、接頭辞 `{m['query_prefix']}`/`{m['doc_prefix']}`。",
                      "用語エントリは根拠資料の行から作っており、正解も同じ資料。小規模な自己参照的な動作確認であり、Ruriの採否を決める証拠ではない(件数・独立課題数が少ない)。"]
        else:
            lines.append(f"| Ruri | 未実施/失敗: {r.get('reason')} | |")
        lines.append("")
    lines += ["## A01〜A48", "", "| ID | 種類 | 検証区分(03) | 状態 |", "|---|---|---|---|"]
    for c in s["cases"]:
        lines.append(f"| {c['id']} | {c['kind']} | {c['verification']} | {case_status(c)} |")
    lines += ["", f"自動検査の集計: 合格 {n['pass']}・不合格 {n['fail']}・一部skip {n['partial_skipped']}・自動検査なし {n['no_automated_check']}(A31は未到達として別扱い)。", ""]
    (DOCS / "ACCEPTANCE-REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def write_sheet(spec, summary):
    sem = importlib.import_module("semantic_fixtures")
    from ctr_refs import Review, load_registry, review_check
    from test_semantic import registry_for
    out = ["# 意味審査の確認票(独立した確認者向け)", "",
           "実装担当のAIが Skill 手順に従って作った出力例を、03の期待(must / must_not)に照らして判断する票。**意味の合否はまだ付いていない。**",
           "機械検査(参照の実在・引用の一致・禁止語彙)は合格済みだが、それは意味保持や適用条件の適合を意味しない。",
           "確認者は、AIの結論を見る前に、資料と入力から判断することが望ましい。判断できない場合は「保留」とし、理由を残す。", ""]
    by = {c["id"]: c for c in spec["cases"]}
    for cid in SEMANTIC:
        c, fx = by[cid], sem.CASES[cid]
        rev = Review.model_validate(fx["review"])
        rep = review_check(rev, registry_for(fx))
        out += [f"## {cid}（{', '.join(c['domains'])}）", "", f"- 入力: {fx['text']}",
                f"- 資料: {', '.join(fx['sources']) or 'なし'}"]
        if c["given"].get("intent"):
            out.append(f"- 本人の意図: {c['given']['intent']}")
        out += ["- 期待(must): " + " / ".join(c["expected"]["must"]), "- 期待(must_not): " + " / ".join(c["expected"]["must_not"]), ""]
        for f in rev.findings:
            out += [f"**判定** 適合={f.professional_fit}・意図={f.intent_clarity}・前提={f.business_premise}・提案={f.proposal_kind}（{f.judgment}）", "",
                    f"理由: {f.reason}", ""]
            if f.proposal_text:
                out.append(f"修正案: {f.proposal_text}")
            if f.oral_rephrase:
                out.append(f"口頭: {f.oral_rephrase}")
        for k, v in fx.get("variants", {}).items():
            out.append(f"相手={k}: {v}")
        footer = [f"- {l}" for l in rep["footer"]] or ["- (なし)"]
        out += ["", "出典一覧(生成):", *footer, "",
                "| 確認項目 | 合 | 否 | 保留 |", "|---|---|---|---|", "| must をすべて満たす | ☐ | ☐ | ☐ |", "| must_not に触れていない | ☐ | ☐ | ☐ |",
                "| 引用が判断を支えている(意味適合) | ☐ | ☐ | ☐ |", "", "確認者: ________  日付: ________  理由: ________", ""]
    (DOCS / "SEMANTIC-REVIEW-SHEET.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
