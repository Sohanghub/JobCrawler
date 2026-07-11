from ..models import JobPosting, make_id


def fetch(company, http):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company['token']}"
    r = http.get(url, cache=True)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("jobs", []):
        jobs.append(JobPosting(
            id=make_id(company["name"], native_id=j.get("id", ""),
                       url=j.get("jobUrl", "")),
            company=company["name"],
            title=j.get("title", ""),
            location=j.get("location", ""),
            url=j.get("jobUrl", ""),
            description=(j.get("descriptionPlain") or "")[:2000],
            posted_at=j.get("publishedAt", ""),
            source_tier=0,
        ))
    return jobs
