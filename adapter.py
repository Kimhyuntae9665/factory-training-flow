"""Loopback-only synthetic n8n adapter. The client marker is not production auth."""
import argparse
import contextlib
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "simulator"))
import engine
import planner
import workforce

MARKER = "factory-training-local-v1"
WEBHOOK = "http://127.0.0.1:5679/webhook/factory-training"
MODEL_LOCK = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class SourceChanged(Exception):
    """The simulator source no longer matches the validated byte snapshot."""


def require_source_hash(expected):
    try:
        digest = hashlib.sha256((workforce.ROOT / "data" / "workforce.json").read_bytes()).hexdigest()
    except OSError as exc:
        raise SourceChanged() from exc
    if digest != expected:
        raise SourceChanged()


def schema(body, fields):
    if not isinstance(body, dict) or set(body) != set(fields):
        raise ApiError(400, "schema", "JSON fields do not match the endpoint schema.")


def request_id(body):
    if not isinstance(body.get("request_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", body["request_id"]):
        raise ApiError(400, "request_id", "Invalid request ID.")
    return body["request_id"]


def check_resume_url(value):
    # n8n 2.42.3 appends WAITING_TOKEN_QUERY_PARAM='signature'; generateSecureToken
    # is exactly 32 random bytes encoded as 64 lowercase hex characters. Preserve
    # it for n8n's own constant-time validation; never expose it in public data.
    # Reject arbitrary queries, duplicate params, encoding, fragments and userinfo.
    if not isinstance(value, str) or not re.fullmatch(r"http://127\.0\.0\.1:5679/webhook-waiting/[0-9]+(?:/[A-Za-z0-9_-]+)?(?:\?signature=[0-9a-f]{64})?", value):
        raise ApiError(400, "resume_url", "Resume URL is outside the fixed local n8n runtime.")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_json(url, value):
    # URLs are checked by the caller. Redirects cannot escape the allowlist.
    data = encode(value).encode("utf-8")
    with build_opener(ProxyHandler({}), NoRedirect()).open(Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST"), timeout=12) as response:
        response.read(32768)
        if not 200 <= response.status < 300:
            raise URLError("Local n8n request failed")


def summarize(result):
    before = next(s for s in result["scenarios"] if s["id"] == "baseline")
    after = next(s for s in result["scenarios"] if s["id"] == result["recommendation"]["scenario_id"])
    keys = ("completed", "mean_wait_min", "wip_end", "skill_coverage_pct")
    return {"selected_focus_id": result["plan"]["selected_focus_id"], "recommended_scenario_id": after["id"],
            "before": before["metrics"], "after": after["metrics"],
            "delta": {key: round(after["metrics"][key] - before["metrics"][key], 4) for key in keys},
            "training_required": after["config"]["training"],
            "explanation": f"계산된 10개 seed 평균 완료 수 {before['metrics']['completed']} → {after['metrics']['completed']}, "
                           f"검사 자격 커버리지 {before['metrics']['skill_coverage_pct']}% → {after['metrics']['skill_coverage_pct']}%. "
                           "이 설명은 SimPy 계산값으로 작성한 정형 요약이며 LLM 자유 생성 문장이 아닙니다."}


class Store:
    def __init__(self, path, sender=post_json):
        self.path, self.sender = str(path), sender
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.fixture = workforce.load()
        self.webhook = os.environ.get("FACTORY_N8N_WEBHOOK_URL", WEBHOOK)
        if self.webhook != WEBHOOK:
            raise ValueError("Only the fixed loopback n8n webhook is allowed")
        self.decision_lock = threading.Lock()
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
              state TEXT NOT NULL, result TEXT, resume_url TEXT, decision TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, issues TEXT,
              source_sha256 TEXT, error_code TEXT, n8n_execution_id TEXT);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
              stage TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS training_plans (
              id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, content TEXT NOT NULL);
            """)
            # Interrupted inference cannot be claimed as a completed experiment.
            rows = db.execute("SELECT id FROM jobs WHERE state='analyzing'").fetchall()
            for row in rows:
                self.change(db, row["id"], "failed", error_code="interrupted_analysis")

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def find(self, db, job_id):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ApiError(404, "not_found", "Request was not found.")
        return row

    def event(self, db, job_id, stage, detail):
        db.execute("INSERT INTO events(job_id,stage,detail,created_at) VALUES(?,?,?,?)", (job_id, stage, encode(detail), now()))

    def change(self, db, job_id, state, **fields):
        fields.update(state=state, updated_at=now())
        db.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?", (*fields.values(), job_id))
        self.event(db, job_id, state, {key: value for key, value in fields.items() if key not in {"result", "resume_url", "updated_at"}})

    def public(self, job_id):
        with self.db() as db:
            row = self.find(db, job_id)
            result = json.loads(row["result"]) if row["result"] else None
            plan = db.execute("SELECT content FROM training_plans WHERE job_id=?", (job_id,)).fetchone()
            events = [{"stage": e["stage"], "detail": json.loads(e["detail"]), "created_at": e["created_at"]}
                      for e in db.execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,))]
            return {"id": row["id"], "request_id": row["id"], "request": json.loads(row["payload"])["request"],
                    "state": row["state"], "status": row["state"], "synthetic": True,
                    "result": result, "summary": summarize(result) if result else None,
                    "experiment_id": result["experiment_id"] if result else None,
                    "training_plan": json.loads(plan["content"]) if plan else None,
                    "training_plan_reason": "Recommendation contains no training; only the approved report is retained." if result and row["state"] == "approved" and not summarize(result)["training_required"] else None,
                    "decision": row["decision"], "issues": json.loads(row["issues"]) if row["issues"] else [],
                    "source_sha256": row["source_sha256"], "error_code": row["error_code"],
                    "n8n_execution_id": row["n8n_execution_id"], "created_at": row["created_at"], "events": events}

    def list_jobs(self):
        with self.db() as db:
            ids = [row["id"] for row in db.execute("SELECT id FROM jobs ORDER BY created_at DESC LIMIT 100")]
        return {"items": [self.public(job_id) for job_id in ids]}

    def submit(self, body):
        schema(body, {"request", "records", "synthetic", "idempotency_key"})
        if body["synthetic"] is not True or not isinstance(body["request"], str) or not isinstance(body["records"], list):
            raise ApiError(400, "schema", "Only explicitly synthetic JSON list input is accepted.")
        if len(body["request"]) > 600 or len(body["records"]) > 12:
            raise ApiError(400, "size", "Fixture/request bound exceeded.")
        if not isinstance(body["idempotency_key"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", body["idempotency_key"]):
            raise ApiError(400, "idempotency_key", "Key must contain 8–100 letters, numbers, underscores or hyphens.")
        payload = encode({key: body[key] for key in ("request", "records", "synthetic")})
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT id,payload FROM jobs WHERE key=?", (body["idempotency_key"],)).fetchone()
            if old:
                if old["payload"] != payload:
                    raise ApiError(409, "idempotency_conflict", "An existing key has different immutable input.")
                job_id, fresh = old["id"], False
            else:
                job_id, fresh = uuid.uuid4().hex, True
                db.execute("INSERT INTO jobs(id,key,payload,state,created_at,updated_at) VALUES(?,?,?,?,?,?)", (job_id, body["idempotency_key"], payload, "submitted", now(), now()))
                self.event(db, job_id, "submitted", {"synthetic": True})
        if fresh:
            try:
                self.sender(self.webhook, {"request_id": job_id})
            except (OSError, URLError, TimeoutError):
                with self.db() as db:
                    if self.find(db, job_id)["state"] == "submitted":
                        self.change(db, job_id, "failed", error_code="n8n_forward_failed")
                raise ApiError(502, "n8n_forward_failed", "Local n8n did not acknowledge this request; request is retained.")
        return self.public(job_id)

    def validate(self, body):
        schema(body, {"request_id"})
        job_id = request_id(body)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.find(db, job_id)
            if row["state"] not in {"submitted", "validated", "blocked"}:
                raise ApiError(409, "state", "Validation requires submitted input.")
            payload = json.loads(row["payload"])
            valid, issues = workforce.validate(payload["records"])
            if len(valid) != 4:
                issues.append({"row": 0, "code": "four_worker_count", "reason": "Exactly four valid synthetic workers are required."})
            # Equality includes types after workforce.validate. Order is immutable fixture order.
            if not issues and valid != self.fixture["snapshot"]["records"]:
                issues.append({"row": 0, "code": "fixture_mismatch", "reason": "Records must exactly match the bundled synthetic fixture."})
            try:
                planner.parse_request(payload["request"])
            except ValueError as exc:
                issues.append({"row": 0, "code": "request_constraints", "reason": str(exc)})
            source = self.fixture["aggregate"]["source_json_sha256"]
            if row["state"] == "submitted":
                self.change(db, job_id, "blocked" if issues else "validated", issues=encode(issues), source_sha256=source)
            return {"request_id": job_id, "valid": not issues, "issues": issues, "source_sha256": source}

    def analyze(self, body):
        schema(body, {"request_id"})
        job_id = request_id(body)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.find(db, job_id)
            if row["result"]:
                result = json.loads(row["result"])
                return {"request_id": job_id, "ok": True, "experiment_id": result["experiment_id"], "summary": summarize(result)}
            if row["state"] == "failed":
                return {"request_id": job_id, "ok": False, "error_code": row["error_code"]}
            if row["state"] == "analyzing":
                return {"request_id": job_id, "ok": False, "error_code": "analysis_in_progress"}
            if row["state"] != "validated":
                raise ApiError(409, "state", "Only a validated fixed fixture can reach inference.")
            self.change(db, job_id, "analyzing")
            payload = json.loads(row["payload"])
            source_hash = row["source_sha256"]
        try:
            # No database lock is held across model work; one shared model invocation at a time.
            with MODEL_LOCK:
                require_source_hash(source_hash)
                plan = planner.plan(payload["request"], "llm")
                require_source_hash(source_hash)
                result = engine.compare(plan)
                require_source_hash(source_hash)
                if result["hr"]["source_json_sha256"] != source_hash:
                    raise SourceChanged()
            with self.db() as db:
                self.change(db, job_id, "analyzed", result=encode(result))
            return {"request_id": job_id, "ok": True, "experiment_id": result["experiment_id"], "summary": summarize(result)}
        except SourceChanged:
            with self.db() as db:
                self.change(db, job_id, "failed", error_code="source_changed")
            return {"request_id": job_id, "ok": False, "error_code": "source_changed"}
        except Exception:
            # Do not expose model paths, secrets or tracebacks through the API.
            with self.db() as db:
                self.change(db, job_id, "failed", error_code="model_or_simulation_failed")
            return {"request_id": job_id, "ok": False, "error_code": "model_or_simulation_failed"}

    def await_review(self, body):
        schema(body, {"request_id", "resume_url", "execution_id"})
        job_id, url = request_id(body), check_resume_url(body["resume_url"])
        execution_id = str(body["execution_id"]) if type(body["execution_id"]) in (str, int) else ""
        if not re.fullmatch(r"[0-9]+", execution_id):
            raise ApiError(400, "execution_id", "n8n execution ID must be numeric.")
        if urlsplit(url).path.split("/")[2] != execution_id:
            raise ApiError(400, "execution_mismatch", "Resume URL must match the n8n execution ID.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.find(db, job_id)
            if row["state"] == "awaiting_approval" and row["resume_url"] == url and row["n8n_execution_id"] == execution_id:
                return {"request_id": job_id, "status": "awaiting_approval"}
            if row["state"] != "analyzed":
                raise ApiError(409, "state", "Only an analyzed experiment can wait for review.")
            self.change(db, job_id, "awaiting_approval", resume_url=url, n8n_execution_id=execution_id)
        return {"request_id": job_id, "status": "awaiting_approval"}

    def decision(self, body):
        schema(body, {"request_id", "decision"})
        job_id = request_id(body)
        decision = body["decision"]
        if not isinstance(decision, str) or decision not in {"approve", "reject"}:
            raise ApiError(400, "decision", "Decision must be approve or reject.")
        # Avoid simultaneous browser retries; finalized state can still arrive asynchronously.
        with self.decision_lock:
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = self.find(db, job_id)
                if row["decision"] and row["decision"] != decision:
                    raise ApiError(409, "decision_conflict", "The persisted review decision is immutable.")
                if row["state"] in {"approved", "rejected"}:
                    terminal = True
                else:
                    terminal = False
                    if row["state"] not in {"awaiting_approval", "decision_pending"}:
                        raise ApiError(409, "state", "A reviewer can decide only an awaiting experiment.")
                    url = check_resume_url(row["resume_url"])
                    if row["state"] == "awaiting_approval":
                        self.change(db, job_id, "decision_pending", decision=decision)
                acknowledged = db.execute("SELECT 1 FROM events WHERE job_id=? AND stage='resume_acknowledged' LIMIT 1", (job_id,)).fetchone() is not None
            if not terminal and not acknowledged:
                try:
                    self.sender(url, {"request_id": job_id, "decision": decision})
                    with self.db() as db:
                        self.event(db, job_id, "resume_acknowledged", {"decision": decision})
                except (OSError, URLError, TimeoutError):
                    with self.db() as db:
                        self.event(db, job_id, "resume_failed", {"error_code": "n8n_resume_failed", "retry_same_decision": True})
                    raise ApiError(502, "n8n_resume_failed", "Decision was persisted; retry the same decision to resume local n8n.")
        return self.public(job_id)

    def finalize(self, body):
        schema(body, {"request_id", "decision"})
        job_id, decision = request_id(body), body["decision"]
        if not isinstance(decision, str) or decision not in {"approve", "reject"}:
            raise ApiError(400, "decision", "Decision must be approve or reject.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.find(db, job_id)
            if row["decision"] != decision or row["state"] not in {"decision_pending", "approved", "rejected"}:
                raise ApiError(409, "approval_required", "Finalize requires the same durable browser review decision.")
            if row["state"] == "decision_pending":
                result = json.loads(row["result"])
                summary = summarize(result)
                if decision == "approve" and summary["training_required"]:
                    plan_id = uuid.uuid4().hex
                    content = {"id": plan_id, "job_id": job_id, "synthetic": True,
                               "reviewer": "local_demo_reviewer", "approved_at": now(),
                               "experiment_id": result["experiment_id"], "scenario_id": summary["recommended_scenario_id"],
                               "before": summary["before"], "after": summary["after"],
                               "participants": result["hr"]["training_participants"], "hours": result["hr"]["total_training_hours"],
                               "assumptions": result["assumptions"], "model": result["plan"]["model"],
                               "source_sha256": row["source_sha256"], "limitations": result["recommendation"]["limitations"]}
                    db.execute("INSERT INTO training_plans(id,job_id,content) VALUES(?,?,?)", (plan_id, job_id, encode(content)))
                self.change(db, job_id, "approved" if decision == "approve" else "rejected")
                self.event(db, job_id, "review_decision", {"decision": decision, "reviewer": "local_demo_reviewer"})
        return self.public(job_id)


class Handler(BaseHTTPRequestHandler):
    server_version = "FactoryLocalDemo/1.0"

    def log_message(self, format, *args):
        pass

    def reply(self, status, value):
        data = encode(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def guard(self, post=False):
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}", f"[::1]:{self.server.server_port}"}
        if host not in allowed:
            raise ApiError(403, "host", "A loopback Host is required.")
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            raise ApiError(403, "origin", "Only the exact same loopback origin is accepted.")
        if post:
            if self.path.startswith("/api/workflow/"):
                if self.headers.get("X-Workflow-Client") != MARKER:
                    raise ApiError(403, "workflow_marker", "The isolated local workflow marker is required.")
            elif origin != f"http://{host}":
                raise ApiError(403, "origin", "Browser writes require the same-origin header.")

    def do_GET(self):
        try:
            self.guard()
            parsed = urlsplit(self.path)
            store = self.server.store
            if parsed.path == "/api/fixture":
                return self.reply(200, store.fixture["snapshot"])
            if parsed.path == "/api/jobs":
                return self.reply(200, store.list_jobs())
            if parsed.path == "/api/job":
                query = parse_qs(parsed.query)
                if set(query) != {"id"} or len(query["id"]) != 1:
                    raise ApiError(400, "query", "Exactly one id is required.")
                job_id = request_id({"request_id": query["id"][0]})
                return self.reply(200, store.public(job_id))
            if parsed.path == "/api/status":
                return self.reply(200, {"synthetic": True, "model": planner.status(), "n8n_configured": True,
                                        "adapter_port": self.server.server_port, "n8n_port": 5679,
                                        "workflow_marker_is_production_auth": False})
            if parsed.path.startswith("/api/"):
                raise ApiError(404, "not_found", "Endpoint was not found.")
            if parsed.query or "%" in parsed.path or "\\" in parsed.path or ".." in parsed.path:
                raise ApiError(400, "path", "Invalid static path.")
            web = (ROOT / "web").resolve()
            target = (web / (parsed.path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(web) or not target.is_file():
                raise ApiError(404, "not_found", "File was not found.")
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(target)[0] or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except ApiError as exc:
            self.reply(exc.status, {"error_code": exc.code, "message": exc.message})

    def do_POST(self):
        try:
            self.guard(post=True)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json" or self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "content_type", "Bounded JSON with Content-Length is required.")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = 0
            if not 1 <= size <= 32768:
                raise ApiError(413, "body_size", "JSON payload must be 1–32768 bytes.")
            try:
                body = json.loads(self.rfile.read(size).decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "json", "Invalid JSON payload.")
            routes = {"/api/submit": "submit", "/api/decision": "decision",
                      "/api/workflow/validate": "validate", "/api/workflow/analyze": "analyze",
                      "/api/workflow/await-review": "await_review", "/api/workflow/finalize": "finalize"}
            method = routes.get(self.path)
            if not method:
                raise ApiError(404, "not_found", "Endpoint was not found.")
            self.reply(200, getattr(self.server.store, method)(body))
        except ApiError as exc:
            self.reply(exc.status, {"error_code": exc.code, "message": exc.message})
        except (TypeError, ValueError):
            self.reply(400, {"error_code": "schema", "message": "Invalid field value/type."})
        except Exception:
            self.reply(500, {"error_code": "adapter_failure", "message": "Adapter operation failed; inspect local runtime logs."})


def make_server(port=8770, db_path=None, sender=post_json):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.store = Store(db_path or ROOT / "data" / "jobs.sqlite3", sender)
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "jobs.sqlite3")
    args = parser.parse_args()
    server = make_server(args.port, args.db)
    print(f"Synthetic factory adapter http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
