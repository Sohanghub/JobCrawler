from ..models import JobPosting, make_id


def fetch(company, http):
    url = f"https://api.lever.co/v0/postings/{company['token']}?mode=json"
    r = http.get(url, cache=True)
    r.raise_for_status()
    jobs = []
    for j in r.json():
        categories = j.get("categories") or {}
        jobs.append(JobPosting(
            id=make_id(company["name"], native_id=j.get("id", ""),
                       url=j.get("hostedUrl", "")),
            company=company["name"],
            title=j.get("text", ""),
            location=categories.get("location") or "",
            url=j.get("hostedUrl", ""),
            description=(j.get("descriptionPlain") or "")[:2000],
            posted_at=str(j.get("createdAt", "")),
            source_tier=0,
        ))
    return jobs
