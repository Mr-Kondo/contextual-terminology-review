"""模擬の受け手による予備試験(tools/effect_pilot.py)の、割付・秘匿・採点の検査。受け手のモデルは呼ばない。"""
import json
import sys
import unittest

from helpers import ROOT, TmpCase

sys.path.insert(0, str(ROOT / "tools"))
import effect_pilot as ep  # noqa: E402

ITEMS = ROOT / "tools" / "data" / "effect-pilot-items.json"


class EffectPilot(TmpCase):
    def prep(self, readers=8, seed=1):
        out = self.tmp / "run"
        res = ep.prepare(ITEMS, readers, seed, out)
        (out / "items.json").write_text(ITEMS.read_text(encoding="utf-8"), encoding="utf-8")
        return out, res

    def answer(self, out, fn):
        org = json.loads((out / "organizer" / "organizer.json").read_text(encoding="utf-8"))
        for rd, info in org["readers"].items():
            answers = []
            for pub, m in info["mapping"].items():
                for qid, key in org["answer_keys"][m["source_id"]].items():
                    answers.append({"item": pub, "qid": qid, "answer": fn(m["source_id"], m["version"], qid, key["key"])})
            (out / "responses" / f"{rd}.json").write_text(json.dumps({"answers": answers}, ensure_ascii=False), encoding="utf-8")

    def test_each_reader_gets_one_version_per_item_and_nothing_secret(self):
        out, res = self.prep()
        self.assertEqual(len(res["readers"]), 8)
        self.assertTrue(bl_ok(out))
        org = json.loads((out / "organizer" / "organizer.json").read_text(encoding="utf-8"))
        for item in json.loads(ITEMS.read_text(encoding="utf-8"))["items"]:
            vs = [info["mapping"][p]["version"] for info in org["readers"].values() for p, m in info["mapping"].items() if m["source_id"] == item["id"]]
            self.assertEqual((vs.count("original"), vs.count("revised")), (4, 4))      # 受け手の半数ずつ
        for rd in res["readers"]:
            tasks = (out / "readers" / rd / "tasks.json").read_text(encoding="utf-8")
            prompt = (out / "readers" / rd / "prompt.txt").read_text(encoding="utf-8")
            for secret in ("original", "revised", "answer_key", "evidence"):
                self.assertNotIn(secret, tasks)
                self.assertNotIn(secret, prompt)
            self.assertIn("同僚", prompt)

    def test_scoring_detects_improvement_and_keeps_the_control_flat(self):
        out, _ = self.prep()
        unk = "文だけでは分からない"
        self.answer(out, lambda sid, ver, qid, key: key if (ver == "revised" or sid.startswith("CTL")) else unk)
        r = ep.summarize({"run": ep.score_run(out, {i["id"]: i for i in json.loads(ITEMS.read_text(encoding="utf-8"))["items"]})}, {})
        self.assertEqual(r["mean_diff"], 1.0)
        self.assertEqual((r["improved"], r["worsened"]), (r["intervention_questions"], 0))
        self.assertEqual(r["control_diff"], [0.0])
        self.assertTrue(r["verdict"]["improvement"] and not r["verdict"]["harm_suspected"])

    def test_scoring_flags_harm_and_treats_outside_choices_as_unanswered(self):
        out, _ = self.prep()
        self.answer(out, lambda sid, ver, qid, key: key if ver == "original" else "選択肢にない回答")
        r = ep.summarize({"run": ep.score_run(out, {i["id"]: i for i in json.loads(ITEMS.read_text(encoding="utf-8"))["items"]})}, {})
        self.assertTrue(r["verdict"]["harm_suspected"] and not r["verdict"]["improvement"])
        self.assertEqual(r["improved"], 0)
        self.assertEqual(ep.binom_two_sided(0, 0), 1.0)
        self.assertAlmostEqual(ep.binom_two_sided(8, 8), 2 / 256)


def bl_ok(out):
    import ctr_blind as bl
    return bl.check_single_version(out / "readers")["ok"]


if __name__ == "__main__":
    unittest.main()
