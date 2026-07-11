import hashlib
import logging
import time
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter, Retry

log = logging.getLogger(__name__)
USER_AGENT = "JobCrawler/0.1 (personal job-search; contact: sohangandla20@gmail.com)"


class Unchanged(Exception):
    """Page identical to last run; parsing can be skipped."""


class Http:
    """Polite session: ~1 req/s per domain, retries with backoff, page cache."""

    def __init__(self, store=None, session=None, min_interval=1.0):
        self.store = store
        self.min_interval = min_interval
        self._last = {}  # domain -> monotonic time of last request
        if session is None:
            session = requests.Session()
            retry = Retry(total=3, backoff_factor=1,
                          status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=["GET", "POST"])
            session.mount("https://", HTTPAdapter(max_retries=retry))
            session.mount("http://", HTTPAdapter(max_retries=retry))
        session.headers.setdefault("User-Agent", USER_AGENT)
        self.session = session

    def _throttle(self, url):
        domain = urlsplit(url).netloc
        wait = self._last.get(domain, 0) + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[domain] = time.monotonic()

    def get(self, url, cache=False, **kwargs):
        """With cache=True: conditional request (ETag/Last-Modified) plus a
        body-hash comparison; raises Unchanged when the page didn't change.
        Fetchers opt in only on their FIRST request per company, so an
        Unchanged can never abort a multi-page crawl halfway through.
        """
        self._throttle(url)
        kwargs.setdefault("timeout", 30)
        headers = dict(kwargs.pop("headers", None) or {})
        cached = self.store.get_cache(url) if cache and self.store else None
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
            unchanged = bool(cached and cached["body_sha1"] == sha1)
            self.store.set_cache(url, r.headers.get("ETag"),
                                 r.headers.get("Last-Modified"), sha1)
            if unchanged:
                raise Unchanged(url)
        return r

    def post(self, url, **kwargs):
        self._throttle(url)
        kwargs.setdefault("timeout", 30)
        return self.session.post(url, **kwargs)
