import yaml
from rapidfuzz import fuzz


def load_filters(path="config/filters.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def matches(job, filters):
    threshold = filters.get("title_threshold", 85)
    title = job.title.lower()
    title_ok = any(fuzz.partial_ratio(kw.lower(), title) >= threshold
                   for kw in filters["roles"])
    location = job.location.lower()
    loc_ok = any(loc.lower() in location for loc in filters["locations"])
    # ponytail: experience filtering is a P2 regex heuristic; everything passes for now
    return title_ok and loc_ok
