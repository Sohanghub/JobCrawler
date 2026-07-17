"""Tiny read-only web UI server: JSON API over data/jobs.db + static dist/.

Run from the repo root:  python webui/server.py  ->  http://localhost:8765
"""
import json
import os
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from jobcrawler.store import Store  # noqa: E402

DB = os.path.join(ROOT, "data", "jobs.db")
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
PAGE = 50


def query(handler):
    return {k: v[0] for k, v in parse_qs(urlparse(handler.path).query).items()}


def api_jobs(q):
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    where, args = ["1=1"], []
    if q.get("q"):
        where.append("(title LIKE ? OR location LIKE ?)")
        args += [f"%{q['q']}%"] * 2
    if q.get("company"):
        where.append("company=?")
        args.append(q["company"])
    if q.get("matched"):
        where.append("matched=1")
    cond = " AND ".join(where)
    total = db.execute(f"SELECT COUNT(*) FROM jobs WHERE {cond}", args).fetchone()[0]
    rows = db.execute(
        f"SELECT company, title, location, url, posted_at, first_seen, matched "
        f"FROM jobs WHERE {cond} ORDER BY first_seen DESC, posted_at DESC "
        f"LIMIT {PAGE} OFFSET ?", args + [int(q.get("offset", 0))]).fetchall()
    cols = ["company", "title", "location", "url", "posted_at", "first_seen", "matched"]
    return {"total": total, "jobs": [dict(zip(cols, r)) for r in rows]}


def api_meta(_q):
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    companies = db.execute(
        "SELECT company, COUNT(*) FROM jobs GROUP BY company ORDER BY company").fetchall()
    total, matched = db.execute(
        "SELECT COUNT(*), SUM(matched) FROM jobs").fetchone()
    last_run = db.execute("SELECT MAX(run_date) FROM run_log").fetchone()[0]
    return {"companies": [{"name": n, "count": c} for n, c in companies],
            "total": total, "matched": matched or 0, "last_run": last_run,
            "alerts": Store(DB).health_alerts()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def do_GET(self):
        route = urlparse(self.path).path
        fn = {"/api/jobs": api_jobs, "/api/meta": api_meta}.get(route)
        if not fn:
            return super().do_GET()
        body = json.dumps(fn(query(self))).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("JobCrawler UI -> http://localhost:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
