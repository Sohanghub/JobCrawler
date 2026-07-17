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
    """Tier 2: SPA fed by the site's own JSON endpoint recorded in the
    registry ('xhr', plain HTTP — no browser)."""
    cfg = company["xhr"]
    if cfg.get("method", "GET").upper() == "POST":
        r = http.post(cfg["url"], json=cfg.get("body") or {})
    else:
        r = http.get(cfg["url"], cache=True)
    r.raise_for_status()
    return _extract(company, cfg, r.json())
