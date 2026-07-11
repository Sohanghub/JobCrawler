import pytest

from jobcrawler.discovery import resolve


@pytest.mark.parametrize("text,expected", [
    ("https://boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
    ("https://job-boards.greenhouse.io/figma/jobs/123", ("greenhouse", "figma")),
    ("https://jobs.lever.co/spotify?lever-source=x", ("lever", "spotify")),
    ("https://jobs.eu.lever.co/acme", ("lever", "acme")),
    ("https://jobs.ashbyhq.com/linear", ("ashby", "linear")),
    ('<iframe src="https://boards.greenhouse.io/embed/job_board?for=acme">',
     ("greenhouse", "acme")),
    ("https://www.example.com/careers", None),
])
def test_detect_ats(text, expected):
    assert resolve.detect_ats(text) == expected


def test_detect_workday():
    hit = resolve.detect_ats(
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite")
    assert hit == ("workday",
                   ("nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite"))
    # locale prefix in the URL must not become the site
    hit = resolve.detect_ats(
        "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced")
    assert hit == ("workday",
                   ("adobe.wd5.myworkdayjobs.com", "external_experienced"))


def test_build_entry():
    assert resolve.build_entry("X", "greenhouse", "x") == {
        "name": "X", "tier": 0, "ats": "greenhouse", "token": "x"}
    assert resolve.build_entry("X", "workday", ("h", "s")) == {
        "name": "X", "tier": 0, "ats": "workday",
        "workday": {"host": "h", "site": "s"}}


def test_entry_from_llm():
    cand = {"name": "Acme", "url": "https://acme.example/careers"}
    sel = {"job_item": "li", "title": "a", "location": ".loc", "link": "a"}
    entry = resolve._entry_from_llm(
        cand, {"ats": "custom_html", "selectors": sel, "notes": ""})
    assert entry["ats"] == "html" and entry["tier"] == 1
    assert entry["url"] == cand["url"]
    assert resolve._entry_from_llm(cand, {"ats": "unknown", "notes": ""}) is None
    # incomplete answers must not produce entries
    assert resolve._entry_from_llm(cand, {"ats": "greenhouse", "notes": ""}) is None


def test_approve_gate_requires_jobs(monkeypatch):
    monkeypatch.setitem(resolve.FETCHERS, "greenhouse", lambda c, h: [])
    entry = resolve.build_entry("X", "greenhouse", "x")
    assert resolve.validate_entry(entry, http=None) == []  # gate rejects this
