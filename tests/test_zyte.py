import pytest

from jobcrawler.fetchers import zyte_tier3

LISTING = """
<ul><li class="j"><a href="/jobs/1">Platform Engineer</a>
<span class="l">Remote</span></li></ul>
"""

COMPANY = {
    "name": "Blocked Co",
    "url": "https://blocked.example/careers",
    "selectors": {"job_item": "li.j", "title": "a", "link": "a",
                  "location": ".l"},
}


class FakeResponse:
    def json(self):
        return {"browserHtml": LISTING}

    def raise_for_status(self):
        pass


class FakeHttp:
    def __init__(self):
        self.calls = 0

    def post(self, url, **kwargs):
        self.calls += 1
        assert kwargs["auth"] == ("k", "")
        assert kwargs["json"]["browserHtml"] is True
        return FakeResponse()


def test_zyte_fetch_and_cap(monkeypatch):
    monkeypatch.setenv("ZYTE_API_KEY", "k")
    monkeypatch.setenv("MAX_ZYTE_REQUESTS_PER_RUN", "1")
    monkeypatch.setattr(zyte_tier3, "_used", 0)
    http = FakeHttp()
    jobs = zyte_tier3.fetch(COMPANY, http)
    assert [(j.title, j.location) for j in jobs] == [("Platform Engineer",
                                                      "Remote")]
    assert jobs[0].source_tier == 1  # parsed via the tier-1 selector parser
    with pytest.raises(RuntimeError, match="cap"):
        zyte_tier3.fetch(COMPANY, http)
    assert http.calls == 1  # capped request never went out


def test_zyte_requires_key(monkeypatch):
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    monkeypatch.setattr(zyte_tier3, "_used", 0)
    with pytest.raises(RuntimeError, match="ZYTE_API_KEY"):
        zyte_tier3.fetch(COMPANY, FakeHttp())
