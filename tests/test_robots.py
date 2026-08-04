import pytest

from jobcrawler.http import Http
from jobcrawler.robots import Robots
from jobcrawler.store import Store
from jobcrawler.urls import Blocked

ROBOTS = """
User-agent: *
Disallow: /private/
Crawl-delay: 4

User-agent: JobCrawler
Disallow: /nope/

Sitemap: https://x.example/sitemap.xml
Sitemap: https://x.example/sitemap-jobs.xml
"""


class FakeResponse:
    def __init__(self, text="", status_code=200, content=b""):
        self.text = text
        self.status_code = status_code
        self.content = content or text.encode()
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fetcher(body, status=200, calls=None):
    def fetch(url):
        if calls is not None:
            calls.append(url)
        return FakeResponse(body, status)
    return fetch


def test_allow_disallow_and_agent_specific_rules():
    robots = Robots(fetcher(ROBOTS))
    assert robots.allowed("https://x.example/careers")
    assert not robots.allowed("https://x.example/nope/x")
    # our own User-agent group wins outright, so the wildcard's /private/
    # rule does not apply to us
    assert robots.allowed("https://x.example/private/x")


def test_crawl_delay_and_sitemaps():
    robots = Robots(fetcher(ROBOTS))
    # Crawl-delay sits in the wildcard group, which JobCrawler's own group
    # overrides -- so there is no delay for us here
    assert robots.crawl_delay("https://x.example/") is None
    assert robots.sitemaps("https://x.example/") == [
        "https://x.example/sitemap.xml", "https://x.example/sitemap-jobs.xml"]


# The three things stdlib's RobotFileParser gets wrong, all lifted from
# robots.txt files in the wild (github.com has every one of them).
WILDCARDS = """
User-agent: *
Disallow: /search$
Disallow: /*?q=
Disallow: /*.atom$
"""


@pytest.mark.parametrize("path,allowed", [
    ("/search", False),            # trailing $ anchors: exact match blocked
    ("/searching", True),          # ...and only the exact one
    ("/a?q=hello", False),         # * spans, and the query is matched too
    ("/a?page=2", True),
    ("/feed.atom", False),
    ("/feed.atom?x=1", True),      # $ is end of URL, and the query is part of it
])
def test_wildcards_and_anchors(path, allowed):
    assert Robots(fetcher(WILDCARDS)).allowed("https://x.example" + path) \
        is allowed


PRECEDENCE = """
User-agent: *
Disallow: /private/
Allow: /private/public
Disallow: /
Allow: /jobs/
"""


@pytest.mark.parametrize("path,allowed", [
    ("/private/x", False),
    ("/private/public", True),     # longer Allow beats shorter Disallow
    ("/jobs/backend", True),       # Allow carves an exception out of "/"
    ("/anything-else", False),     # ...and the blanket Disallow still holds
])
def test_longest_match_wins(path, allowed):
    assert Robots(fetcher(PRECEDENCE)).allowed("https://x.example" + path) \
        is allowed


# github.com's shape: named groups first, then a wildcard group whose rules
# sit behind a blank line. stdlib drops that entire group and crawls freely.
BLANK_LINE_GROUPS = """
User-agent: bingbot
Disallow: /bing-only

User-agent: *

Disallow: /search
Disallow: /copilot/
"""


@pytest.mark.parametrize("path,allowed", [
    ("/search", False),
    ("/copilot/c", False),
    ("/features", True),
    ("/bing-only", True),   # another agent's group is not ours
])
def test_blank_line_inside_a_group(path, allowed):
    assert Robots(fetcher(BLANK_LINE_GROUPS)).allowed(
        "https://x.example" + path) is allowed


def test_wildcard_crawl_delay_applies():
    robots = Robots(fetcher("User-agent: *\nCrawl-delay: 7\n"))
    assert robots.crawl_delay("https://x.example/") == 7


def test_fetched_once_per_host():
    calls = []
    robots = Robots(fetcher(ROBOTS, calls=calls))
    for path in ("/a", "/b", "/c"):
        robots.allowed("https://x.example" + path)
    robots.allowed("https://y.example/a")
    assert calls == ["https://x.example/robots.txt",
                     "https://y.example/robots.txt"]


@pytest.mark.parametrize("fetch", [
    fetcher("", 404),                                  # no robots.txt
    fetcher("", 503),                                  # host having a bad day
    lambda url: (_ for _ in ()).throw(OSError("boom")),  # connection refused
])
def test_failures_allow(fetch):
    assert Robots(fetch).allowed("https://x.example/anything")


def test_store_caches_across_instances(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    calls = []
    Robots(fetcher(ROBOTS, calls=calls), store).allowed("https://x.example/a")
    # a fresh Robots (i.e. tomorrow's run) reads the stored body
    assert not Robots(fetcher("", 404), store).allowed("https://x.example/nope/x")
    assert calls == ["https://x.example/robots.txt"]


class FakeSession:
    """Serves robots.txt for every host; records ordinary page fetches."""

    def __init__(self, robots_body=ROBOTS):
        self.headers = {}
        self.robots_body = robots_body
        self.fetched = []

    def get(self, url, headers=None, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse(self.robots_body)
        self.fetched.append(url)
        return FakeResponse("<html>page</html>")

    def post(self, url, **kwargs):
        self.fetched.append(url)
        return FakeResponse("{}")


def make_http(**kw):
    kw.setdefault("min_interval", 0)
    return Http(session=FakeSession(), **kw)


def test_http_blocks_disallowed_page():
    http = make_http()
    assert http.get("https://x.example/careers").text == "<html>page</html>"
    with pytest.raises(Blocked):
        http.get("https://x.example/nope/jobs")
    assert http.session.fetched == ["https://x.example/careers"]


def test_http_blocks_post_too():
    http = make_http()
    with pytest.raises(Blocked):
        http.post("https://x.example/nope/api", json={})


def test_ats_apis_are_never_robots_gated():
    http = make_http()
    # this robots.txt disallows /nope/, but ATS APIs skip the gate entirely
    http.get("https://api.lever.co/nope/v0/postings/x")
    assert http.session.fetched == ["https://api.lever.co/nope/v0/postings/x"]
    # and no robots.txt was fetched for that host at all
    assert "api.lever.co" not in http.robots._parsers


def test_per_call_robots_opt_out():
    http = make_http()
    http.get("https://x.example/nope/api", robots=False)
    assert http.session.fetched == ["https://x.example/nope/api"]


def test_check_robots_false_disables_the_gate():
    http = make_http(check_robots=False)
    http.get("https://x.example/nope/jobs")
    assert http.robots is None


def test_crawl_delay_raises_the_throttle(monkeypatch):
    slept = []
    monkeypatch.setattr("jobcrawler.http.time.sleep", slept.append)
    http = Http(session=FakeSession("User-agent: *\nCrawl-delay: 5\n"),
                min_interval=1)
    http.get("https://x.example/a")
    http.get("https://x.example/b")
    assert max(slept) > 1  # waited out the site's 5s, not our 1s
