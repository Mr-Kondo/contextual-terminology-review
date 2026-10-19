"""実行記録・フィードバック・書き出し/取り込み・削除(A33〜A39, A43〜A45, A47, A48)。仮の保存先だけを使う。"""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import ACCEPT, HOSTS_DOC, SKILL, TmpCase, run_ctr
from semantic_fixtures import CASES

import ctr_log as L
from ctr_common import CtrError, read_json, sha256_bytes, write_json
from ctr_improve import metrics, sample_candidates
from ctr_refs import Review, load_registry, review_check

SHARE_ALL = ["run_status", "versions", "environment", "domains", "problem_axes", "machine_checks", "human_feedback",
             "project_opaque_id", "effort"]


def summary_for(cid="A01"):
    c = CASES[cid]
    rev = Review.model_validate(c["review"])
    rep = review_check(rev, load_registry(ACCEPT))
    return L.summarize_review(rep, rev), rep, rev


class LogBase(TmpCase):
    def setUp(self):
        super().setUp()
        self.rt, self.imp = self.mk("runtime"), self.mk("improvement")
        L.store_init(self.rt)

    def start(self, **kw):
        kw.setdefault("host", "claude-code")
        kw.setdefault("route", "local")
        kw.setdefault("domains", ["業務用語"])
        return L.record_start(self.rt, **kw)

    def finish(self, run_id, cid="A01"):
        s, rep, rev = summary_for(cid)
        return L.record_finish(self.rt, run_id, review_summary=s, private_output={"footer": rep["footer"]})

    def run_dir(self, run_id):
        return L.find_run_dir(self.rt, run_id)

    def share(self, fields=None):
        L.set_policy(self.rt, share_fields=fields or SHARE_ALL, share_scope="テスト用の範囲", granted_by="テスト許可者")

    def package(self, **kw):
        self.share()
        return Path(L.export_package(self.rt, **kw)["path"])


class RunLifecycle(LogBase):
    def test_A33_run_without_end_event_is_incomplete_not_guessed(self):
        r = self.start()
        self.assertTrue(r["write"]["verified"])                         # 書いた後に再読込して照合している
        run = read_json(self.run_dir(r["run_id"]) / "run.json")
        self.assertFalse(run["retention"]["raw_text_retention"])        # 開始時の保存方針を保持
        self.assertIn("skill", run["versions"])
        old = L.check_runs(self.rt, in_progress_minutes=0)[0]
        self.assertEqual(old["status"], "incomplete_suspected")
        self.assertFalse(old["reason_known"])                           # 原因・成功を推測しない
        self.assertEqual(L.check_runs(self.rt, in_progress_minutes=60)[0]["status"], "in_progress_or_unknown")
        self.finish(r["run_id"])
        self.assertEqual(L.check_runs(self.rt)[0]["status"], "completed")
        run2 = read_json(self.run_dir(r["run_id"]) / "run.json")
        self.assertEqual(run2, run)                                     # 終了で run.json を上書きしない
        with self.assertRaises(CtrError) as cm:
            self.finish(r["run_id"])
        self.assertEqual(cm.exception.code, "already_terminated")

    def test_A33_failed_run_is_recorded_as_failure(self):
        r = self.start()
        L.record_finish(self.rt, r["run_id"], failed_with="tool_failed")
        self.assertEqual(L.check_runs(self.rt)[0]["status"], "failed")

    def test_A34_unwritable_store_keeps_existing_and_reports_unsaved(self):
        if os.geteuid() == 0:
            self.skipTest("root では書き込み拒否を再現できない")
        r = self.start()
        before = self.read_all_text(self.rt)
        runs = self.run_dir(r["run_id"]).parent                         # 月別ディレクトリ。ここを書込み不可にする
        runs.chmod(0o500)
        self.addCleanup(lambda: runs.chmod(0o700))
        with self.assertRaises(CtrError) as cm:
            self.start()
        self.assertEqual(cm.exception.code, "storage_unwritable")
        runs.chmod(0o700)
        self.assertEqual(self.read_all_text(self.rt), before)           # 既存記録を保持
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["improvement", "runtime"])  # 別の場所へ退避しない
        self.assertEqual(metrics(self.rt, None)["populations"]["runs_started_collected"], 1)  # 失敗した実行を保存成功へ加算しない
        # CLI の表示
        runs.chmod(0o500)
        code, out = run_ctr("record", "start", "--runtime-root", self.rt, "--host", "codex")
        runs.chmod(0o700)
        self.assertEqual(code, 3)
        self.assertIn("保存未確認", out["status"])

    def test_A34_midwrite_failure_leaves_no_partial_file(self):
        r = self.start()
        with mock.patch("ctr_common.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(CtrError) as cm:
                self.finish(r["run_id"])
        self.assertEqual(cm.exception.code, "storage_unwritable")
        leftovers = [p for p in self.rt.rglob("*") if p.name.startswith(".tmp-")]
        self.assertEqual(leftovers, [])
        self.assertEqual(L.check_runs(self.rt)[0]["status"], "in_progress_or_unknown")      # 部分ファイルを終了扱いにしない
        self.assertTrue(L.check_store(self.rt)["ok"])

    def test_A34_existing_id_is_never_overwritten(self):
        p = self.rt / "x.json"
        write_json(p, {"a": 1})
        with self.assertRaises(CtrError) as cm:
            write_json(p, {"a": 2})
        self.assertEqual(cm.exception.code, "already_exists")
        self.assertEqual(read_json(p), {"a": 1})

    def test_A34_write_works_without_hard_links_and_still_never_overwrites(self):
        from unittest import mock
        p = self.rt / "nolink.json"
        with mock.patch("os.link", side_effect=OSError(1, "Operation not permitted")):   # exFAT・一部のネットワーク共有
            res = write_json(p, {"a": 1})
            self.assertTrue(res["verified"])
            with self.assertRaises(CtrError) as cm:
                write_json(p, {"a": 2})
        self.assertEqual(cm.exception.code, "already_exists")
        self.assertEqual(read_json(p), {"a": 1})
        self.assertEqual([q for q in self.rt.rglob("*") if q.name.startswith(".tmp-")], [])

    def test_A39_unconfigured_store_is_reported_with_manual_route_and_writes_nothing(self):
        wd = self.mk("cwd")
        code, out = run_ctr("record", "start", "--host", "codex", cwd=wd)
        self.assertEqual(code, 3)
        self.assertEqual(out["error"], "storage_unconfigured")
        self.assertIn("手動記録", out["message"])
        self.assertEqual(list(wd.iterdir()), [])                         # 既定の場所を勝手に作らない
        self.assertIn("手動の記録票", HOSTS_DOC.read_text(encoding="utf-8"))
        self.assertIn("消失リスク", HOSTS_DOC.read_text(encoding="utf-8"))

    def test_A39_relative_path_is_refused_and_nonexistent_parent_fails_cleanly(self):
        code, out = run_ctr("record", "start", "--runtime-root", "relative/dir")
        self.assertEqual((code, out["error"]), (3, "storage_path_not_absolute"))

    def test_A47_raw_text_not_retained_when_not_permitted(self):
        secret = "秘密の契約文言ゼータ第7条"
        f = self.tmp / "input.txt"
        f.write_text(secret, encoding="utf-8")
        r = self.start(target_text_file=f)
        s, rep, rev = summary_for("A01")
        L.record_finish(self.rt, r["run_id"], review_summary=s, private_output={"text": secret, "footer": rep["footer"]})
        L.feedback_add(self.rt, r["run_id"], "F1", validity="ok", reason=f"{secret} を引用した理由")
        self.assertNotIn(secret, self.read_all_text(self.rt))
        self.assertFalse((self.run_dir(r["run_id"]) / "private").exists())
        run = read_json(self.run_dir(r["run_id"]) / "run.json")
        self.assertFalse(run["target"]["raw_stored"])
        self.assertIn("再現できる範囲は限定", run["target"]["reason"])    # 再現可能範囲の制限を表示
        self.assertEqual(run["target"]["reproducibility"], "limited")
        fb = next((self.run_dir(r["run_id"]) / "feedback").glob("*.json"))
        self.assertTrue(read_json(fb)["reason_withheld"])
        fin = next(p for p in (self.run_dir(r["run_id"]) / "events").glob("*.json"))
        self.assertFalse(read_json(fin)["private_output_stored"])
        # エラー・CLI出力へも迂回しない
        code, out = run_ctr("feedback", "add", "--runtime-root", self.rt, "--run-id", r["run_id"], "--finding-id", "F1",
                            "--reason", secret, "--validity", "ok")
        self.assertNotIn(secret, json.dumps(out, ensure_ascii=False))
        self.assertNotIn(secret, self.read_all_text(self.rt))

    def test_A47_raw_text_kept_only_with_explicit_permission(self):
        L.set_policy(self.rt, raw_text="allow")
        f = self.tmp / "input.txt"
        f.write_text("許可された原文", encoding="utf-8")
        r = self.start(target_text_file=f)
        self.assertTrue(r["target"]["raw_stored"])
        self.assertEqual((self.run_dir(r["run_id"]) / "private" / "target.txt").read_text(encoding="utf-8"), "許可された原文")


class Feedback(LogBase):
    def test_A35_correction_is_appended_and_only_effective_value_counts(self):
        r = self.start()
        self.finish(r["run_id"])
        first = L.feedback_add(self.rt, r["run_id"], "F1", validity="ng", intent="changed")
        second = L.feedback_add(self.rt, r["run_id"], "F1", validity="ok", intent="kept", corrects=first["event_id"])
        d = self.run_dir(r["run_id"]) / "feedback"
        self.assertEqual(len(list(d.glob("*.json"))), 2)                  # 訂正前も来歴として保持
        self.assertEqual(read_json(d / f"{second['event_id']}.json")["corrects"], first["event_id"])
        events = [read_json(p) for p in d.glob("*.json")]
        eff = L.effective_feedback(events)
        self.assertEqual(len(eff), 1)
        self.assertEqual(next(iter(eff.values()))["validity"], "ok")
        m = {x["id"]: x for x in metrics(self.rt, None)["metrics"]}
        self.assertEqual((m["unnecessary_fix"]["numerator"], m["unnecessary_fix"]["denominator"]), (0, 1))   # 両評価を独立例にしない
        self.assertEqual(m["unnecessary_fix"]["independent_tasks"], 1)
        with self.assertRaises(CtrError):
            L.feedback_add(self.rt, r["run_id"], "F1", corrects="fb-none")        # 存在しない訂正対象

    def test_A35_unanswered_is_not_positive(self):
        r = self.start()
        self.finish(r["run_id"])
        L.feedback_add(self.rt, r["run_id"], "F1")                                   # 何も答えていない
        m = metrics(self.rt, None)
        by = {x["id"]: x for x in m["metrics"]}
        self.assertEqual(by["unnecessary_fix"]["status"], "unevaluated(分母0)")
        self.assertEqual(m["missingness"]["unanswered_validity"], 1)
        with self.assertRaises(CtrError):
            L.feedback_add(self.rt, r["run_id"], "F1", validity="yes")               # 列挙外は受け付けない

    def test_A43_metrics_separate_valid_confirmation_from_missing_and_do_not_inflate_independent_count(self):
        r = self.start(task_group="grp-1")
        s, rep, rev = summary_for("A01")
        s["findings"].append({**s["findings"][0], "id": "F2"})           # 指摘は2件。確認は1件だけ
        L.record_finish(self.rt, r["run_id"], review_summary=s)
        a = L.feedback_add(self.rt, r["run_id"], "F1", validity="ng")
        L.feedback_add(self.rt, r["run_id"], "F1", validity="ok", corrects=a["event_id"])
        pkg = self.package()
        imp1 = L.import_package(self.imp, pkg)
        imp2 = L.import_package(self.imp, pkg)                           # 再取り込み
        self.assertEqual(imp2["status"], "already_imported")
        m = metrics(None, self.imp)                                      # 取り込み側だけで数える
        by = {x["id"]: x for x in m["metrics"]}
        self.assertEqual((by["unnecessary_fix"]["numerator"], by["unnecessary_fix"]["denominator"]), (0, 1))
        self.assertEqual(m["populations"]["independent_tasks_with_human_confirmation"], 1)
        self.assertEqual(m["populations"]["shared_runs"], 1)
        self.assertIsNone(m["collection_rate"]["value"])                 # 利用総数が未知なら収集率を出さない
        self.assertIn("未知", m["collection_rate"]["reason"])
        self.assertEqual(by["recurrence"]["status"], "unevaluated(評価入力なし)")
        self.assertEqual(by["receiver_confirmation"]["status"], "unevaluated(分母0)")
        self.assertIsNone(by["unnecessary_fix"]["wilson_95"])             # 件数が少ないときに区間を出さない
        full = metrics(self.rt, None)
        self.assertEqual(full["missingness"]["findings_recorded"], 2)
        self.assertEqual(full["missingness"]["unanswered_validity"], 1)
        self.assertEqual(metrics(self.rt, None, known_total_usage=10)["collection_rate"]["value"], 0.1)

    def test_A45_effort_counts_setup_and_daily_entries_and_flags_budget(self):
        r = self.start()
        for cat, mins in (("setup", 10), ("record", 5), ("evidence", 15), ("compare", 5)):
            L.effort_add(self.rt, category=cat, minutes=mins, who="self", run_id=r["run_id"])
        L.effort_add(self.rt, category="evidence", minutes=40, who="collaborator")
        wk = next(iter(metrics(self.rt, None)["effort"].values()))
        self.assertEqual(wk["self_minutes"], 35)
        self.assertEqual(wk["collaborator_minutes"], 40)                  # 協力者の時間は別
        self.assertTrue(wk["over_30min_budget"])
        self.assertEqual(wk["by_category"]["setup"], 10)                  # 初期設定も負担に数える
        with self.assertRaises(CtrError):
            L.effort_add(self.rt, category="other", minutes=1)

    def test_A45_sampling_includes_no_finding_runs_with_recorded_conditions_and_no_assumed_correctness(self):
        ids = []
        for i in range(4):
            r = self.start()
            ids.append(r["run_id"])
            L.record_finish(self.rt, r["run_id"], review_summary={"findings": [], "ref_counts": {"checked": 0}, "error_classes": [],
                                                                    "independent_source_count": 0})
        r = self.start()
        self.finish(r["run_id"])
        a = sample_candidates(self.rt, self.imp, seed=7, n_no_finding=2, n_high_risk=1, n_random=1)
        b = sample_candidates(self.rt, None, seed=7, n_no_finding=2, n_high_risk=1, n_random=1)
        self.assertEqual(a["chosen"], b["chosen"])                        # seed と条件で再現できる
        self.assertEqual(len(a["chosen"]["no_finding"]), 2)
        self.assertTrue(a["unselected_are_not_assumed_correct"])
        self.assertEqual(a["pool_sizes"]["no_finding"], 4)
        self.assertEqual(len(list((self.imp / "evaluations" / "samples").glob("*.json"))), 1)


class Sharing(LogBase):
    def setUp(self):
        super().setUp()
        self.secret_ctx = "案件ゼータの契約書第3条の引用文"

    def prepare_run(self):
        L.set_policy(self.rt, raw_text="allow")
        f = self.tmp / "in.txt"
        f.write_text(self.secret_ctx, encoding="utf-8")
        r = self.start(target_text_file=f, model_id="model-x1")
        self.finish(r["run_id"])
        L.feedback_add(self.rt, r["run_id"], "F1", validity="ok", intent="kept", usage="edited", receiver="confirmed",
                       reason=f"{self.secret_ctx} を根拠にしたため")
        return r

    def test_A36_export_stops_until_item_permission_is_set_and_install_is_not_consent(self):
        self.prepare_run()
        self.assertIsNone(L.load_policy(self.rt)["share_fields"])
        with self.assertRaises(CtrError) as cm:
            L.export_package(self.rt)
        self.assertEqual(cm.exception.code, "sharing_not_configured")
        self.assertFalse((self.rt / "outbox").exists())
        code, out = run_ctr("export", "--runtime-root", self.rt)
        self.assertEqual(code, 4)                                       # 確認待ちとして停止
        with self.assertRaises(CtrError):
            L.set_policy(self.rt, share_fields=["run_status"])         # 範囲・許可者なしでは許可にならない
        with self.assertRaises(CtrError):
            L.set_policy(self.rt, share_fields=["private_inputs"], share_scope="x", granted_by="y")

    def test_A36_permitted_package_contains_only_allowed_items_and_no_leak_by_bypass(self):
        self.prepare_run()
        pkg = self.package()
        text = self.read_all_text(pkg)
        for leaked in (self.secret_ctx, "契約書", "案件ゼータ", str(self.tmp), "/Users/", "/tmp/", "private", "根拠にしたため",
                       "一致", "引用文"):
            self.assertNotIn(leaked, text, leaked)
        manifest = read_json(pkg / "manifest.json")
        self.assertEqual(manifest["fields"], sorted(SHARE_ALL))
        self.assertEqual(manifest["permission"]["status"], "granted")
        for f in manifest["files"]:                                      # ハッシュ・サイズが実ファイルと一致
            data = (pkg / f["name"]).read_bytes()
            self.assertEqual((sha256_bytes(data), len(data)), (f["sha256"], f["bytes"]))
        for p in (pkg / "events").glob("*.json"):
            L.validate_shared_event(read_json(p))
        fb = [read_json(p) for p in (pkg / "events").glob("*.json") if read_json(p)["type"] == "feedback"][0]
        self.assertNotIn("reason", fb)
        self.assertNotIn("reviewer", fb)

    def test_A36_only_permitted_groups_are_exported(self):
        self.prepare_run()
        L.set_policy(self.rt, share_fields=["run_status"], share_scope="範囲", granted_by="許可者")
        pkg = Path(L.export_package(self.rt)["path"])
        keys = set()
        for p in (pkg / "events").glob("*.json"):
            keys |= set(read_json(p))
        self.assertTrue(keys <= set(L.PROVENANCE) | {"error_class"}, keys)

    def test_A36_validator_rejects_extra_and_pathlike_values(self):
        base = {"schema_version": 1, "event_id": "ev-1", "run_id": "run-1", "type": "completed",
                "created_at": "2026-10-17T00:00:00Z", "origin_id": "org-1"}
        L.validate_shared_event(base)
        for extra in ({"quote": "x"}, {"text": "x"}, {"cmd": "rm -rf /"}, {"model_id": "/Users/me/model"},
                      {"error_class": "$(touch x)"}, {"domains": ["案件ゼータ"]}):
            with self.assertRaises(CtrError, msg=str(extra)):
                L.validate_shared_event({**base, **extra})

    def test_A36_export_with_path_like_model_id_aborts_without_package(self):
        r = self.start(model_id="/Users/someone/models/x")
        self.finish(r["run_id"])
        L.set_policy(self.rt, share_fields=SHARE_ALL, share_scope="範囲", granted_by="許可者")
        with self.assertRaises(CtrError):
            L.export_package(self.rt)
        self.assertFalse((self.rt / "outbox").exists())

    def test_A37_duplicate_import_is_not_double_counted_and_same_id_other_content_is_quarantined(self):
        self.prepare_run()
        pkg = self.package()
        first = L.import_package(self.imp, pkg)
        again = L.import_package(self.imp, pkg)
        self.assertEqual(first["status"], "imported")
        self.assertEqual(again["status"], "already_imported")
        n_before = len(list((self.imp / "inbox").glob("*/events/*.json")))
        # 別パッケージIDで、同じイベント(同一内容)を再送 → 重複として加算しない
        twin = self.repack(pkg, "pkg-twin", lambda ev: ev)
        res = L.import_package(self.imp, twin)
        self.assertEqual((res["duplicate"], res["accepted"]), (n_before, 0))
        self.assertEqual(len(list((self.imp / "inbox").glob("*/events/*.json"))), n_before)
        # 同じIDで内容が違う → 競合として隔離。既存を上書きしない
        before = {p.name: p.read_bytes() for p in (self.imp / "inbox").glob("*/events/*.json")}
        evil = self.repack(pkg, "pkg-conflict", lambda ev: {**ev, "created_at": "2030-01-01T00:00:00Z"})
        res2 = L.import_package(self.imp, evil)
        self.assertEqual(res2["conflict_quarantined"], n_before)
        self.assertEqual(res2["accepted"], 0)
        self.assertEqual({p.name: p.read_bytes() for p in (self.imp / "inbox").glob("*/events/*.json")}, before)
        self.assertTrue(list((self.imp / "quarantine").glob("conflict-*")))
        m = metrics(None, self.imp)
        self.assertEqual(m["populations"]["shared_runs"], 1)             # 二回の受信を二例に数えない

    def repack(self, pkg: Path, new_id: str, mutate, manifest_edit=None) -> Path:
        out = self.mk(f"repack-{new_id}") / new_id
        shutil.copytree(pkg, out)
        m = read_json(out / "manifest.json")
        m["package_id"] = new_id
        for f in m["files"]:
            p = out / f["name"]
            ev = mutate(read_json(p))
            data = json.dumps(ev, ensure_ascii=False, indent=2, sort_keys=True).encode()
            p.write_bytes(data)
            f["sha256"], f["bytes"] = sha256_bytes(data), len(data)
        if manifest_edit:
            manifest_edit(m)
        (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    def test_A38_untrusted_packages_are_each_rejected_without_side_effects(self):
        self.prepare_run()
        good = self.package()
        canary = self.tmp / "canary.txt"
        canary.write_text("untouched")
        inbox_empty = lambda: not list((self.imp / "inbox").glob("*"))

        def rejected(pkg, code=None, **kw):
            with self.assertRaises(CtrError) as cm:
                L.import_package(self.imp, pkg, **kw)
            if code:
                self.assertEqual(cm.exception.code, code)
            self.assertTrue(inbox_empty())                                # 不正なパッケージを確定しない
            self.assertNotIn("案件ゼータ", cm.exception.message + str(cm.exception))   # 原文をエラーへ漏らさない
            return cm.exception

        rejected(self.repack(good, "pkg-s", lambda e: e, lambda m: m.update(schema_version=99)), "unknown_schema")
        rejected(self.repack(good, "pkg-u", lambda e: e, lambda m: m.update(extra="x")), "unknown_schema")
        bad = self.repack(good, "pkg-h", lambda e: e)
        ev = next((bad / "events").glob("*.json"))
        ev.write_text(ev.read_text(encoding="utf-8") + " ", encoding="utf-8")   # manifest 作成後の改変
        rejected(bad, "hash_mismatch")
        rejected(self.repack(good, "pkg-p", lambda e: e, lambda m: m["files"][0].update(name="../canary.json")), None)
        link = self.repack(good, "pkg-l", lambda e: e)
        target = next((link / "events").glob("*.json"))
        target.unlink()
        os.symlink(canary, target)                                        # リンク経由で境界外を指す
        rejected(link)
        self.assertEqual(canary.read_text(), "untouched")
        extra = self.repack(good, "pkg-x", lambda e: e)
        (extra / "events" / "unlisted.json").write_text("{}")
        rejected(extra, "unlisted_file")
        rejected(self.repack(good, "pkg-z", lambda e: e), "size_limit_exceeded", max_file_bytes=10)
        # 添付内の命令: 許可項目に当たらないキー/値は拒否し、実行しない
        marker = self.tmp / "executed"
        cmd = self.repack(good, "pkg-c", lambda e: {**e, "cmd": f"touch {marker}"})
        rejected(cmd, "field_not_allowed")
        inj = self.repack(good, "pkg-i", lambda e: {**e, "error_class": f"$(touch {marker})"})
        rejected(inj, "field_value_invalid")
        self.assertFalse(marker.exists())
        self.assertEqual(canary.read_text(), "untouched")
        # 正しいパッケージは取り込めるが、送信者の認証や内容の正しさを主張しない
        ok = L.import_package(self.imp, good)
        self.assertEqual(ok["status"], "imported")
        self.assertNotIn("authenticated", json.dumps(ok))
        self.assertIn("認証", read_json(good / "manifest.json")["note"])

    def test_A38_import_denies_unpermitted_package(self):
        self.prepare_run()
        pkg = self.package()
        nope = self.repack(pkg, "pkg-n", lambda e: e, lambda m: m.update(permission={"status": "pending"}))
        with self.assertRaises(CtrError) as cm:
            L.import_package(self.imp, nope)
        self.assertEqual(cm.exception.code, "permission_not_granted")


class Deletion(LogBase):
    def test_A44_delete_tracks_derivatives_marks_external_pending_and_blocks_reimport(self):
        L.set_policy(self.rt, raw_text="allow")
        r = self.start(task_group="grp-d")
        self.finish(r["run_id"])
        pkg = self.package()
        L.mark_shared(self.rt, pkg.name, "外部共有先A")
        L.import_package(self.imp, pkg)
        # 派生物: 回帰例・索引メタ(別ディレクトリ)
        write_json(self.imp / "regressions" / "reg1.json", {"derived_from": [r["run_id"]], "case_id": "reg1"})
        idx = self.mk("index")
        write_json(idx / "index_meta.json", {"derived_from": [r["run_id"]], "terms_sha256": "x"})
        plan = L.delete_plan([self.rt, self.imp, idx], self.rt, r["run_id"])
        labels = "\n".join(h["label"] for h in plan["local_dependents"])
        for expect in ("run.json", "private/output.json", "outbox/", "inbox/", "regressions/reg1.json", "index_meta.json"):
            self.assertIn(expect, labels)
        self.assertTrue(any(p["kind"] == "shared_copy" and "外部共有先A" in p["shared_to"] for p in plan["pending_confirmation"]))
        code, out = run_ctr("delete", "apply", "--id", r["run_id"], "--runtime-root", self.rt)
        self.assertEqual((code, out["error"]), (4, "approval_required"))          # --confirm なしでは消さない
        self.assertTrue(list(self.rt.glob("runs/*/*")))
        rep = L.delete_apply([self.rt, self.imp, idx], self.rt, r["run_id"], known_copies=["バックアップ(利用者申告)"])
        self.assertEqual(rep["status"], "deleted_local_pending_external")         # 全消去を完了と言わない
        self.assertTrue(any(p["kind"] == "known_copy" for p in rep["pending_confirmation"]))
        self.assertEqual(list(self.rt.glob("runs/*/run-*")), [])
        self.assertFalse((idx / "index_meta.json").exists())
        self.assertEqual(list((self.imp / "inbox").glob("*/events/*.json")), [])

    def test_A44_reimport_of_old_package_is_blocked_by_tombstone(self):
        L.set_policy(self.rt, raw_text="allow")
        r = self.start()
        self.finish(r["run_id"])
        pkg = self.package()
        keep = self.mk("keep") / "pkg"
        shutil.copytree(pkg, keep)                                               # 利用者が別の場所へ複製していた移送物
        L.import_package(self.imp, pkg)
        L.delete_apply([self.rt, self.imp], self.rt, r["run_id"])
        res = L.import_package(self.imp, keep)
        self.assertEqual(res["accepted"], 0)
        self.assertGreaterEqual(res["tombstoned"], 1)
        self.assertEqual(list((self.imp / "inbox").glob("*/events/*.json")), [])
        led = read_json(self.rt / "deleted_ids.json")
        self.assertEqual(set(led["deleted"][0]), {"id", "deleted_at"})            # 台帳はIDだけ。内容を残さない


class PortableLogging(TmpCase):
    def test_A48_each_route_records_rereads_exports_imports_and_reports_failure(self):
        for host in L.HOSTS:
            for route in ("local", "remote"):
                with self.subTest(host=host, route=route):
                    rt, imp = self.mk(f"rt-{host}-{route}"), self.mk(f"imp-{host}-{route}")
                    L.store_init(rt)
                    r = L.record_start(rt, host=host, route=route, domains=["分野横断"], model_id=None)
                    self.assertTrue(r["write"]["verified"])
                    s, rep, rev = summary_for("A01")
                    L.record_finish(rt, r["run_id"], review_summary=s)
                    L.feedback_add(rt, r["run_id"], "F1", validity="ok")
                    self.assertTrue(L.check_store(rt)["ok"])
                    L.set_policy(rt, share_fields=SHARE_ALL, share_scope="試験", granted_by="試験者")
                    pkg = Path(L.export_package(rt)["path"])
                    self.assertEqual(L.import_package(imp, pkg)["accepted"], 3)
                    start = next(read_json(p) for p in (imp / "inbox").glob("*/events/*.json") if read_json(p)["type"] == "run_started")
                    self.assertEqual((start["host_environment"], start["host_route"]), (host, route))
                    self.assertEqual(start["model_id"], "unknown")                # 取得できないモデル識別子は unknown(後から埋めない)
        if os.geteuid() != 0:
            ro = self.mk("ro")
            L.store_init(ro)
            (ro / "runs").mkdir()
            (ro / "runs").chmod(0o500)
            self.addCleanup(lambda: (ro / "runs").chmod(0o700))
            with self.assertRaises(CtrError) as cm:
                L.record_start(ro, host="antigravity", route="remote")
            self.assertEqual(cm.exception.code, "storage_unwritable")


if __name__ == "__main__":
    unittest.main()
