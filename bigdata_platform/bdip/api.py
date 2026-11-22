"""Read-only REST API over the warehouse, using only the Python standard library."""

import json
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

MAX_ROWS = 1000
_SELECT_ONLY = re.compile(r"^\s*select\b", re.IGNORECASE)


def is_safe_query(sql: str) -> bool:
    """Allow a single SELECT statement only."""
    return bool(sql) and bool(_SELECT_ONLY.match(sql)) and ";" not in sql


class Api:
    def __init__(self, warehouse_path):
        self.warehouse_path = str(warehouse_path)

    def _conn(self):
        # Read-only connection: even a crafted query cannot modify the warehouse.
        conn = sqlite3.connect(f"file:{self.warehouse_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def rows(self, sql, params=()):
        conn = self._conn()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchmany(MAX_ROWS)]
        finally:
            conn.close()

    def tables(self):
        return [r["name"] for r in self.rows(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

    def handle(self, path, query):
        """Return (status_code, payload)."""
        if path in ("", "/"):
            return 200, {"service": "Big Data Integration and Management Platform",
                         "endpoints": ["/health", "/catalog", "/lineage", "/quality?stage=raw|clean",
                                       "/runs", "/tables", "/tables/<name>?limit=&offset=",
                                       "/query?sql=SELECT ..."]}
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/catalog":
            return 200, self.rows("SELECT * FROM catalog ORDER BY layer, dataset")
        if path == "/lineage":
            return 200, self.rows("SELECT * FROM lineage")
        if path == "/runs":
            return 200, self.rows("SELECT * FROM pipeline_runs ORDER BY started_at DESC")
        if path == "/quality":
            stage = query.get("stage", [None])[0]
            if stage:
                return 200, self.rows("SELECT * FROM dq_report WHERE stage = ?", (stage,))
            return 200, self.rows("SELECT * FROM dq_report")
        if path == "/tables":
            return 200, self.tables()
        if path.startswith("/tables/"):
            name = unquote(path[len("/tables/"):])
            if name not in self.tables():
                return 404, {"error": f"unknown table '{name}'"}
            try:
                limit = min(int(query.get("limit", ["100"])[0]), MAX_ROWS)
                offset = max(int(query.get("offset", ["0"])[0]), 0)
            except ValueError:
                return 400, {"error": "limit and offset must be integers"}
            return 200, self.rows(f'SELECT * FROM "{name}" LIMIT ? OFFSET ?', (limit, offset))
        if path == "/query":
            sql = query.get("sql", [""])[0]
            if not is_safe_query(sql):
                return 400, {"error": "only a single SELECT statement is allowed"}
            try:
                return 200, self.rows(sql)
            except sqlite3.Error as exc:
                return 400, {"error": str(exc)}
        return 404, {"error": "not found"}


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            status, payload = api.handle(parsed.path.rstrip("/") or "/", parse_qs(parsed.query))
            body = json.dumps(payload, indent=2, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            print(f"[api] {self.address_string()} {fmt % args}")

    return Handler


def serve(warehouse_path, host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), make_handler(Api(warehouse_path)))
    print(f"Serving on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
