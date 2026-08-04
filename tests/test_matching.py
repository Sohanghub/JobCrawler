import datetime

import pytest

from jobcrawler.matching import matches
from jobcrawler.models import JobPosting

FILTERS = {
    "roles": ["Software Engineer", "Backend Engineer", "ML Engineer"],
    "locations": ["India", "Bengaluru"],
    "include_remote": False,
}


def job(title, location):
    return JobPosting(id="x", company="C", title=title, location=location,
                      url="http://x")


@pytest.mark.parametrize("title,location,expected", [
    ("Software Engineer", "Bengaluru, India", True),
    ("Senior Software Engineer, Payments", "Remote - India", True),
    ("Backend Engineer II", "Bengaluru", True),
    ("Machine Learning Engineer", "Bengaluru", True),     # ML alias
    ("Software Development Engineer II", "Bengaluru", True),  # one-word gap ok
    ("Account Executive", "Bengaluru, India", False),     # wrong role
    ("Escalation Engineer", "Bengaluru, India", False),   # engineer != our roles
    ("Escalation Engineer - AI Security", "Bengaluru", False),  # words out of order
    ("Software QA Tools Development Engineer", "Bengaluru", False),  # gap too wide
    ("ASIC Verification Engineer", "Bengaluru", False),
    ("Customer Support Specialist", "Bengaluru", False),
    ("Software Engineer", "New York, USA", False),        # wrong location
    ("Software Engineer", "Indianapolis, Indiana", False),  # "india" substring trap
    ("SOFTWARE ENGINEER", "REMOTE", False),               # bare remote, no India tie
])
def test_matches(title, location, expected):
    assert matches(job(title, location), FILTERS) is expected


@pytest.mark.parametrize("location,expected", [
    ("Remote", True),
    ("Remote - US", False),        # remote elsewhere is not remote-for-us
    ("Remote - India", True),      # passes via the locations list, not the toggle
    ("Remote - Indiana, USA", False),
    ("New York, USA", False),      # still needs bare "remote" or an India city
])
def test_include_remote_toggle(location, expected):
    filters = {**FILTERS, "include_remote": True}
    assert matches(job("Software Engineer", location), filters) is expected


FILTERS_EXP = {**FILTERS, "experience": "0-2 years"}


@pytest.mark.parametrize("title,description,expected", [
    ("Software Engineer", "", True),                       # no signal: keep
    ("Senior Software Engineer", "", False),               # seniority in title
    ("Staff Backend Engineer", "", False),
    ("Software Engineer", "Requires 5+ years of Python", False),
    ("Software Engineer", "3-5 years experience needed", False),
    ("Software Engineer", "0-2 years of experience", True),
    ("Software Engineer (3-5 Years)", "", False),          # years in the title
    ("Software Engineer Intern", "5+ years preferred", True),  # junior title wins
    ("Junior Software Engineer", "", True),
    ("Software Development Engineer 4", "", False),        # numeric level
    ("Software Engineer III", "", False),                  # roman level
    ("Software Engineer II", "", True),                    # II and below pass
    ("Backend Engineer (1 - 3 Years)", "", True),          # years, not a level
    ("Software Engineer", "founded 12 years ago", True),   # history, not a req
    # description outranks a harmless-looking title
    ("Software Engineer", "great intro... then 7+ years of experience", False),
])
def test_experience_heuristic(title, description, expected):
    j = job(title, "Bengaluru, India")
    j.description = description
    assert matches(j, FILTERS_EXP) is expected


def _iso_days_ago(days):
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return dt.isoformat().replace("+00:00", "Z")


FILTERS_AGE = {**FILTERS, "max_days_old": 7}


@pytest.mark.parametrize("posted_at,expected", [
    ("", True),                              # no signal: keep
    ("garbage", True),                       # unparseable: keep
    (_iso_days_ago(1), True),                # Greenhouse/Ashby ISO, fresh
    (_iso_days_ago(30), False),              # Greenhouse/Ashby ISO, stale
    ("Posted Today", True),                  # Workday prose
    ("Posted 3 Days Ago", True),
    ("Posted 30+ Days Ago", False),
    (str(int((datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=1)).timestamp() * 1000)), True),   # Lever epoch-ms, fresh
    (str(int((datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=30)).timestamp() * 1000)), False),  # Lever epoch-ms, stale
])
def test_posted_recently(posted_at, expected):
    j = job("Software Engineer", "Bengaluru, India")
    j.posted_at = posted_at
    assert matches(j, FILTERS_AGE) is expected
