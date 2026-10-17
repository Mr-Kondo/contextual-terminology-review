"""意味判断ケース(A01〜A12, A17, A19, A20, A28, A29)に対する、Skill手順に従って作成した出力の例。

作成者は実装担当のAI。独立した確認者ではないので、意味の合否は「pending_independent_review」のまま。
テストが確認するのは、(1)スキーマ、(2)参照の機械検査、(3)禁止変更の語彙ガード(必要条件であって十分条件ではない)、
(4)ケースごとの構造上の期待(4軸の値など)だけ。意味・適用条件の審査は tools/semantic_sheet.py が作る確認票で人が行う。
"""
from __future__ import annotations

OWNER1 = {"kind": "lines", "start": 1, "end": 1}
OWNER2 = {"kind": "lines", "start": 2, "end": 2}


def ref(rid, fids, sid, a, b, quote, mode="direct_quote", **kw):
    r = {"ref_id": rid, "finding_ids": fids, "source_id": sid, "version": "1", "mode": mode,
         "location": {"kind": "lines", "start": a, "end": b}}
    if mode == "direct_quote":
        r["quote"] = quote
    else:
        r["used_content"] = quote
    r.update(kw)
    return r


def finding(fid, target, judgment, fit, clarity, premise, kind, reason, proposal=None, oral=None, refs=(), **kw):
    f = {"id": fid, "target": target, "judgment": judgment, "professional_fit": fit, "intent_clarity": clarity,
         "business_premise": premise, "proposal_kind": kind, "reason": reason, "ref_ids": list(refs)}
    if proposal:
        f["proposal_text"] = proposal
    if oral:
        f["oral_rephrase"] = oral
    f.update(kw)
    return f


def review(rid, purpose, findings, refs, **kw):
    return {"review_id": rid, "purpose": purpose, "domains": kw.pop("domains", ["分野横断"]), "findings": findings,
            "refs": refs, **kw}


Q = {
    "owner1": "担当者は論点の整理、関係者調整、成果物の作成を主担当として行う。",
    "owner2": "最終承認は部長が行う。",
    "arch1": "本発注の成果物はアーキテクチャ設計書一式である。",
    "arch2": "サービスの開発と本番公開は本発注の成果物に含まない。",
    "whole1": "本発注の成果物は設計書と本番利用可能なサービス一式である。",
    "whole2": "設計書だけの提出は、サービス一式の納品完了を意味しない。",
    "whole3": "本案件では部分引渡しの合意はない。",
    "api1": "このAPIでは冪等を、同じ操作を繰り返しても一度の実行と同じ対象状態になる性質として扱う。",
    "api2": "請求作成APIは同じ入力を繰り返すたびに別の請求を追加する。",
    "cloud1": "この設計では可用性を、必要なときに利用可能である性質として説明する。",
    "cloud2": "可用性99.9%は目標であり、今回の実測値ではない。",
    "net1": "ログにはタイムアウトとだけ記録されている。",
    "net2": "接続、読み取り、処理全体のどの期限を超えたかは未特定である。",
    "sec1": "この仕様では暗号化を、対応する復号によって平文へ戻す処理として扱う。",
    "sec2": "この仕様のハッシュ値は、復号して元の入力へ戻すための値ではない。",
    "emb1": "埋め込み検索の得点は、候補資料の関連性を並べるために使う。",
    "emb2": "得点は用語の正しさの確率ではない。",
    "emb3": "この試行では埋め込みモデルをまだ実行していない。",
    "eng2": "この資料のaは加速度で、単位はm/s²である。",
    "biz1": "この計画の売上高は、費用を差し引く前の販売額である。",
    "biz2": "この計画の利益は、売上高から指定された費用を差し引いた額である。",
}

CASES = {
    "A01": {
        "text": "私が取りまとめます。", "sources": ["owner"],
        "review": review("A01", "担当表明のレビュー", [finding(
            "F1", "私が取りまとめます", "confirmed", "conformant", "ambiguous", "agreed", "meaning_preserving_fix",
            "「取りまとめ」だけでは主担当の範囲が伝わらない。資料は主担当の範囲と、最終承認者が別であることを定めている。",
            "論点の整理、関係者調整、成果物の作成は私が主担当として進めます。最終承認は部長が行います。",
            "論点整理と調整と資料づくりは私が主担当です。承認は部長です。", ["r1", "r2"])],
            [ref("r1", ["F1"], "owner", 1, 1, Q["owner1"]), ref("r2", ["F1"], "owner", 2, 2, Q["owner2"])],
            intent="論点整理、調整、成果物作成を自分が主担当として行う"),
        "forbid": ["私が最終承認", "最終承認します", "最終承認を行います"],
        "expect": {"premise": "agreed", "refs_pass": 2},
    },
    "A02": {
        "text": "私が取りまとめます。", "sources": [],
        "review": review("A02", "資料なしの担当表明", [finding(
            "F1", "私が取りまとめます", "provisional", "conformant", "ambiguous", "unverifiable", "needs_confirmation",
            "「取りまとめ」の責務の範囲は資料がなく確認できない。主担当の意図なら言い換えられるが、合意の有無は未確認。",
            "（主担当のつもりで、担当範囲が確認できた場合に）論点整理と調整は私が主担当で進めます。",
            None, [])], []),
        "forbid": ["合意済み", "承認権", "最終承認"],
        "expect": {"premise": "unverifiable", "no_refs": True},
    },
    "A03": {
        "text": "設計書を引き渡します。サービスは未リリースです。", "sources": ["architecture"],
        "review": review("A03", "成果物範囲が資料で分かる場合", [finding(
            "F1", "サービスは未リリースです", "confirmed", "conformant", "explicit", "agreed", "meaning_preserving_fix",
            "本発注の成果物は設計書一式で、サービスの開発と本番公開は含まれない。未リリースは成果物の未完を意味しない。",
            "アーキテクチャ設計書一式を引き渡します。サービスの開発と本番公開は本発注の対象外のため、未リリースです。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "architecture", 1, 1, Q["arch1"]), ref("r2", ["F1"], "architecture", 2, 2, Q["arch2"])]),
        "forbid": ["部分引渡し", "検収完了", "検収済み", "検収が完了"],
        "expect": {"premise": "agreed", "refs_pass": 2},
    },
    "A04": {
        "text": "設計書を引き渡したので全成果物の納品は完了です。", "sources": ["whole-service"],
        "review": review("A04", "全成果物完了の主張", [finding(
            "F1", "全成果物の納品は完了です", "confirmed", "misuse_with_basis", "explicit", "not_agreed", "meaning_preserving_fix",
            "この案件の成果物は設計書とサービス一式で、設計書だけの提出はサービス一式の納品完了を意味しない。部分引渡しの合意もない。",
            "設計書を提出しました。設計書の提出だけでは、サービス一式の納品完了にはなりません。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "whole-service", 2, 2, Q["whole2"]), ref("r2", ["F1"], "whole-service", 3, 3, Q["whole3"])]),
        "forbid": ["部分引渡しが成立", "部分納品が成立", "部分引渡しとして完了"],
        "expect": {"premise": "not_agreed", "refs_pass": 2},
    },
    "A05": {
        "text": "設計書を引き渡します。サービスは未リリースです。", "sources": [],
        "review": review("A05", "成果物範囲が不明な場合", [finding(
            "F1", "設計書を引き渡します。サービスは未リリースです", "provisional", "unknown", "insufficient_sources", "unverifiable",
            "needs_confirmation", "未リリースだけでは、設計書のみの納品か、部分引渡しか、全体の遅れかを決められない。成果物の範囲が分からない。",
            "（成果物が設計書一式の場合）設計書一式を引き渡します。サービスは本発注の範囲外のため未リリースです。"
            "（範囲が未確認の場合）まず成果物の範囲を確認させてください。", None, [])], []),
        "forbid": ["部分引渡しです", "全面納品です", "納品が完了しました"],
        "expect": {"premise": "unverifiable", "no_refs": True},
    },
    "A06": {
        "text": "この請求作成APIは同じ入力を繰り返せるので冪等です。", "sources": ["api"],
        "review": review("A06", "冪等の用法", [finding(
            "F1", "同じ入力を繰り返せるので冪等", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
            "このAPIの定義では、繰り返しても一度の実行と同じ状態になる性質が冪等。請求作成APIは繰り返すたびに別の請求を追加する。"
            "応答本文の一致だけでは判定しない。",
            "この請求作成APIは同じ入力を繰り返すと別の請求が追加されるため、冪等ではありません。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "api", 1, 1, Q["api1"]), ref("r2", ["F1"], "api", 2, 2, Q["api2"])]),
        "forbid": ["応答本文が同じ", "応答が等しい"],
        "expect": {"refs_pass": 2},
    },
    "A07": {
        "text": "この設計は可用性99.9%を目標とします。", "sources": ["cloud"],
        "review": review("A07", "正しい用法の確認", [finding(
            "F1", "可用性99.9%を目標とします", "confirmed", "conformant", "explicit", "agreed", "no_change",
            "資料は可用性99.9%を目標とし、実測値ではないと定める。「目標」という表現は資料と一致する。修正不要。",
            None, None, ["r1", "r2"])],
            [ref("r1", ["F1"], "cloud", 1, 1, Q["cloud1"]), ref("r2", ["F1"], "cloud", 2, 2, Q["cloud2"])]),
        "forbid": ["達成済み", "実測で99.9"],
        "expect": {"kind": "no_change", "fit": "conformant", "refs_pass": 2},
    },
    "A08": {
        "text": "タイムアウトなので接続に失敗しました。", "sources": ["network"],
        "review": review("A08", "タイムアウトの種類", [finding(
            "F1", "タイムアウトなので接続に失敗", "provisional", "unknown", "insufficient_sources", "unverifiable", "needs_confirmation",
            "ログは「タイムアウト」とだけ記録し、接続・読み取り・処理全体のどの期限かは未特定。接続失敗と断定する根拠が足りない。",
            "タイムアウトが発生しました（接続・読み取り・処理全体のどの期限かは未特定です）。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "network", 1, 1, Q["net1"]), ref("r2", ["F1"], "network", 2, 2, Q["net2"])]),
        "forbid": ["接続タイムアウトでした", "接続タイムアウトです"],
        "expect": {"fit": "unknown", "refs_pass": 2},
    },
    "A09": {
        "text": "ハッシュ値を復号して元の入力を復元します。", "sources": ["security"],
        "review": review("A09", "ハッシュと復号", [finding(
            "F1", "ハッシュ値を復号して", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
            "この仕様では、復号は暗号化に対応する処理で、ハッシュ値は復号して元の入力へ戻すための値ではない。",
            "元の入力を復元する必要がある場合は、ハッシュ値ではなく、暗号化と対応する復号の対象にするかどうかを確認してください。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "security", 1, 1, Q["sec1"]), ref("r2", ["F1"], "security", 2, 2, Q["sec2"])]),
        "forbid": ["AES", "bcrypt", "SHA-", "RSA", "Argon"],
        "expect": {"fit": "misuse_with_basis", "refs_pass": 2},
    },
    "A10": {
        "text": "Ruriの得点0.9なのでこの用語は90%の確率で正しいです。", "sources": ["embedding"],
        "review": review("A10", "検索得点の解釈", [finding(
            "F1", "得点0.9なので90%の確率で正しい", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
            "得点は候補資料の関連性を並べるための値で、用語の正しさの確率ではない。この試行では埋め込みモデルをまだ実行していない。",
            "得点0.9は、候補資料の関連性の並びに使う値です。用語が正しい確率ではありません。なお、この試行ではモデルを実行していません。",
            None, ["r1", "r2", "r3"])],
            [ref("r1", ["F1"], "embedding", 1, 1, Q["emb1"]), ref("r2", ["F1"], "embedding", 2, 2, Q["emb2"]),
             ref("r3", ["F1"], "embedding", 3, 3, "この試行では埋め込みモデルをまだ実行していない。")]),
        "forbid": ["90%", "確率で正しい", "実行済み", "実行しました"],
        "expect": {"refs_pass": 3},
    },
    "A11": {
        "text": "加速度aの単位はm/sです。", "sources": ["engineering"],
        "review": review("A11", "単位の照合", [finding(
            "F1", "単位はm/s", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
            "この資料ではaは加速度で単位はm/s²。m/sは速度vの単位。単位の照合のみで、科学モデル全体の妥当性は対象外。",
            "加速度aの単位はm/s²です。", None, ["r1"],
            correction={"corrected_item": "単位 m/s → m/s²", "basis_ref_id": "r1",
                        "meaning_before": "加速度の単位を速度の単位で述べている",
                        "meaning_after": "加速度aの単位をこの資料どおりm/s²で述べる", "unrelated_additions": []})],
            [ref("r1", ["F1"], "engineering", 2, 2, Q["eng2"])]),
        "forbid": ["モデル全体は正しい", "計算は正しい"],
        "require": ["m/s²"],
        "expect": {"has_correction": True, "refs_pass": 1},
    },
    "A12": {
        "text": "費用を差し引いた売上高を利益として報告します。", "sources": ["business"],
        "review": review("A12", "売上高と利益", [finding(
            "F1", "費用を差し引いた売上高を利益として", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
            "この計画の売上高は費用を差し引く前の販売額で、利益は売上高から指定された費用を差し引いた額。「費用を差し引いた売上高」は両者を混ぜている。",
            "売上高から指定された費用を差し引いた額を、利益として報告します。",
            None, ["r1", "r2"])],
            [ref("r1", ["F1"], "business", 1, 1, Q["biz1"]), ref("r2", ["F1"], "business", 2, 2, Q["biz2"])]),
        "forbid": ["実績値", "予測値", "円"],
        "expect": {"refs_pass": 2},
    },
    "A17": {
        "text": "この引用を根拠に、私が最終承認します。", "sources": ["owner"],
        "review": review("A17", "引用が結論を支えない例", [finding(
            "F1", "この引用を根拠に、私が最終承認します", "confirmed", "unknown", "explicit", "not_agreed", "needs_confirmation",
            "引用は原文と一致するが、最終承認は部長が行うと読める。私が最終承認する根拠にならない。承認者は資料で確認する。",
            "最終承認は部長が行います。私は承認の前段（資料の取りまとめ）を担当します（担当範囲は確認が必要）。",
            None, ["r1"])],
            [ref("r1", ["F1"], "owner", 2, 2, Q["owner2"])],
            semantic_reviews=[{"ref_id": "r1", "reviewer": "実装担当AI(独立ではない)", "independent": False, "verdict": "does_not_support",
                               "about": "user_claim", "date": "2026-10-17",
                               "reason": "引用の原文一致は成立するが、『私が最終承認する』という結論は支えない"}]),
        "forbid": ["私が最終承認します", "承認権は私"],
        "expect": {"refs_pass": 1, "mechanical_valid": True, "semantic_user_claim": "does_not_support"},
    },
}


# ---- A19/A20: 図 -------------------------------------------------------------
CASES["A19"] = {
    "text": "この図では破線の経路は承認済みです。", "sources": [],
    "review": review("A19", "図を参照できない場合", [finding(
        "F1", "破線の経路は承認済みです", "provisional", "unknown", "insufficient_sources", "unverifiable", "needs_confirmation",
        "図またはスキャンPDFを読めないため、破線の意味(凡例)を確認できない。承認済みの根拠は確認不能。",
        "（図を確認できていないため）破線の意味を図の凡例で確認してから表現を決めてください。", None, [])], []),
    "forbid": ["図1", "凡例には", "未承認と書かれて", "承認済みと書かれて", "右上"],
    "expect": {"no_refs": True, "premise": "unverifiable"},
}
CASES["A20"] = {
    "text": "この図では破線の経路は承認済みです。", "sources": ["figure-pdf"], "needs_figure": True,
    "review": review("A20", "図を実際に読めた場合", [finding(
        "F1", "破線の経路は承認済みです", "confirmed", "misuse_with_basis", "explicit", "not_agreed", "meaning_preserving_fix",
        "PDFのページ1・図1の右上の凡例に「破線：未承認」とある。図の破線の矢印(開始→承認)は未承認の経路を表す。",
        "この図では、破線の経路は未承認です。", None, ["r1", "r2"])],
        [{"ref_id": "r1", "finding_ids": ["F1"], "source_id": "figure-pdf", "version": "1", "mode": "direct_quote",
          "location": {"kind": "figure", "page": 1, "figure": "図1", "region": "右上の凡例"}, "quote": "破線：未承認",
          "visual_check": "agent_viewed",
          "visual_note": "PDF1ページ目の描画と元PNGを開いて凡例の文字と破線の見本を確認(2026-10-17)。文字層は不可視で、抽出文字と一致"},
         {"ref_id": "r2", "finding_ids": ["F1"], "source_id": "figure-pdf", "version": "1", "mode": "inference",
          "location": {"kind": "figure", "page": 1, "figure": "図1", "region": "破線の矢印"},
          "used_content": "開始から承認へ向かう矢印が破線で描かれている(視覚による読み取り)。凡例の意味と組み合わせた推論",
          "visual_check": "agent_viewed", "visual_note": "矢印と凡例の対応を目視。文字抽出では得られない情報"}]),
    "forbid": ["承認済みです。"],
    "expect": {"refs_pass": 2, "visual": True},
}

# ---- A28/A29 -----------------------------------------------------------------
CASES["A28"] = {
    "text": "加速度aの単位はm/sです。", "sources": ["engineering"],
    "intent": "資料の加速度aの単位を正しく説明する",
    "review": review("A28", "根拠付き訂正の記録", [finding(
        "F1", "単位はm/s", "confirmed", "misuse_with_basis", "explicit", "agreed", "meaning_preserving_fix",
        "根拠(資料の行2)が示すm/s²へ訂正する。訂正は単位の1点のみで、責務・完了状態など他の事実は追加しない。",
        "加速度aの単位はm/s²です。", None, ["r1"],
        correction={"corrected_item": "単位 m/s → m/s²", "basis_ref_id": "r1",
                    "meaning_before": "加速度の単位が m/s（速度の単位）", "meaning_after": "加速度の単位が m/s²（資料どおり）",
                    "unrelated_additions": []})],
        [ref("r1", ["F1"], "engineering", 2, 2, Q["eng2"])]),
    "forbid": ["承認", "完了", "担当"],
    "require": ["m/s²"],
    "expect": {"has_correction": True, "refs_pass": 1},
}
CASES["A29"] = {
    "text": "同じ合意済み事実を同僚と他職種へ説明する。", "sources": ["owner"],
    "variants": {
        "同僚": "論点整理と調整と資料づくりは私が主担当です。承認は部長です。",
        "他職種": "この件では、私が論点を整理し、関係者と調整し、成果物をまとめる主担当です（まとめ役のイメージです）。"
                  "最終的な承認は部長が行います。",
    },
    "review": review("A29", "相手別の説明量", [finding(
        "F1", "私が取りまとめます", "confirmed", "conformant", "explicit", "agreed", "meaning_preserving_fix",
        "合意済みの事実(主担当の範囲・最終承認は部長)は共通。相手に応じて補足量だけ変える。",
        "論点の整理、関係者調整、成果物の作成は私が主担当です。最終承認は部長が行います。", None, ["r1", "r2"])],
        [ref("r1", ["F1"], "owner", 1, 1, Q["owner1"]), ref("r2", ["F1"], "owner", 2, 2, Q["owner2"])],
        audience="同僚/他職種"),
    "forbid": ["私が最終承認", "最終承認します", "決定権は私"],
    "expect": {"refs_pass": 2},
}
