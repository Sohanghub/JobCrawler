from ..models import JobPosting, make_id


def fetch(company, http):
    url = (f"https://boards-api.greenhouse.io/v1/boards/"
           f"{company['token']}/jobs?content=true")
    r = http.get(url, cache=True)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("jobs", []):
        jobs.append(JobPosting(
            id=make_id(company["name"], native_id=str(j["id"])),
            company=company["name"],
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=(j.get("content") or "")[:2000],
            posted_at=j.get("updated_at", ""),
            source_tier=0,
        ))
    return jobs
