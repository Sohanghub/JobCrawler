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
        re-notifies old postings.
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
        self.db.commit()
        return new

    def log_run(self, company, status, jobs_found, error=""):
        self.db.execute("INSERT INTO run_log VALUES (?,?,?,?,?)",
                        (_utcnow(), company, status, jobs_found, error))
        self.db.commit()
