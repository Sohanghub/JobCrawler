import hashlib
import logging
import time
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter, Retry

from .robots import Robots
from .urls import Blocked, validate_public_url

log = logging.getLogger(__name__)
USER_AGENT = "JobCrawler/0.1 (personal job-search; contact: sohangandla20@gmail.com)"

# Public, documented JSON APIs that registry entries name outright — not crawl
# surfaces, and exempt from the robots.txt gate. Firecrawl draws the same line:
# shouldCheckRobots() applies robots to crawls that discover their own URLs,
# not to fetching an endpoint the caller asked for by name.
ATS_API_HOSTS = ("boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com")
ATS_API_SUFFIXES = (".myworkdayjobs.com",)


class Unchanged(Exception):
    """Page identical to last run; parsing can be skipped."""


def is_ats_api(url):
    host = (urlsplit(url).hostname or "").lower()
    return host in ATS_API_HOSTS or host.endswith(ATS_API_SUFFIXES)


class Http:
    """Polite session: robots.txt-aware, ~1 req/s per domain, retries with
    backoff, page cache."""

    def __init__(self, store=None, session=None, min_interval=1.0,
                 check_robots=True, validate_urls=False):
        """check_robots gates every non-ATS-API request on the host's
        robots.txt and lets its Crawl-delay raise min_interval.

        validate_urls refuses non-http(s) schemes and private addresses
        before connecting. Off by default because the daily loop only visits
        URLs the user put in the registry; discovery turns it on, since its
        URLs come from search results, scraped pages, and an LLM.
        """
        self.store = store
        self.min_interval = min_interval
        self.validate_urls = validate_urls
        self._last = {}  # domain -> monotonic time of last request
        self._pending_cache = None  # cache row awaiting commit_cache()
        if session is None:
            session = requests.Session()
            retry = Retry(total=3, backoff_factor=1,
                          status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=["GET", "POST"])
            session.mount("https://", HTTPAdapter(max_retries=retry))
            session.mount("http://", HTTPAdapter(max_retries=retry))
        session.headers.setdefault("User-Agent", USER_AGENT)
        self.session = session
        self.robots = Robots(self._raw_get, store) if check_robots else None

    def _throttle(self, url, delay=None):
        domain = urlsplit(url).netloc
        interval = max(self.min_interval, delay or 0)
        wait = self._last.get(domain, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[domain] = time.monotonic()

    def _raw_get(self, url):
        """Throttled fetch that skips the gate — for robots.txt itself, which
        cannot be gated on the file it is about to fetch."""
        self._throttle(url)
        return self.session.get(url, timeout=15)

    def _gate(self, url, robots=True):
        """Refuse the request or return the Crawl-delay to throttle by.
        Raises Blocked; the caller decides whether that ends the company's
        run or just skips one page.

        robots=False is for endpoints we are a first-party API client of
        (OpenRouter, JSearch) rather than a crawler on. URL validation is not
        skippable — it costs one cached DNS lookup and those hosts are
        hardcoded, so it can only ever fire on a genuine surprise.
        """
        if self.validate_urls:
            validate_public_url(url)
        if not robots or self.robots is None or is_ats_api(url):
            return None
        if not self.robots.allowed(url):
            raise Blocked(f"robots.txt disallows {url}")
        return self.robots.crawl_delay(url)

    def get(self, url, cache=False, robots=True, **kwargs):
        """With cache=True: conditional request (ETag/Last-Modified) plus a
        body-hash comparison; raises Unchanged when the page didn't change.
        Fetchers opt in only on their FIRST request per company, so an
        Unchanged can never abort a multi-page crawl halfway through.

        The cache row is NOT written here — it is staged and persisted only
        by commit_cache(), after the page parsed successfully. Otherwise a
        parser crash would freeze a broken page as "unchanged" forever.
        """
        delay = self._gate(url, robots)
        self._throttle(url, delay)
        kwargs.setdefault("timeout", 30)
        headers = dict(kwargs.pop("headers", None) or {})
        cached = self.store.get_cache(url) if cache and self.store else None
        if cache:
            self._pending_cache = None
        if cached and cached["etag"]:
            headers["If-None-Match"] = cached["etag"]
        if cached and cached["last_modified"]:
            headers["If-Modified-Since"] = cached["last_modified"]
        r = self.session.get(url, headers=headers, **kwargs)
        if cache and self.store:
            if r.status_code == 304:
                raise Unchanged(url)
            r.raise_for_status()
            sha1 = hashlib.sha1(r.content).hexdigest()
            self._pending_cache = (url, r.headers.get("ETag"),
                                   r.headers.get("Last-Modified"), sha1)
            if cached and cached["body_sha1"] == sha1:
                raise Unchanged(url)
        return r

    def commit_cache(self):
        """Persist the staged cache row from the last cached get(). Call
        after a successful parse (or on Unchanged, whose refreshed
        ETag/Last-Modified is safe because the prior parse was good)."""
        if self._pending_cache and self.store:
            self.store.set_cache(*self._pending_cache)
            self._pending_cache = None

    def post(self, url, robots=True, **kwargs):
        delay = self._gate(url, robots)
        self._throttle(url, delay)
        kwargs.setdefault("timeout", 30)
        return self.session.post(url, **kwargs)
