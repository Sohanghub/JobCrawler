import re

import yaml
from rapidfuzz import fuzz

SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|manager|head|vp|architect)\b",
    re.I)
JUNIOR_RE = re.compile(
    r"\b(intern|internship|junior|jr\.?|new grad|graduate|entry[- ]level)\b", re.I)
# first "N[+/-M] years" mention is treated as the minimum required
YEARS_RE = re.compile(r"(\d{1,2})\s*(?:-|–|to)?\s*\d*\s*\+?\s*years?", re.I)


def load_filters(path="config/filters.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _max_years(filters):
    nums = re.findall(r"\d+", str(filters.get("experience", "")))
    return int(nums[-1]) if nums else None


def experience_ok(job, filters):
    # ponytail: regex heuristic; jobs with no signal pass through.
    # P3+ can add LLM inference on the already-matched short list.
    max_years = _max_years(filters)
    if max_years is None:
        return True
    if JUNIOR_RE.search(job.title):
        return True
    if SENIOR_RE.search(job.title) and max_years < 5:
        return False
    m = YEARS_RE.search(job.description)
    if m and int(m.group(1)) > max_years:
        return False
    return True


def title_ok(job, filters):
    threshold = filters.get("title_threshold", 85)
    title = job.title.lower()
    return any(fuzz.partial_ratio(kw.lower(), title) >= threshold
               for kw in filters["roles"])


def deterministic_ok(job, filters):
    """Location + experience checks — required regardless of whether the
    title matched via fuzzy or semantic similarity."""
    location = job.location.lower()
    loc_ok = any(loc.lower() in location for loc in filters["locations"])
    return loc_ok and experience_ok(job, filters)


def matches(job, filters):
    return title_ok(job, filters) and deterministic_ok(job, filters)
