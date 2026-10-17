"""匿名二候補比較・非相殺の採点・単一版の理解問題(A21〜A23)。"""
import hashlib
import json
import unittest
from pathlib import Path

from helpers import TmpCase

import ctr_blind as bl
from ctr_common import CtrError, read_json

NAMES = ("baseline-v1", "grounded-v2")


def pairs(n=3):
    return [{"id": f"p{i}", "document_id": f"d{i}", "request": "言い直しを比較", "audience": "同僚", "context": "架空",
             "original": f"私が取りまとめます({i})", "candidates": {NAMES[0]: f"案A{i}: 論点整理は私が主担当です", NAMES[1]: f"案B{i}: 主担当として論点整理と調整を進めます"}}
            for i in range(1, n + 1)]


class Blind(TmpCase):
    def prep(self, seed=5, readers="r1,r2"):
        out = self.tmp / "blind"
        res = bl.blind_prepare(pairs(), readers.split(","), out, seed)
        return out, read_json(Path(res["organizer_file"]))

    def test_A21_distribution_has_no_method_names_or_answers_and_organizer_keeps_assignment(self):
        out, org = self.prep()
        for f in (out / "readers").rglob("*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                for secret in (*NAMES, "mapping", "baseline", "grounded", "answer_key", "expected", "gold"):
                    self.assertNotIn(secret, text)
                self.assertEqual({p.name for p in f.parent.iterdir()}, {"tasks.json"})   # 読み手に渡るのは tasks.json だけ
        self.assertTrue((out / "organizer" / "organizer.json").exists())
        self.assertFalse(any((out / "readers").rglob("organizer*")))
        for rd, info in org["readers"].items():
            actual = hashlib.sha256((out / "readers" / rd / "tasks.json").read_bytes()).hexdigest()
            self.assertEqual(info["distributed_file_sha256"], actual)              # 実際の配布物との対応を保存
            for m in info["mapping"].values():
                self.assertEqual({m["left"], m["right"]}, set(NAMES))                # 左右の割付を保存
        self.assertEqual(org["seed"], 5)
        self.assertIn("アクセス権限の隔離を達成したことにはならない", Path(bl.__file__).read_text(encoding="utf-8"))

    def test_A21_label_leak_in_candidate_text_is_refused_and_existing_distribution_is_not_overwritten(self):
        bad = pairs(1)
        bad[0]["candidates"][NAMES[0]] += " (baseline-v1)"
        with self.assertRaises(CtrError) as cm:
            bl.blind_prepare(bad, ["r1"], self.tmp / "leak", 1)
        self.assertEqual(cm.exception.code, "label_leak")
        out, _ = self.prep()
        with self.assertRaises(CtrError):
            bl.blind_prepare(pairs(), ["r1"], out, 1)

    def test_A21_same_document_keeps_orientation_and_assignments_are_balanced_by_seed(self):
        two = pairs(2) + [{**pairs(1)[0], "id": "p1b"}]            # 同じ文書(d1)の別出力
        out = self.tmp / "o2"
        res = bl.blind_prepare(two, ["r1", "r2", "r3", "r4"], out, 11)
        org = read_json(Path(res["organizer_file"]))
        for info in org["readers"].values():
            m = info["mapping"]
            self.assertEqual(m["pair-001"]["left"], m["pair-003"]["left"])         # 同一文書は同じ向き

    def responses(self, org, meaning_by_variant, pref=None):
        out = []
        for rd, info in org["readers"].items():
            rs = []
            for pid, m in info["mapping"].items():
                r = {"pair_id": pid, "meaning": {"left": meaning_by_variant[m["left"]], "right": meaning_by_variant[m["right"]]},
                     "readability": {"left": 5 if m["left"] == NAMES[0] else 3, "right": 5 if m["right"] == NAMES[0] else 3}}
                if pref:
                    r["preference"] = "left" if m["left"] == pref else "right"
                rs.append(r)
            out.append({"reader": rd, "responses": rs})
        return out

    def test_A22_meaning_failure_is_independent_and_not_offset_by_readability_or_preference(self):
        _, org = self.prep(readers="r1")
        resp = self.responses(org, {NAMES[0]: "fail", NAMES[1]: "pass"}, pref=NAMES[0])      # 方式0: 意味保持fail・読みやすさ5・選好される
        res = bl.blind_score(org, resp)
        self.assertEqual(res["meaning_by_candidate"][NAMES[0]]["fail"], 3)
        self.assertEqual(res["meaning_by_candidate"][NAMES[1]]["pass"], 3)
        self.assertFalse(res["eligible"][NAMES[0]])
        self.assertTrue(res["eligible"][NAMES[1]])
        self.assertEqual(res["preference_among_both_pass"], {})                      # 両候補が合格した組がないので選好は空
        self.assertEqual(res["excluded"]["meaning_not_both_pass"], 3)
        self.assertEqual(res["missing_pairs"], 0)

    def test_A22_preference_counts_only_when_both_pass_and_missing_is_reported(self):
        _, org = self.prep(readers="r1")
        resp = self.responses(org, {NAMES[0]: "pass", NAMES[1]: "pass"}, pref=NAMES[1])
        resp[0]["responses"] = resp[0]["responses"][:2]
        res = bl.blind_score(org, resp)
        self.assertEqual(res["preference_among_both_pass"], {NAMES[1]: 2})
        self.assertEqual(res["missing_pairs"], 1)
        with self.assertRaises(CtrError):
            bl.blind_score(org, [{"reader": "reader-001", "responses": [{"pair_id": "pair-001", "meaning": {"left": "good", "right": "pass"}}]}])


ITEMS = [{"id": "c1", "versions": {"v-old": "取りまとめは私です。", "v-new": "論点整理と調整は私が主担当です。承認は部長です。"},
          "questions": [{"qid": "q1", "prompt": "誰が承認しますか", "format": "choice", "choices": ["私", "部長"], "answer_key": "部長", "evidence": "owner 行2"},
                        {"qid": "q2", "prompt": "話し手の担当を自分の言葉で", "format": "free", "answer_key": "論点整理・調整・成果物作成", "evidence": "owner 行1"}]},
         {"id": "c2", "ai_free_delayed": True, "versions": {"v-old": "引渡しは終わりです。", "v-new": "設計書一式を引き渡します。サービスは範囲外です。"},
          "questions": [{"qid": "q1", "prompt": "何を渡しましたか", "format": "free", "answer_key": "設計書一式", "evidence": "architecture 行1"}]}]


class Comprehension(TmpCase):
    def prep(self, readers="a,b,c,d", seed=3):
        out = self.tmp / "comp"
        res = bl.comprehension_prepare(ITEMS, readers.split(","), out, seed)
        return out, read_json(Path(res["organizer_file"]))

    def test_A23_each_reader_gets_one_version_per_item_and_answers_stay_with_organizer(self):
        out, org = self.prep()
        seen = {"c1": set(), "c2": set()}
        for rd, info in org["readers"].items():
            tasks = read_json(out / "readers" / rd / "tasks.json")
            self.assertEqual(len({i["id"] for i in tasks["items"]}), len(tasks["items"]))
            self.assertEqual(len(info["mapping"]), 2)                               # 一人が一課題について持つ版は一つ
            for pub, m in info["mapping"].items():
                seen[m["source_id"]].add(m["version"])
            blob = json.dumps(tasks, ensure_ascii=False)
            for secret in ("v-old", "v-new", "answer_key", "evidence", "owner 行"):
                self.assertNotIn(secret, blob)
        self.assertEqual(seen["c1"], {"v-old", "v-new"})                            # 版が読み手に分散する
        self.assertIn("部長", json.dumps(org["answer_keys"], ensure_ascii=False))     # 正解・根拠は主催者側
        self.assertTrue(bl.check_single_version(out / "readers")["ok"])
        # 配布物を改変して同じ項目を二重に持たせると検出する
        f = out / "readers" / "reader-001" / "tasks.json"
        d = read_json(f)
        d["items"].append(d["items"][0])
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(bl.check_single_version(out / "readers")["ok"])

    def test_A23_other_version_answers_are_excluded_unanswered_stay_in_denominator_and_free_text_needs_human_score(self):
        out, org = self.prep(readers="a,b")
        def ans(rd, item, qid, answer, saw=False):
            pub = next(p for p, m in org["readers"][rd]["mapping"].items() if m["source_id"] == item)
            return {"item": pub, "qid": qid, "answer": answer, "saw_other_version": saw}
        responses = [{"reader": "reader-001", "answers": [ans("reader-001", "c1", "q1", "部長"), ans("reader-001", "c1", "q2", "調整役")]},
                     {"reader": "reader-002", "answers": [ans("reader-002", "c1", "q1", "部長", saw=True)]}]   # 両版を先に読んだ
        scores = []
        res = bl.comprehension_score(org, responses, scores)
        self.assertEqual(res["invalid_excluded_total"], 1)
        rows = {(r["version"], r["format"], r["timing"]): r for r in res["rows"]}
        total_required = sum(r["required"] for r in res["rows"])
        self.assertEqual(total_required, 2 * 3 - 1)                                  # 必須項目(各読み手 q1,q2,c2.q1)。除外1件
        free = [r for r in res["rows"] if r["format"] == "free"]
        self.assertTrue(all(r["matched"] == 0 for r in free))                        # 人の採点がない自由記述を正解にしない
        self.assertGreaterEqual(sum(r["unscored"] for r in free), 1)
        self.assertGreaterEqual(sum(r["unanswered"] for r in res["rows"]), 1)         # 未回答も分母に残る
        self.assertTrue(any(k[2] == "ai_free_delayed" for k in rows))                # AIなしの後日課題は別行
        reader = "reader-001"
        pub = next(p for p, m in org["readers"][reader]["mapping"].items() if m["source_id"] == "c1")
        with self.assertRaises(CtrError):
            bl.comprehension_score(org, responses, [{"reader": reader, "item": pub, "qid": "q2", "match": True}])   # 理由なし
        scored = bl.comprehension_score(org, responses, [{"reader": reader, "item": pub, "qid": "q2", "match": False, "reason": "担当範囲が不足"}])
        self.assertEqual(sum(r["unscored"] for r in scored["rows"] if r["format"] == "free"),
                         sum(r["unscored"] for r in free) - 1)                       # 採点した1件だけ未採点が減る
        self.assertIn("口頭", scored["note"])


if __name__ == "__main__":
    unittest.main()
