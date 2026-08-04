import json
from types import SimpleNamespace

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


class FakeHttp:
    """Replays canned assistant messages; records what was posted."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.posted = []

    def post(self, url, **kwargs):
        self.posted.append(kwargs["json"])
        msg = self.replies.pop(0)
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": msg}]})


def _call(name, args, call_id="c1"):
    return {"id": call_id,
            "function": {"name": name, "arguments": json.dumps(args)}}


def test_agent_classify_loop(monkeypatch):
    monkeypatch.setitem(resolve.FETCHERS, "greenhouse",
                        lambda c, h: [SimpleNamespace(title="Engineer")])
    http = FakeHttp([
        {"role": "assistant", "content": None, "tool_calls": [
            _call("probe_token", {"ats": "greenhouse", "token": "acme"})]},
        {"role": "assistant", "content": None, "tool_calls": [
            _call("submit", {"ats": "greenhouse", "token": "acme",
                             "notes": "probe confirmed"})]},
    ])
    cand = {"name": "Acme", "url": "https://acme.example/careers"}
    data = resolve._agent_classify(cand, "<html>", http, key="k")
    assert data["ats"] == "greenhouse" and data["token"] == "acme"
    # probe result was fed back to the model as a tool message
    tool_msgs = [m for m in http.posted[1]["messages"] if m["role"] == "tool"]
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert "1 jobs live" in tool_msgs[0]["content"]


def test_agent_classify_turn_limit():
    chatter = {"role": "assistant", "content": "hmm", "tool_calls": None}
    http = FakeHttp([chatter] * resolve.MAX_TURNS)
    with pytest.raises(RuntimeError):
        resolve._agent_classify({"name": "X", "url": "u"}, "", http, key="k")
    # the final turn must force a verdict: submit-only toolset + tool_choice
    assert http.posted[-1]["tools"] == resolve.TOOLS[-1:]
    assert http.posted[-1]["tool_choice"]["function"]["name"] == "submit"
    assert any("budget exhausted" in (m.get("content") or "")
               for m in http.posted[-1]["messages"] if m["role"] == "user")
    assert all("tool_choice" not in b for b in http.posted[:-1])


def test_fetch_url_tool_refuses_private_targets():
    # a scraped page is attacker-controlled text one hop from our HTTP client;
    # the model must not be able to be talked into hitting the metadata service
    fetched = []
    http = SimpleNamespace(get=lambda url, **kw: fetched.append(url))
    for url in ("http://169.254.169.254/latest/meta-data/",
                "file:///etc/passwd",
                "http://localhost:8765/api/jobs"):
        result = resolve._run_tool("fetch_url", {"url": url}, http)
        assert result.startswith("refused:")
    assert fetched == []


def test_fetch_url_tool_allows_public_targets(monkeypatch):
    monkeypatch.setattr("jobcrawler.urls.is_private_address", lambda h: False)
    http = SimpleNamespace(get=lambda url, **kw: SimpleNamespace(text="<html>"))
    assert resolve._run_tool(
        "fetch_url", {"url": "https://acme.example/careers"}, http) == "<html>"


def test_find_careers_page_tool(monkeypatch):
    monkeypatch.setattr(resolve.sitemap, "find_careers_urls",
                        lambda http, url, **kw: ["https://acme.example/careers"])
    out = resolve._run_tool("find_careers_page",
                            {"url": "https://acme.example/"}, http=None)
    assert out == "https://acme.example/careers"
    monkeypatch.setattr(resolve.sitemap, "find_careers_urls",
                        lambda http, url, **kw: [])
    assert "no careers pages" in resolve._run_tool(
        "find_careers_page", {"url": "https://acme.example/"}, http=None)


def test_probe_falls_back_to_the_sitemap(monkeypatch):
    # the homepage names no ATS (the Greenhouse iframe lives on /careers),
    # so the sitemap hop is the only thing that resolves this candidate
    pages = {"https://acme.example/": "<html>we are hiring!</html>",
             "https://acme.example/careers":
                 '<iframe src="https://boards.greenhouse.io/acme">'}
    monkeypatch.setattr(resolve.sitemap, "find_careers_urls",
                        lambda http, url, **kw: ["https://acme.example/careers"])
    monkeypatch.setitem(resolve.FETCHERS, "greenhouse",
                        lambda c, h: [SimpleNamespace(title="Backend Engineer")])
    http = SimpleNamespace(get=lambda url, **kw: SimpleNamespace(text=pages[url]))
    entry, evidence = resolve.resolve_deterministic(
        {"name": "Acme", "url": "https://acme.example/"}, http)
    assert entry == {"name": "Acme", "tier": 0, "ats": "greenhouse",
                     "token": "acme"}
    assert "1 jobs live" in evidence


def test_sitemap_failure_leaves_the_candidate_unresolved(monkeypatch):
    monkeypatch.setattr(resolve.sitemap, "find_careers_urls",
                        lambda http, url, **kw: (_ for _ in ()).throw(
                            RuntimeError("no sitemap")))
    monkeypatch.setitem(resolve.FETCHERS, "greenhouse", lambda c, h: [])
    monkeypatch.setitem(resolve.FETCHERS, "lever", lambda c, h: [])
    monkeypatch.setitem(resolve.FETCHERS, "ashby", lambda c, h: [])
    http = SimpleNamespace(get=lambda url, **kw: SimpleNamespace(text="<html>"))
    assert resolve.resolve_deterministic(
        {"name": "Acme", "url": "https://acme.example/"}, http) == (None, None)


def test_infer_handles_urlless_candidates(tmp_path, monkeypatch):
    cands = tmp_path / "candidates.yaml"
    pend = tmp_path / "pending.yaml"
    import yaml
    cands.write_text(yaml.safe_dump([{"name": "acme", "url": ""}]))
    monkeypatch.setattr(resolve, "CANDIDATES", str(cands))
    monkeypatch.setattr(resolve, "PENDING", str(pend))
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    searched = []
    monkeypatch.setattr(resolve, "_http", lambda: SimpleNamespace(
        get=lambda url, **kw: (searched.append(url) or
                               SimpleNamespace(text="<search results>"))))
    monkeypatch.setattr(resolve, "_agent_classify",
                        lambda cand, page, http, key: {
                            "ats": "greenhouse", "token": "acme", "notes": "n"})
    resolve.cmd_infer(SimpleNamespace(limit=10))
    assert "duckduckgo" in searched[0]  # seeded via web search, not skipped
    pending = yaml.safe_load(pend.read_text())
    assert pending[0]["entry"]["token"] == "acme"
    assert yaml.safe_load(cands.read_text()) == []
