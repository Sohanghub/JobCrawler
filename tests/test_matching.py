import pytest

from jobcrawler.matching import matches
from jobcrawler.models import JobPosting

FILTERS = {
    "roles": ["Software Engineer", "Backend Engineer"],
    "title_threshold": 85,
    "locations": ["Remote", "India", "Bengaluru"],
}


def job(title, location):
    return JobPosting(id="x", company="C", title=title, location=location,
                      url="http://x")


@pytest.mark.parametrize("title,location,expected", [
    ("Software Engineer", "Bengaluru, India", True),
    ("Senior Software Engineer, Payments", "Remote - India", True),
    ("Backend Engineer II", "Bengaluru", True),
    ("Account Executive", "Bengaluru, India", False),     # wrong role
    ("Software Engineer", "New York, USA", False),        # wrong location
    ("SOFTWARE ENGINEER", "REMOTE", True),                # case-insensitive
])
def test_matches(title, location, expected):
    assert matches(job(title, location), FILTERS) is expected


FILTERS_EXP = {**FILTERS, "experience": "0-2 years"}


@pytest.mark.parametrize("title,description,expected", [
    ("Software Engineer", "", True),                       # no signal: keep
    ("Senior Software Engineer", "", False),               # seniority in title
    ("Staff Backend Engineer", "", False),
    ("Software Engineer", "Requires 5+ years of Python", False),
    ("Software Engineer", "3-5 years experience needed", False),
    ("Software Engineer", "0-2 years of experience", True),
    ("Software Engineer Intern", "5+ years preferred", True),  # junior title wins
    ("Junior Software Engineer", "", True),
])
def test_experience_heuristic(title, description, expected):
    j = job(title, "Remote")
    j.description = description
    assert matches(j, FILTERS_EXP) is expected
