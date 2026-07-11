from jobcrawler.fetchers import html_tier1

LISTING = """
<ol class="jobs">
  <li><h2><a class="t" href="/jobs/1/">Backend Engineer</a></h2>
      <span class="loc">Bengaluru, India</span></li>
  <li><h2><a class="t" href="/jobs/2/">Data Engineer</a></h2>
      <span class="loc">Remote</span></li>
  <li><h2><a class="t" href="/jobs/3/">Designer</a></h2>
      <span class="loc">Pune</span></li>
</ol>
"""

DETAIL = '<div class="desc">Requires 1-2 years of Python.</div>'

COMPANY = {
    "name": "X",
    "url": "https://x.example/careers/",
    "detail_limit": 2,
    "selectors": {
        "job_item": "ol.jobs li",
        "title": "a.t",
        "link": "a.t",
        "location": ".loc",
        "detail": {"description": ".desc"},
    },
}


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeHttp:
    def __init__(self):
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(LISTING if url.endswith("/careers/") else DETAIL)


def test_listing_and_bounded_detail_hop():
    http = FakeHttp()
    jobs = html_tier1.fetch(COMPANY, http)
    assert [(j.title, j.location) for j in jobs] == [
        ("Backend Engineer", "Bengaluru, India"),
        ("Data Engineer", "Remote"),
        ("Designer", "Pune"),
    ]
    assert jobs[0].url == "https://x.example/jobs/1/"  # relative link resolved
    # detail hop bounded by detail_limit=2: only first two got descriptions
    assert jobs[0].description.startswith("Requires 1-2 years")
    assert jobs[1].description
    assert jobs[2].description == ""
    assert len(http.urls) == 3  # 1 listing + 2 details
    assert len({j.id for j in jobs}) == 3
