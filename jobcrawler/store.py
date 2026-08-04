import datetime
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
    id TEXT PRIMARY KEY,
    company TEXT, title TEXT, location TEXT, url TEXT,
    posted_at TEXT, first_seen TEXT, matched INTEGER);
CREATE TABLE IF NOT EXISTS run_log(
    run_date TEXT, company TEXT, status TEXT, jobs_found INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS page_cache(
    url TEXT PRIMARY KEY, etag TEXT, last_modified TEXT,
    body_sha1 TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS robots_cache(
    host TEXT PRIMARY KEY, body TEXT, fetched_at TEXT);
"""


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path="data/jobs.db"):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def is_empty(self):
        return self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    def insert_new(self, jobs, matched_ids):
        """Insert all fetched jobs; return only the never-seen-before ones.

        Unmatched jobs are stored too, so loosening filters later never
        re-notifies old postings. Already-seen jobs get their matched flag
        refreshed so filter edits propagate to stored rows.
        """
        now = _utcnow()
        new = []
        for j in jobs:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (j.id, j.company, j.title, j.location, j.url,
                 j.posted_at, now, int(j.id in matched_ids)))
            if cur.rowcount:
                new.append(j)
            else:
                self.db.execute("UPDATE jobs SET matched=? WHERE id=?",
                                (int(j.id in matched_ids), j.id))
        self.db.commit()
        return new

    def log_run(self, company, status, jobs_found, error=""):
        self.db.execute("INSERT INTO run_log VALUES (?,?,?,?,?)",
                        (_utcnow(), company, status, jobs_found, error))
        self.db.commit()

    def get_cache(self, url):
        row = self.db.execute(
            "SELECT etag, last_modified, body_sha1 FROM page_cache WHERE url=?",
            (url,)).fetchone()
        if not row:
            return None
        return {"etag": row[0], "last_modified": row[1], "body_sha1": row[2]}

    def set_cache(self, url, etag, last_modified, body_sha1):
        self.db.execute("INSERT OR REPLACE INTO page_cache VALUES (?,?,?,?,?)",
                        (url, etag, last_modified, body_sha1, _utcnow()))
        self.db.commit()

    def get_robots(self, host, max_age):
        """Cached robots.txt body, or None when absent or older than max_age
        seconds. An empty body is a real answer ("no rules"), not a miss."""
        row = self.db.execute(
            "SELECT body, fetched_at FROM robots_cache WHERE host=?",
            (host,)).fetchone()
        if not row:
            return None
        try:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(row[1])).total_seconds()
        except (TypeError, ValueError):
            return None
        return row[0] if age <= max_age else None

    def set_robots(self, host, body):
        self.db.execute("INSERT OR REPLACE INTO robots_cache VALUES (?,?,?)",
                        (host, body, _utcnow()))
        self.db.commit()

    def health_alerts(self):
        """Companies that look silently broken, for the daily digest."""
        alerts = []
        for (name,) in self.db.execute("SELECT DISTINCT company FROM run_log"):
            rows = self.db.execute(
                "SELECT status, jobs_found, error FROM run_log "
                "WHERE company=? AND status != 'skipped' "
                "ORDER BY rowid DESC LIMIT 10", (name,)).fetchall()
            errors = 0
            for status, _, _ in rows:
                if status != "error":
                    break
                errors += 1
            if errors >= 2:
                alerts.append(f"{name}: {errors} consecutive failed runs "
                              f"({(rows[0][2] or '')[:120]})")
                continue
            if rows and rows[0][0] == "blocked":
                # Only worth reporting if the company used to deliver: one
                # that never parsed a job has nothing to have gone quiet.
                # Actionable either way — drop it, or point the registry at a
                # URL its robots.txt permits.
                if self.db.execute("SELECT 1 FROM run_log WHERE company=? AND "
                                   "status='ok' LIMIT 1", (name,)).fetchone():
                    alerts.append(f"{name}: blocked — "
                                  f"{(rows[0][2] or '')[:120]}")
                continue
            # compare the last two successfully parsed runs, over full
            # history: an old "ok 0" must not scroll out behind a run of
            # 'unchanged' rows and silence the alert
            oks = [jf for (jf,) in self.db.execute(
                "SELECT jobs_found FROM run_log WHERE company=? AND "
                "status='ok' ORDER BY rowid DESC LIMIT 2", (name,))]
            if len(oks) == 2 and oks[0] == 0 and oks[1] > 0:
                alerts.append(f"{name}: 0 jobs found (was {oks[1]}) — "
                              "parser may be broken")
        return alerts
