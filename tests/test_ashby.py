from jobcrawler.fetchers import ashby

FIXTURE = {"jobs": [{
    "id": "uuid-1",
    "title": "Product Engineer",
    "location": "Remote - India",
    "jobUrl": "https://jobs.ashbyhq.com/x/uuid-1",
    "descriptionPlain": "Build things",
    "publishedAt": "2026-07-01T00:00:00Z",
}]}


class FakeResponse:
    def json(self):
        return FIXTURE

    def raise_for_status(self):
        pass


class FakeHttp:
    def get(self, url, **kwargs):
        assert "posting-api/job-board/x" in url
        return FakeResponse()


def test_ashby_parse():
    jobs = ashby.fetch({"name": "X", "token": "x"}, FakeHttp())
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.title, j.location) == ("Product Engineer", "Remote - India")
    assert j.id and j.source_tier == 0
