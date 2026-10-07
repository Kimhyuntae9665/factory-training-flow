"""Factory Scenario Lab loopback HTTP server and transactional experiment history."""
import argparse
import datetime as dt
import json
import mimetypes
import re
import sqlite3
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import engine
import planner
import workforce

ROOT = Path(__file__).resolve().parent


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, plan_id TEXT, created_at TEXT, payload TEXT)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(experiments)")}
            if "workforce_snapshot" not in columns:
                db.execute("ALTER TABLE experiments ADD COLUMN workforce_snapshot TEXT")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def now():
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")

    def save_plan(self, plan):
        with self.lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO plans VALUES (?,?,?)", (plan["plan_id"], self.now(), json.dumps(plan, ensure_ascii=False, allow_nan=False)))
        return plan

    def get_plan(self, pid):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT payload FROM plans WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError("plan not found")
        return json.loads(row[0])

    def save_experiment(self, exp):
        state = workforce.load()
        if state["aggregate"]["source_json_sha256"] != exp["hr"]["source_json_sha256"]:
            raise ValueError("synthetic workforce snapshot changed during experiment; retry required")
        with self.lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO experiments(id,plan_id,created_at,payload,workforce_snapshot) VALUES (?,?,?,?,?)", (exp["experiment_id"], exp["plan"]["plan_id"], self.now(), json.dumps(exp, ensure_ascii=False, allow_nan=False), json.dumps(state["snapshot"], ensure_ascii=False)))
        return exp

    def get_experiment(self, eid):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT payload FROM experiments WHERE id=?", (eid,)).fetchone()
        if not row:
            raise KeyError("experiment not found")
        return json.loads(row[0])

    def history(self):
        with self.lock, self.connection() as db:
            rows = db.execute("SELECT id,plan_id,created_at,payload FROM experiments ORDER BY created_at DESC,id DESC LIMIT 10").fetchall()
        items = []
        for eid, pid, created, payload in rows:
            exp = json.loads(payload)
            items.append({"experiment_id": eid, "plan_id": pid, "created_at": created, "request": exp["plan"]["request"],
                          "mode": exp["plan"]["mode"], "selected_ids": exp["plan"]["selected_ids"], "recommendation": exp["recommendation"]["scenario_id"]})
        return {"items": items}


class Handler(BaseHTTPRequestHandler):
    server_version = "FactoryScenarioLab/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def send_json(self, status, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def host_ok(self):
        try:
            host = urlsplit("http://" + self.headers.get("Host", ""))
            return host.hostname in ("127.0.0.1", "localhost") and host.port == self.server.server_port and not host.username and not host.path and not host.query and not host.fragment
        except ValueError:
            return False

    def do_GET(self):
        if not self.host_ok():
            return self.send_json(403, {"error": "loopback Host required"})
        url = urlsplit(self.path)
        try:
            if url.path == "/api/status":
                return self.send_json(200, {"model": planner.status(), "engine": f"SimPy {engine.simpy.__version__}", "synthetic": True})
            if url.path == "/api/demo":
                return self.send_json(200, self.server.demo)
            if url.path == "/api/history":
                return self.send_json(200, self.server.store.history())
            if url.path == "/api/experiment":
                query = parse_qs(url.query)
                if set(query) != {"id"} or len(query["id"]) != 1 or not re.fullmatch(r"[0-9a-f]{32}|demo-default", query["id"][0]):
                    return self.send_json(400, {"error": "invalid experiment id"})
                eid = query["id"][0]
                return self.send_json(200, self.server.demo if eid == "demo-default" else self.server.store.get_experiment(eid))
            if url.path.startswith("/api/"):
                return self.send_json(404, {"error": "route not found"})
            decoded = unquote(url.path)
            if "\\" in decoded or "\x00" in decoded:
                return self.send_json(404, {"error": "file not found"})
            base = (ROOT / "web").resolve()
            target = (base / (decoded.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                return self.send_json(404, {"error": "file not found"})
            raw = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)
        except KeyError:
            self.send_json(404, {"error": "experiment not found"})
        except Exception:
            self.send_json(500, {"error": "local service error"})

    def do_POST(self):
        if not self.host_ok():
            return self.send_json(403, {"error": "loopback Host required"})
        if self.headers.get("Origin") not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return self.send_json(403, {"error": "loopback Origin required"})
        path = urlsplit(self.path).path
        if path not in ("/api/plan", "/api/compare"):
            return self.send_json(404, {"error": "route not found"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if self.headers.get("Transfer-Encoding") or not 0 <= length <= 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError("invalid JSON request")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid object")
            if path == "/api/plan":
                if set(data) != {"request", "mode"} or not isinstance(data["request"], str) or not isinstance(data["mode"], str):
                    raise ValueError("request and mode are required strings")
                result = self.server.store.save_plan(planner.plan(data["request"], data["mode"]))
            else:
                if set(data) != {"plan_id"} or not isinstance(data["plan_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", data["plan_id"]):
                    raise ValueError("invalid plan id")
                plan = self.server.store.get_plan(data["plan_id"])
                result = self.server.store.save_experiment(engine.compare(plan))
            self.send_json(200, result)
        except (ValueError, TypeError, UnicodeError) as error:
            # Parser errors contain fixed explanations, never user text or paths.
            message = str(error) if isinstance(error, ValueError) and len(str(error)) <= 180 else "invalid request"
            self.send_json(400, {"error": message})
        except KeyError:
            self.send_json(404, {"error": "plan not found"})
        except RuntimeError:
            self.send_json(503, {"error": "로컬 모델 실행 실패. 규칙으로 대체하지 않았습니다. 상태와 모델 경로를 확인하세요."})
        except Exception:
            self.send_json(500, {"error": "local service error"})


def make_server(port=8766, db_path=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.store = Store(db_path or ROOT / "data" / "factory-state.sqlite3")
    server.demo = engine.demo()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    server = make_server(args.port)
    print(f"Factory Scenario Lab http://127.0.0.1:{args.port} · synthetic only", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
