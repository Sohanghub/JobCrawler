from jobcrawler.fetchers import spa_tier2

DATA = {"data": {"jobs": [
    {"id": "j1", "attributes": {"name": "Frontend Engineer"},
     "loc": {"city": "Remote"}, "link": "https://x.example/j1"},
]}}

COMPANY = {
    "name": "X",
    "xhr": {
        "url": "https://x.example/api/jobs",
        "jobs_path": "data.jobs",
        "fields": {"title": "attributes.name", "location": "loc.city",
                   "url": "link", "id": "id"},
    },
}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class FakeHttp:
    def get(self, url, **kwargs):
        return FakeResponse(DATA)


def test_xhr_dotted_path_extraction():
    jobs = spa_tier2.fetch(COMPANY, FakeHttp())
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.title, j.location, j.url) == ("Frontend Engineer", "Remote",
                                            "https://x.example/j1")
    assert j.source_tier == 2
    assert j.id


def test_dig_missing_path_is_none():
    assert spa_tier2.dig({"a": {"b": 1}}, "a.b") == 1
    assert spa_tier2.dig({"a": {"b": 1}}, "a.c.d") is None


def test_first_with_jobs_skips_jobless_payloads():
    cfg = COMPANY["xhr"]
    # first XHR matched the regex but holds no jobs (e.g. org metadata)
    jobs = spa_tier2._first_with_jobs(COMPANY, cfg, [{"data": {"org": 1}}, DATA])
    assert len(jobs) == 1

    import pytest
    with pytest.raises(RuntimeError):
        spa_tier2._first_with_jobs(COMPANY, cfg, [{"data": {"org": 1}}])
