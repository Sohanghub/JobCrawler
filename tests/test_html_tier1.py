import copy

from jobcrawler.fetchers import html_tier1
from jobcrawler.urls import Blocked

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


def test_no_detail_block_means_no_detail_hop():
    company = copy.deepcopy(COMPANY)
    del company["selectors"]["detail"]
    http = FakeHttp()
    jobs = html_tier1.fetch(company, http)
    assert len(http.urls) == 1
    assert all(j.description == "" for j in jobs)


DETAIL_PAGE = """
<html><body><nav>Home</nav>
  <main><h1>Backend Engineer</h1><p>Wants 1-2 years of Python.</p></main>
  <footer>Cookie notice</footer></body></html>
"""


def test_detail_without_a_description_selector_uses_clean_text():
    # `detail: {}` is enough now: the page's own text stands in, which is what
    # matching.experience_ok reads for "N years"
    company = copy.deepcopy(COMPANY)
    company["selectors"]["detail"] = {}

    class Http:
        def get(self, url, **kwargs):
            return FakeResponse(LISTING if url.endswith("/careers/")
                                else DETAIL_PAGE)

    jobs = html_tier1.fetch(company, Http())
    assert "Wants 1-2 years of Python." in jobs[0].description
    assert "Cookie notice" not in jobs[0].description


def test_binary_links_are_not_fetched():
    class BinaryListing(FakeHttp):
        def get(self, url, **kwargs):
            self.urls.append(url)
            body = LISTING.replace('href="/jobs/2/"', 'href="/jobs/2.pdf"')
            return FakeResponse(body if url.endswith("/careers/") else DETAIL)

    http = BinaryListing()
    html_tier1.fetch(COMPANY, http)
    assert http.urls == ["https://x.example/careers/", "https://x.example/jobs/1/"]


def test_blocked_detail_page_skips_only_that_page():
    class PartlyBlocked(FakeHttp):
        def get(self, url, **kwargs):
            self.urls.append(url)
            if url.endswith("/jobs/1/"):
                raise Blocked("robots.txt disallows " + url)
            return FakeResponse(LISTING if url.endswith("/careers/") else DETAIL)

    http = PartlyBlocked()
    jobs = html_tier1.fetch(COMPANY, http)
    assert jobs[0].description == ""      # blocked
    assert jobs[1].description            # the rest still ran
    assert len(jobs) == 3
