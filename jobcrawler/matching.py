import datetime
import re

import yaml

# Workday reports relative age in prose instead of a date.
POSTED_AGO_RE = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s*days?\s*ago)", re.I)

SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|manager|head|vp|architect)\b",
    re.I)
JUNIOR_RE = re.compile(
    r"\b(intern|internship|junior|jr\.?|new grad|graduate|entry[- ]level)\b", re.I)
# "N[+/-M] years" with N as the required minimum; "years ago/old" is company
# history ("founded 12 years ago"), not a requirement
YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:-|–|to)?\s*\d*\s*\+?\s*years?\b(?!\s*(?:ago|old))", re.I)
# "Engineer III" / "SDE 4" / "SWE L5" style level suffixes; II and below pass
LEVEL_RE = re.compile(r"\b(?:iii|iv|v|[lp]?[3-9])\b", re.I)


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
    # level suffix check, with year phrases stripped first so
    # "Engineer (1 - 3 Years)" isn't read as a level-3 title
    if LEVEL_RE.search(YEARS_RE.sub("", job.title)):
        return False
    # any years mention above the cap rejects — titles lie ("Forward
    # Deployed Engineer" wanting 7+ yrs), descriptions state it outright
    for text in (job.title, job.description):
        for m in YEARS_RE.finditer(text):
            if int(m.group(1)) > max_years:
                return False
    return True


def _posted_date(posted_at):
    """Best-effort parse across ATS formats (ISO string, Lever epoch-ms,
    Workday's "Posted N Days Ago" prose); None if none of them fit."""
    if not posted_at:
        return None
    if posted_at.isdigit():
        return datetime.datetime.fromtimestamp(
            int(posted_at) / 1000, tz=datetime.timezone.utc)
    m = POSTED_AGO_RE.search(posted_at)
    if m:
        now = datetime.datetime.now(datetime.timezone.utc)
        word = m.group(1).lower()
        if word == "today":
            return now
        if word == "yesterday":
            return now - datetime.timedelta(days=1)
        return now - datetime.timedelta(days=int(m.group(2)))
    try:
        return datetime.datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def posted_recently(job, filters):
    # ponytail: unparseable/missing dates pass through rather than being
    # dropped, since a wrong "too old" guess loses a job silently.
    max_days = filters.get("max_days_old")
    if not max_days:
        return True
    dt = _posted_date(job.posted_at)
    if dt is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - dt).days <= max_days


# spelled-out forms collapse to the short role keyword before comparing
_ALIASES = (("machine learning", "ml"), ("artificial intelligence", "ai"))


def _norm(s):
    s = s.lower()
    for long, short in _ALIASES:
        s = s.replace(long, short)
    return s


def title_ok(job, filters):
    """Role words must appear in the title in order, with at most one word
    between them: "Software Development Engineer" matches "Software
    Engineer", but "Escalation Engineer - AI Security" does not match
    "AI Engineer". Replaces fuzzy partial_ratio, which scored any
    '* Engineer' title 90 vs 'AI Engineer'."""
    title = _norm(job.title)
    for kw in filters["roles"]:
        words = re.findall(r"[a-z0-9]+", _norm(kw))
        pat = r"\b" + r"\W+(?:\w+\W+)?".join(map(re.escape, words)) + r"\b"
        if re.search(pat, title):
            return True
    return False


def deterministic_ok(job, filters):
    """Location + experience checks, applied on top of the title match."""
    location = job.location
    # whole words only: substring "india" also matched Indianapolis/Indiana
    loc_ok = any(re.search(rf"\b{re.escape(loc)}\b", location, re.I)
                 for loc in filters["locations"])
    # bare "Remote" only: "Remote - US" names elsewhere, and "Remote - India"
    # already passes via the locations list
    if filters.get("include_remote") and location.strip().lower() == "remote":
        loc_ok = True
    return loc_ok and experience_ok(job, filters) and posted_recently(job, filters)


def matches(job, filters):
    return title_ok(job, filters) and deterministic_ok(job, filters)
