from ..models import JobPosting, make_id

PAGE_SIZE = 20  # Workday cxs API maximum


def fetch(company, http):
    cfg = company["workday"]
    host, site = cfg["host"], cfg["site"]
    tenant = cfg.get("tenant", host.split(".")[0])
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    base = f"https://{host}/en-US/{site}"
    max_jobs = cfg.get("max_jobs", 2000)

    jobs, offset, total = [], 0, 1
    while offset < min(total, max_jobs):
        body = {"appliedFacets": cfg.get("facets", {}), "limit": PAGE_SIZE,
                "offset": offset, "searchText": cfg.get("search", "")}
        r = http.post(api, json=body, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        if offset == 0:  # some tenants report total=0 on every later page
            total = data.get("total", 0)
        postings = data.get("jobPostings", [])
        if not postings:
            break
        for p in postings:
            path = p.get("externalPath", "")
            jobs.append(JobPosting(
                id=make_id(company["name"], native_id=path,
                           title=p.get("title", "")),
                company=company["name"],
                title=p.get("title", ""),
                location=p.get("locationsText", ""),
                url=base + path,
                posted_at=p.get("postedOn", ""),
                source_tier=0,
            ))
        offset += PAGE_SIZE
    return jobs
