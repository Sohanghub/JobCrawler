from jobcrawler.fetchers import workday


def posting(i):
    return {"title": f"Engineer {i}", "locationsText": "Chennai, India",
            "externalPath": f"/job/Chennai/Engineer_{i}",
            "postedOn": "Posted Today"}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


class SeqHttp:
    """Returns queued responses; records request bodies."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    def post(self, url, json=None, **kwargs):
        self.bodies.append(json)
        return FakeResponse(self.responses.pop(0))


CFG = {"name": "X", "workday": {"host": "x.wd5.myworkdayjobs.com", "site": "S"}}


def test_pagination():
    http = SeqHttp([
        {"total": 21, "jobPostings": [posting(i) for i in range(20)]},
        # real tenants report total=0 on pages after the first
        {"total": 0, "jobPostings": [posting(20)]},
    ])
    jobs = workday.fetch(CFG, http)
    assert len(jobs) == 21
    assert [b["offset"] for b in http.bodies] == [0, 20]
    assert jobs[0].url == ("https://x.wd5.myworkdayjobs.com/en-US/S"
                           "/job/Chennai/Engineer_0")
    assert jobs[0].location == "Chennai, India"
    assert len({j.id for j in jobs}) == 21  # ids unique


def test_max_jobs_cap():
    cfg = {"name": "X", "workday": {**CFG["workday"], "max_jobs": 20}}
    http = SeqHttp([{"total": 500, "jobPostings": [posting(i) for i in range(20)]}])
    jobs = workday.fetch(cfg, http)
    assert len(jobs) == 20
    assert len(http.bodies) == 1  # stopped at the cap, no second request
