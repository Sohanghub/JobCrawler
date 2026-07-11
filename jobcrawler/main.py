import logging
import os

from . import matching, notify, registry
from .fetchers import FETCHERS
from .http import session
from .store import Store

log = logging.getLogger("jobcrawler")


def load_env(path=".env"):
    # ponytail: 8-line .env loader; swap for python-dotenv if it ever needs more
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    load_env()
    companies = registry.load_companies()
    filters = matching.load_filters()
    store = Store()
    http = session()
    seed_mode = store.is_empty()

    fresh = []
    for c in companies:
        name = c["name"]
        fetch = FETCHERS.get(c["ats"])
        if not fetch:
            log.warning("%s: no fetcher for ats=%r (tier %s), skipped",
                        name, c["ats"], c.get("tier"))
            store.log_run(name, "skipped", 0, f"no fetcher for {c['ats']}")
            continue
        try:
            jobs = fetch(c, http)
        except Exception as e:
            log.error("%s: fetch failed: %s", name, e)
            store.log_run(name, "error", 0, str(e))
            continue
        matched_ids = {j.id for j in jobs if matching.matches(j, filters)}
        new = store.insert_new(jobs, matched_ids)
        fresh.extend(j for j in new if j.id in matched_ids)
        store.log_run(name, "ok", len(jobs))
        log.info("%s: %d jobs, %d matched, %d new", name, len(jobs),
                 len(matched_ids), len(new))

    if seed_mode:
        log.info("first run: seeded DB silently, no notifications "
                 "(%d jobs would have matched)", len(fresh))
    elif fresh:
        notify.send(fresh)
        log.info("notified %d fresh matching job(s)", len(fresh))
    else:
        log.info("no fresh matches today")


if __name__ == "__main__":
    main()
