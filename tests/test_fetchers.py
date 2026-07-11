from jobcrawler.fetchers import greenhouse, lever

GREENHOUSE_FIXTURE = {"jobs": [{
    "id": 4444,
    "title": "Backend Engineer",
    "location": {"name": "Bengaluru, India"},
    "absolute_url": "https://boards.greenhouse.io/x/jobs/4444",
    "content": "<p>Build things</p>",
    "updated_at": "2026-07-01T00:00:00Z",
}]}

LEVER_FIXTURE = [{
    "id": "abc-123",
    "text": "Software Engineer",
    "categories": {"location": "Remote"},
    "hostedUrl": "https://jobs.lever.co/x/abc-123",
    "descriptionPlain": "Build things",
    "createdAt": 1751328000000,
}]


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class FakeHttp:
    def __init__(self, data):
        self._data = data

    def get(self, url, **kwargs):
        return FakeResponse(self._data)


def test_greenhouse_parse():
    jobs = greenhouse.fetch({"name": "X", "token": "x"},
                            FakeHttp(GREENHOUSE_FIXTURE))
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.title, j.location, j.company) == ("Backend Engineer",
                                                "Bengaluru, India", "X")
    assert j.url == "https://boards.greenhouse.io/x/jobs/4444"
    assert j.id  # stable non-empty dedup key


def test_lever_parse():
    jobs = lever.fetch({"name": "Y", "token": "y"}, FakeHttp(LEVER_FIXTURE))
    assert len(jobs) == 1
    j = jobs[0]
    assert (j.title, j.location) == ("Software Engineer", "Remote")
    assert j.id


def test_same_job_same_id():
    a = greenhouse.fetch({"name": "X", "token": "x"},
                         FakeHttp(GREENHOUSE_FIXTURE))[0]
    b = greenhouse.fetch({"name": "X", "token": "x"},
                         FakeHttp(GREENHOUSE_FIXTURE))[0]
    assert a.id == b.id
