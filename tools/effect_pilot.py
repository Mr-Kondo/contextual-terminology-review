#!/usr/bin/env python3
"""模擬の受け手による、理解度の予備試験。元の言い方(original)と、Skillの修正案(revised)を、別々の受け手に示して比べる。

**人の受け手の代わりにならない。** 受け手は別のAIモデルで、実際の同僚の知識・文脈・聞き方を持たない。項目と正解の作成者は
Skillの設計者と同じAIで、独立していない。パイプライン(単一版の配布・版を伏せた割付・自動採点)が通ることと、修正案が
理解を損なっていないかの目安を見るためのもの。人による測定の手順は docs/EFFECT-MEASUREMENT.md。

流れ(受け手の呼び出しは、このスクリプトの外で行う):
  prepare : 受け手ごとの配布物(readers/reader-NNN/tasks.json と prompt.txt)と、主催者側の割付(organizer/)を作る
            各受け手には、1項目につき一つの版だけが渡る(版は無作為・受け手の半数ずつ)。版の名前は配布物に出ない
  (受け手の呼び出し): 各 prompt.txt を別々の新しいセッションで1回ずつ実行し、回答のJSONを responses/reader-NNN.json に保存する
  score   : 回答を自動採点する。版ごとの正答率、質問ごとの差、符号検定を出す

採点と判断基準(結果を見る前に固定):
  - 正答 = 回答が正解の選択肢と完全に一致。選択肢にない回答は無回答として数える。『分からない』系の選択は誤答だが、別に割合を出す
  - 主指標 = 修正案を含む項目(CTLを除く)の質問ごとの正答率の差(revised − original)の平均
  - 『改善あり』: 平均の差が 0.15 以上で、改善した質問の数が悪化した質問の数より多い
  - 『害の疑い』: ある質問で revised の正答率が original より 0.25 以上低い。起票して原因を調べる
  - 対照(CTL: 両方の版が同一の文): 差の大きさが判定のばらつきの目安

  python3 tools/effect_pilot.py prepare --items tools/data/effect-pilot-items.json --readers 8 --seed 1 --out .work/pilot-codex
  python3 tools/effect_pilot.py score --dir .work/pilot-codex --dir .work/pilot-agy --out docs/evidence/effect-pilot.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "contextual-terminology-review" / "scripts"))

import ctr_blind as bl  # noqa: E402
from ctr_common import read_json  # noqa: E402
from ctr_improve import wilson  # noqa: E402

INSTRUCTION = ("あなたは、同じ会社で働く同僚です。次の各項目は、会議や文書で聞いた(読んだ)文です。背景の資料は与えられていません。"
               "文の内容だけから、各質問に最も適切な選択肢を一つ選んでください。回答に使う選択肢の文字列は、一字一句変えずにそのまま使ってください。\n"
               "回答はJSONだけを出力してください(前後の説明やコードフェンスは不要):\n"
               '{"answers":[{"item":"item-001","qid":"q1","answer":"<選択肢の文字列>"}]}\n')


def render_prompt(tasks: dict) -> str:
    out = [INSTRUCTION]
    for it in tasks["items"]:
        out += ["", f"## {it['id']}", f"文: {it['text']}"]
        for q in it["questions"]:
            out.append(f"- {q['qid']}: {q['prompt']}")
            out += [f"    - {c}" for c in q["choices"]]
    return "\n".join(out) + "\n"


def prepare(items_path: Path, readers: int, seed: int, out: Path) -> dict:
    items = read_json(items_path)["items"]
    res = bl.comprehension_prepare(items, [f"r{i}" for i in range(1, readers + 1)], out, seed)
    for rd in res["readers"]:
        d = out / "readers" / rd
        (d / "prompt.txt").write_text(render_prompt(read_json(d / "tasks.json")), encoding="utf-8")
    (out / "responses").mkdir(exist_ok=True)
    return {"readers": res["readers"], "out": str(out)}


def binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    p = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * p)


def collect(run_dir: Path):
    org = read_json(run_dir / "organizer" / "organizer.json")
    items = {i["id"]: i for i in read_json(run_dir / "items.json")["items"]} if (run_dir / "items.json").exists() else {}
    responses = []
    for f in sorted((run_dir / "responses").glob("reader-*.json")):
        d = read_json(f)
        responses.append({"reader": f.stem, "answers": d.get("answers", [])})
    return org, responses, items


def score_run(run_dir: Path, items_by_id: dict) -> dict:
    org, responses, _ = collect(run_dir)
    official = bl.comprehension_score(org, responses, [])
    per_q = defaultdict(lambda: {"original": [0, 0], "revised": [0, 0]})
    unsure = {"original": [0, 0], "revised": [0, 0]}
    invalid = 0
    for rd, info in org["readers"].items():
        resp = next((r for r in responses if r["reader"] == rd), {"answers": []})
        ans = {(a["item"], a["qid"]): a.get("answer") for a in resp["answers"]}
        for pub_id, m in info["mapping"].items():
            sid, ver = m["source_id"], m["version"]
            for qid, key in org["answer_keys"][sid].items():
                a = ans.get((pub_id, qid))
                choices = next(q for q in items_by_id[sid]["questions"] if q["qid"] == qid)["choices"]
                if a not in choices:
                    invalid += 1 if a else 0
                per_q[(sid, qid)][ver][1] += 1
                per_q[(sid, qid)][ver][0] += int(a == key["key"])
                unsure[ver][1] += 1
                unsure[ver][0] += int(isinstance(a, str) and ("分からない" in a or "未特定" in a) and a != key["key"])
    return {"readers": len(org["readers"]), "answered_files": len(responses), "invalid_choice_answers": invalid,
            "official_rows": official.get("rows"), "per_question": {f"{k[0]}/{k[1]}": v for k, v in per_q.items()}, "unsure": unsure}


def summarize(runs: dict, items_by_id: dict) -> dict:
    """複数の受け手(run)を合算して、質問ごとの差と全体の指標を出す。"""
    agg = defaultdict(lambda: {"original": [0, 0], "revised": [0, 0]})
    for r in runs.values():
        for q, v in r["per_question"].items():
            for ver in ("original", "revised"):
                agg[q][ver][0] += v[ver][0]
                agg[q][ver][1] += v[ver][1]
    rows, diffs, improved, worsened, harm = [], [], 0, 0, []
    for q, v in sorted(agg.items()):
        ro = v["original"][0] / v["original"][1] if v["original"][1] else None
        rr = v["revised"][0] / v["revised"][1] if v["revised"][1] else None
        diff = None if ro is None or rr is None else round(rr - ro, 4)
        control = q.startswith("CTL")
        rows.append({"question": q, "control": control, "original": {"correct": v["original"][0], "n": v["original"][1], "rate": ro and round(ro, 3)},
                     "revised": {"correct": v["revised"][0], "n": v["revised"][1], "rate": rr and round(rr, 3)}, "diff": diff})
        if control or diff is None:
            continue
        diffs.append(diff)
        improved += diff > 0
        worsened += diff < 0
        if diff <= -0.25:
            harm.append(q)
    mean = round(sum(diffs) / len(diffs), 4) if diffs else None
    ctl = [r["diff"] for r in rows if r["control"] and r["diff"] is not None]
    return {"questions": rows, "intervention_questions": len(diffs), "mean_diff": mean, "improved": improved, "worsened": worsened,
            "unchanged": len(diffs) - improved - worsened, "sign_test_p_two_sided": round(binom_two_sided(improved, improved + worsened), 4),
            "harm_suspected": harm, "control_diff": ctl,
            "verdict": {"improvement": bool(mean is not None and mean >= 0.15 and improved > worsened), "harm_suspected": bool(harm)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--readers", type=int, default=8)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("score")
    s.add_argument("--dir", type=Path, action="append", required=True)
    s.add_argument("--items", type=Path, default=ROOT / "tools" / "data" / "effect-pilot-items.json")
    s.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        res = prepare(a.items, a.readers, a.seed, a.out)
        (a.out / "items.json").write_text(a.items.read_text(encoding="utf-8"), encoding="utf-8")   # 主催者側(読み手に渡さない)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    items_by_id = {i["id"]: i for i in read_json(a.items)["items"]}
    runs = {d.name: score_run(d, items_by_id) for d in a.dir}
    report = {"scope": "模擬の受け手(別のAIモデル)による予備試験。人の受け手の代わりにならない。項目と正解の作成者はSkillの設計者と同じAIで独立していない",
              "runs": {k: {x: v[x] for x in ("readers", "answered_files", "invalid_choice_answers", "unsure")} for k, v in runs.items()},
              "overall": summarize(runs, items_by_id), "by_run": {k: summarize({k: v}, items_by_id) for k, v in runs.items()}}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    ov = report["overall"]
    print(json.dumps({"mean_diff": ov["mean_diff"], "improved": ov["improved"], "worsened": ov["worsened"], "p": ov["sign_test_p_two_sided"],
                      "harm_suspected": ov["harm_suspected"], "control_diff": ov["control_diff"], "verdict": ov["verdict"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
