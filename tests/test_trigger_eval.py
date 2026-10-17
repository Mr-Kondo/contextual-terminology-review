"""発動精度の評価(tools/trigger_eval.py)の、書式検査・ストリーム解釈・採点の検査。モデルは呼ばない。"""
import json
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import trigger_eval as te  # noqa: E402

DATA = json.loads(te.DATA.read_text(encoding="utf-8"))


def ev(name, skill=None):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": {"skill": skill} if skill else {"x": 1}}]}})


class TriggerEvalSet(unittest.TestCase):
    def test_dataset_is_valid_and_balanced(self):
        self.assertEqual(te.validate(DATA), [])
        qs = DATA["queries"]
        for split in ("dev", "test", "test2"):
            self.assertEqual(sum(q["split"] == split and q["should_trigger"] for q in qs), 12)
            self.assertEqual(sum(q["split"] == split and not q["should_trigger"] for q in qs), 12)

    def test_validate_catches_problems(self):
        bad = {"queries": [{"id": "a", "query": "", "should_trigger": "yes", "split": "x"}, {"id": "a", "query": "q", "should_trigger": True, "split": "dev"}]}
        errs = te.validate(bad)
        self.assertTrue(any("重複" in e for e in errs) and any("query" in e for e in errs) and any("真偽値" in e for e in errs))


class Parse(unittest.TestCase):
    def test_first_skill_call_wins_and_other_tools_are_ignored(self):
        lines = [json.dumps({"type": "system"}), ev("Read"), ev("Skill", "yomiyasu"), ev("Skill", te.SKILL)]
        self.assertEqual(te.parse_stream(lines), {"fired": "yomiyasu", "finished": False})

    def test_no_skill_before_result(self):
        r = te.parse_stream([ev("Read"), json.dumps({"type": "result", "is_error": False}), ev("Skill", te.SKILL)])
        self.assertEqual((r["fired"], r["finished"]), (None, True))

    def test_garbage_lines_are_skipped(self):
        self.assertEqual(te.parse_stream(["not json", "", ev("Skill", te.SKILL)])["fired"], te.SKILL)

    def test_plugin_prefixed_name_counts_as_ours(self):
        self.assertTrue(te.is_ours("plugin:" + te.SKILL) and te.is_ours(te.SKILL))
        self.assertFalse(te.is_ours("yomiyasu") or te.is_ours(None) or te.is_ours(""))


class Score(unittest.TestCase):
    def results(self, fire):
        return [{"id": q["id"], "run": 1, "fired": fire(q), "finished": True} for q in DATA["queries"]]

    def test_perfect_routing_passes_and_borderline_is_not_counted(self):
        res = self.results(lambda q: te.SKILL if q["should_trigger"] or q.get("borderline") else None)
        r = te.score(DATA, res, "test")
        self.assertEqual((r["recall"]["hit"], r["recall"]["n"]), (12, 12))
        self.assertEqual((r["false_fire"]["fired"], r["false_fire"]["n"]), (0, 11))      # test の否定12件のうち borderline(N16)を除く
        self.assertEqual(r["borderline_fired"], {"fired": 1, "n": 1})
        self.assertTrue(r["pass"]["recall"] and r["pass"]["false_fire"])

    def test_misrouting_to_another_skill_is_reported_and_fails_recall(self):
        res = self.results(lambda q: "yomiyasu" if q["should_trigger"] else None)
        r = te.score(DATA, res, "test")
        self.assertEqual(r["recall"]["hit"], 0)
        self.assertEqual(r["other_skill_on_positive"], {"yomiyasu": 12})
        self.assertFalse(r["pass"]["recall"])

    def test_false_fire_fails_the_criterion(self):
        res = self.results(lambda q: te.SKILL)
        r = te.score(DATA, res, "test")
        self.assertFalse(r["pass"]["false_fire"])

    def test_runs_that_did_not_finish_cleanly_void_the_verdict(self):
        res = self.results(lambda q: None)
        res[0]["finished"] = False
        r = te.score(DATA, res, "all")
        self.assertIsNone(r["pass"])
        self.assertEqual(r["runs_without_clean_finish"], 1)
        self.assertIn("正常に終わっていない", r["warning"])

    def test_split_filter_uses_only_that_split(self):
        res = [r for r in self.results(lambda q: te.SKILL if q["should_trigger"] else None)]
        self.assertEqual(te.score(DATA, res, "dev")["positive_runs"], 12)
        self.assertEqual(te.score(DATA, res, "all")["positive_runs"], 36)


if __name__ == "__main__":
    unittest.main()
