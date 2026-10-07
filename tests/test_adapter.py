"""Adapter unit tests: mocked model selection, real SimPy; NOT actual-Qwen evidence."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapter


def mocked_plan(request, mode):
    assert mode == "llm"
    return {"plan_id": "unit-model-mock", "request": request, "mode": "llm", "model": {"name": "UNIT TEST MOCK - not actual Qwen", "revision": "unit"},
            "interpretation": adapter.planner.parse_request(request), "selected_ids": ["training"], "selected_focus_id": "training"}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "jobs.sqlite3"
        self.sent = []
        self.store = adapter.Store(self.path, lambda url, body: self.sent.append((url, body)))

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, key="unit-test-key", records=None, request="직원 검사 교육을 우선 적용"):
        return self.store.submit({"request": request, "records": copy.deepcopy(records if records is not None else self.store.fixture["snapshot"]["records"]),
                                  "synthetic": True, "idempotency_key": key})["id"]

    def ready(self, key="unit-test-key"):
        job = self.submit(key)
        self.assertTrue(self.store.validate({"request_id": job})["valid"])
        with patch.object(adapter.planner, "plan", side_effect=mocked_plan):
            result = self.store.analyze({"request_id": job})
        self.assertTrue(result["ok"])
        self.store.await_review({"request_id": job, "resume_url": "http://127.0.0.1:5679/webhook-waiting/42", "execution_id": "42"})
        return job

    def count(self, job):
        with self.store.db() as db:
            return db.execute("SELECT count(*) FROM training_plans WHERE job_id=?", (job,)).fetchone()[0]

    def test_approve_only_after_durable_browser_decision(self):
        job = self.ready()
        self.assertEqual(self.count(job), 0)
        with self.assertRaises(adapter.ApiError) as caught:
            self.store.finalize({"request_id": job, "decision": "approve"})
        self.assertEqual(caught.exception.status, 409)
        self.store.decision({"request_id": job, "decision": "approve"})
        self.assertEqual(self.count(job), 0)
        approved = self.store.finalize({"request_id": job, "decision": "approve"})
        self.assertEqual(approved["state"], "approved")
        self.assertEqual(self.count(job), 1)
        self.assertEqual(approved["training_plan"]["participants"], 1)
        self.assertEqual(approved["training_plan"]["hours"], 8)
        self.assertNotIn("resume_url", json.dumps(approved))
        self.assertNotIn("records", approved)

    def test_reject_creates_no_plan(self):
        job = self.ready()
        self.store.decision({"request_id": job, "decision": "reject"})
        rejected = self.store.finalize({"request_id": job, "decision": "reject"})
        self.assertEqual(rejected["state"], "rejected")
        self.assertEqual(self.count(job), 0)

    def test_idempotency_no_new_workflow_and_conflict(self):
        job = self.submit()
        self.assertEqual(self.submit(), job)
        self.assertEqual(len(self.sent), 1)
        with self.assertRaises(adapter.ApiError) as caught:
            self.submit(request="현재 공정을 유지")
        self.assertEqual(caught.exception.code, "idempotency_conflict")

    def test_duplicate_decision_finalize_and_conflict(self):
        job = self.ready()
        body = {"request_id": job, "decision": "approve"}
        self.store.decision(body)
        acknowledged_calls = len(self.sent)
        self.store.decision(body)
        self.assertEqual(len(self.sent), acknowledged_calls)
        original = self.store.finalize(body)["training_plan"]
        self.assertEqual(self.store.finalize(body)["training_plan"], original)
        self.store.decision(body)
        self.assertEqual(self.count(job), 1)
        with self.assertRaises(adapter.ApiError):
            self.store.decision({"request_id": job, "decision": "reject"})
        with self.assertRaises(adapter.ApiError):
            self.store.finalize({"request_id": job, "decision": "reject"})

    def test_restart_retains_history_plan_and_decision(self):
        job = self.ready()
        self.store.decision({"request_id": job, "decision": "approve"})
        original = self.store.finalize({"request_id": job, "decision": "approve"})
        restored = adapter.Store(self.path, self.store.sender).public(job)
        self.assertEqual(restored, original)

    def test_invalid_fixture_never_inference(self):
        rows = self.store.fixture["snapshot"]["records"]
        cases = [rows[:-1], rows + [rows[0]], [dict(rows[0], training_hours=8)] + rows[1:], list(reversed(rows))]
        with patch.object(adapter.planner, "plan") as inference:
            for index, records in enumerate(cases):
                job = self.submit(f"invalid-case-{index}", records)
                checked = self.store.validate({"request_id": job})
                self.assertFalse(checked["valid"])
                self.assertEqual(self.store.public(job)["state"], "blocked")
                with self.assertRaises(adapter.ApiError):
                    self.store.analyze({"request_id": job})
            inference.assert_not_called()

    def test_request_constraints_block_before_inference(self):
        job = self.submit(request="https://example.com 공정 교육")
        checked = self.store.validate({"request_id": job})
        self.assertFalse(checked["valid"])
        self.assertIn("request_constraints", [issue["code"] for issue in checked["issues"]])

    def test_resume_url_allowlist_and_execution_match(self):
        values = ["https://127.0.0.1:5679/webhook-waiting/42", "http://example.com/webhook-waiting/42",
                  "http://127.0.0.1:5679/webhook-waiting/42?next=x", "http://user@127.0.0.1:5679/webhook-waiting/42",
                  "http://127.0.0.1:5679/webhook-waiting/42/%2e%2e", "http://127.0.0.1:5679/webhook-waiting/42#x"]
        for value in values:
            with self.assertRaises(adapter.ApiError):
                adapter.check_resume_url(value)
        job = self.ready()
        with self.assertRaises(adapter.ApiError) as caught:
            self.store.await_review({"request_id": job, "resume_url": "http://127.0.0.1:5679/webhook-waiting/43", "execution_id": 42})
        self.assertEqual(caught.exception.code, "execution_mismatch")

    def test_n8n_signed_resume_query_preserved_and_private(self):
        # Deliberately synthetic placeholder; never use an actual runtime token.
        dummy_signature = "a" * 64
        signed_url = "http://127.0.0.1:5679/webhook-waiting/43?signature=" + dummy_signature
        self.assertEqual(adapter.check_resume_url(signed_url), signed_url)
        job = self.submit()
        self.store.validate({"request_id": job})
        with patch.object(adapter.planner, "plan", side_effect=mocked_plan):
            self.store.analyze({"request_id": job})
        self.store.await_review({"request_id": job, "resume_url": signed_url, "execution_id": "43"})
        self.store.decision({"request_id": job, "decision": "approve"})
        self.assertEqual(self.sent[-1][0], signed_url)
        public = json.dumps(self.store.public(job))
        self.assertNotIn(dummy_signature, public)
        self.assertNotIn("resume_url", public)
        with self.assertRaises(adapter.ApiError) as caught:
            self.store.await_review({"request_id": job, "resume_url": signed_url, "execution_id": "44"})
        self.assertEqual(caught.exception.code, "execution_mismatch")

    def test_signed_resume_rejects_other_query_forms(self):
        base = "http://127.0.0.1:5679/webhook-waiting/43"
        dummy = "a" * 64
        bad_queries = ["?token=" + dummy, "?signature=" + dummy + "&next=x",
                       "?signature=" + dummy + "&signature=" + dummy,
                       "?signature=" + "a" * 63, "?signature=" + "a" * 65,
                       "?signature=" + "A" * 64, "?signature=" + "z" * 64,
                       "?%73ignature=" + dummy, "?signature=" + "%61" * 64,
                       "?signature=" + dummy + "/node", "?signature=" + dummy + "#x"]
        for query in bad_queries:
            with self.assertRaises(adapter.ApiError):
                adapter.check_resume_url(base + query)

    def test_forward_failure_is_retained_failed_without_replay(self):
        def fail(url, body):
            raise URLError("unit test network failure")
        self.store.sender = fail
        with self.assertRaises(adapter.ApiError) as caught:
            self.submit()
        self.assertEqual(caught.exception.code, "n8n_forward_failed")
        self.assertEqual(self.store.list_jobs()["items"][0]["state"], "failed")
        self.store.sender = lambda *args: self.fail("idempotency must not retry workflow")
        self.submit()

    def test_pending_resume_failure_can_retry_only_same_decision(self):
        job = self.ready()
        self.store.sender = lambda *args: (_ for _ in ()).throw(URLError("unit test failure"))
        with self.assertRaises(adapter.ApiError):
            self.store.decision({"request_id": job, "decision": "approve"})
        self.assertEqual(self.store.public(job)["state"], "decision_pending")
        self.assertEqual(self.count(job), 0)
        with self.assertRaises(adapter.ApiError):
            self.store.decision({"request_id": job, "decision": "reject"})
        self.store.sender = lambda *args: None
        self.store.decision({"request_id": job, "decision": "approve"})
        self.store.finalize({"request_id": job, "decision": "approve"})
        self.assertEqual(self.count(job), 1)

    def test_analysis_claim_prevents_duplicate_model_work(self):
        job = self.submit()
        self.store.validate({"request_id": job})
        entered, release = threading.Event(), threading.Event()
        def slow(request, mode):
            entered.set()
            self.assertTrue(release.wait(5))
            return mocked_plan(request, mode)
        with patch.object(adapter.planner, "plan", side_effect=slow) as inference:
            thread = threading.Thread(target=lambda: self.store.analyze({"request_id": job}))
            thread.start()
            self.assertTrue(entered.wait(3))
            concurrent = self.store.analyze({"request_id": job})
            self.assertEqual(concurrent["error_code"], "analysis_in_progress")
            # Reads stay responsive while inference owns no SQLite lock.
            self.assertEqual(self.store.public(job)["state"], "analyzing")
            release.set()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertTrue(self.store.analyze({"request_id": job})["ok"])
            self.assertEqual(inference.call_count, 1)

    def test_model_failure_no_fallback_or_fabricated_result(self):
        job = self.submit()
        self.store.validate({"request_id": job})
        with patch.object(adapter.planner, "plan", side_effect=RuntimeError("unit failure")) as inference:
            result = self.store.analyze({"request_id": job})
        self.assertFalse(result["ok"])
        self.assertEqual(inference.call_count, 1)
        self.assertIsNone(self.store.public(job)["result"])

    def test_whitespace_source_change_blocks_before_model(self):
        job = self.submit()
        self.store.validate({"request_id": job})
        source_root = Path(self.temp.name) / "source"
        (source_root / "data").mkdir(parents=True)
        original = (adapter.workforce.ROOT / "data" / "workforce.json").read_bytes()
        (source_root / "data" / "workforce.json").write_bytes(original + b"\n")
        with patch.object(adapter.workforce, "ROOT", source_root), patch.object(adapter.planner, "plan") as inference:
            result = self.store.analyze({"request_id": job})
            inference.assert_not_called()
        self.assertEqual(result["error_code"], "source_changed")
        public = self.store.public(job)
        self.assertEqual(public["state"], "failed")
        self.assertIsNone(public["result"])
        self.assertEqual(self.count(job), 0)

    def test_source_change_during_compare_discards_experiment(self):
        job = self.submit()
        checked = self.store.validate({"request_id": job})
        source_root = Path(self.temp.name) / "source"
        (source_root / "data").mkdir(parents=True)
        original = (adapter.workforce.ROOT / "data" / "workforce.json").read_bytes()
        copied_source = source_root / "data" / "workforce.json"
        copied_source.write_bytes(original)
        real_compare = adapter.engine.compare
        def changed_compare(plan):
            experiment = real_compare(plan)
            copied_source.write_bytes(original + b" ")
            return experiment
        with patch.object(adapter.workforce, "ROOT", source_root), patch.object(adapter.planner, "plan", side_effect=mocked_plan), patch.object(adapter.engine, "compare", side_effect=changed_compare):
            result = self.store.analyze({"request_id": job})
        self.assertEqual(result["error_code"], "source_changed")
        public = self.store.public(job)
        self.assertEqual(public["source_sha256"], checked["source_sha256"])
        self.assertEqual(public["state"], "failed")
        self.assertIsNone(public["result"])
        self.assertEqual(self.count(job), 0)

    def test_simulator_snapshot_hash_must_match_validated_source(self):
        job = self.submit()
        self.store.validate({"request_id": job})
        real_compare = adapter.engine.compare
        def mismatched_compare(plan):
            experiment = real_compare(plan)
            experiment["hr"]["source_json_sha256"] = "0" * 64
            return experiment
        with patch.object(adapter.planner, "plan", side_effect=mocked_plan), patch.object(adapter.engine, "compare", side_effect=mismatched_compare):
            result = self.store.analyze({"request_id": job})
        self.assertEqual(result["error_code"], "source_changed")
        self.assertIsNone(self.store.public(job)["result"])

    def test_approval_without_training_retains_report_only(self):
        job = self.submit(request="현재 공정을 유지")
        self.store.validate({"request_id": job})
        plan = mocked_plan("현재 공정을 유지", "llm")
        plan.update(selected_ids=["baseline"], selected_focus_id="baseline")
        with patch.object(adapter.planner, "plan", return_value=plan):
            self.store.analyze({"request_id": job})
        self.store.await_review({"request_id": job, "resume_url": "http://127.0.0.1:5679/webhook-waiting/42", "execution_id": 42})
        self.store.decision({"request_id": job, "decision": "approve"})
        result = self.store.finalize({"request_id": job, "decision": "approve"})
        self.assertEqual(result["state"], "approved")
        self.assertEqual(self.count(job), 0)
        self.assertIn("no training", result["training_plan_reason"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = adapter.make_server(0, Path(self.temp.name) / "jobs.sqlite3", sender=lambda *args: None)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def fetch(self, path, body=None, headers=None):
        headers = dict(headers or {})
        data = None if body is None else json.dumps(body).encode()
        if data:
            headers.setdefault("Content-Type", "application/json")
        try:
            response = urlopen(Request(self.base + path, data=data, headers=headers), timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_browser_origin_and_workflow_marker(self):
        body = {"request": "검사 교육 적용", "records": self.server.store.fixture["snapshot"]["records"], "synthetic": True, "idempotency_key": "http-test-key"}
        self.assertEqual(self.fetch("/api/submit", body)[0], 403)
        self.assertEqual(self.fetch("/api/submit", body, {"Origin": "https://evil.example"})[0], 403)
        status, submitted = self.fetch("/api/submit", body, {"Origin": self.base})
        self.assertEqual(status, 200)
        request = {"request_id": submitted["id"]}
        self.assertEqual(self.fetch("/api/workflow/validate", request)[0], 403)
        self.assertEqual(self.fetch("/api/workflow/validate", request, {"X-Workflow-Client": adapter.MARKER, "Origin": "https://evil.example"})[0], 403)
        status, validated = self.fetch("/api/workflow/validate", request, {"X-Workflow-Client": adapter.MARKER})
        self.assertEqual(status, 200)
        self.assertTrue(validated["valid"])

    def test_host_path_size_and_unknown_keys(self):
        self.assertEqual(self.fetch("/api/status", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.fetch("/%2e%2e/adapter.py")[0], 400)
        self.assertEqual(self.fetch("/../adapter.py")[0], 400)
        self.assertEqual(self.fetch("/api/submit", {"extra": "x"}, {"Origin": self.base})[0], 400)
        self.assertEqual(self.fetch("/api/submit", {"extra": "x" * 33000}, {"Origin": self.base})[0], 413)

    def test_fixture_and_status_are_synthetic_model_not_loaded(self):
        status, fixture = self.fetch("/api/fixture")
        self.assertEqual(status, 200)
        self.assertTrue(fixture["synthetic"])
        self.assertEqual(len(fixture["records"]), 4)
        status, info = self.fetch("/api/status")
        self.assertEqual(status, 200)
        self.assertFalse(info["workflow_marker_is_production_auth"])
        self.assertFalse(info["model"]["loaded"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"scope": "adapter unit tests; model selection mocked, real SimPy; not actual-Qwen E2E", "tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful(),
              "actual_model_loaded": adapter.planner.status()["loaded"], "external_contacts": False}
    (Path(__file__).parent / "test-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(not result.wasSuccessful())
