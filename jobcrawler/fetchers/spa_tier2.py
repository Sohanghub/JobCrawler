import re

from ..http import USER_AGENT
from ..models import JobPosting, make_id


def dig(obj, path):
    """'a.b.c' -> obj['a']['b']['c'], None-safe."""
    for key in path.split("."):
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def _get(item, path):
    value = dig(item, path) if path else None
    return "" if value is None else str(value)


def _extract(company, cfg, data):
    items = dig(data, cfg["jobs_path"]) if cfg.get("jobs_path") else data
    fields = cfg["fields"]
    jobs = []
    for it in items or []:
        title = _get(it, fields.get("title", "title"))
        location = _get(it, fields.get("location", "location"))
        url = _get(it, fields.get("url", "url"))
        jobs.append(JobPosting(
            id=make_id(company["name"], native_id=_get(it, fields.get("id", "")),
                       url=url, title=title, location=location),
            company=company["name"], title=title, location=location, url=url,
            description=_get(it, fields.get("description", ""))[:2000],
            source_tier=2))
    return jobs


def fetch(company, http):
    """Tier 2: SPA. Preferred: the site's own JSON endpoint recorded in the
    registry ('xhr', plain HTTP). Fallback: Playwright with network
    interception ('playwright') for sites whose endpoint can't be replayed.
    """
    if "xhr" in company:
        cfg = company["xhr"]
        if cfg.get("method", "GET").upper() == "POST":
            r = http.post(cfg["url"], json=cfg.get("body") or {})
        else:
            r = http.get(cfg["url"], cache=True)
        r.raise_for_status()
        return _extract(company, cfg, r.json())
    return _fetch_playwright(company)


def _first_with_jobs(company, cfg, payloads):
    """A page can fire several XHRs matching the capture regex; use the
    first payload the field mapping actually extracts jobs from."""
    for data in payloads:
        jobs = _extract(company, cfg, data)
        if jobs:
            return jobs
    raise RuntimeError(
        f"{len(payloads)} XHR(s) matching {cfg.get('capture')!r} captured on "
        f"{company.get('url')!r}, but none contained jobs at "
        f"{cfg.get('jobs_path')!r}")


def _fetch_playwright(company):
    from playwright.sync_api import sync_playwright  # lazy: optional heavy dep
    cfg = company["playwright"]
    pattern = re.compile(cfg["capture"])
    captured = []

    def on_response(resp):
        if pattern.search(resp.url):
            try:
                captured.append(resp.json())
            except Exception:
                pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)
        page.on("response", on_response)
        page.goto(company["url"], wait_until="networkidle", timeout=60000)
        browser.close()
    return _first_with_jobs(company, cfg, captured)
