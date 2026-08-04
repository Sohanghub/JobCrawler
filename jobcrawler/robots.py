"""robots.txt gate, adapted from Firecrawl's lib/robots-txt.ts and
WebScraper/crawler.ts (importRobotsTxt / getRobotsCrawlDelay).

Firecrawl fetches a host's robots.txt once, caches it for a day, and answers
three questions from it: may I fetch this URL, how long must I wait between
requests, and which sitemaps did the site declare. Same three here, over
stdlib urllib.robotparser.

Every failure mode allows the fetch. That matches Firecrawl (a failed
robots.txt fetch yields empty content, which permits everything) and is the
right default for a crawler whose alternative is silently dropping a
company from the daily run because its CDN hiccuped.
"""
import logging
import re
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)

MAX_AGE = 24 * 60 * 60  # Firecrawl's ROBOTS_MAX_AGE
AGENT = "JobCrawler"    # the token sites would write in a User-agent line
MAX_BODY = 512 * 1024   # a robots.txt larger than this is not a robots.txt


def _pattern_re(pattern):
    """A robots.txt path pattern as a regex: '*' matches any run of
    characters, a trailing '$' anchors the end of the URL, the rest is
    literal. Google's spec, and what npm robots-parser implements for
    Firecrawl."""
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    body = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.compile(body + ("$" if anchored else ""))


def _url_path(url):
    """The part of a URL robots.txt rules are written against: path plus
    query, since patterns like `Disallow: /*?q=` target the query string."""
    parts = urlsplit(unquote(url))
    return urlunsplit(("", "", parts.path, parts.query, "")) or "/"


class Rules(RobotFileParser):
    """RobotFileParser with the matching semantics real robots.txt files
    are written against.

    stdlib compares rule paths with str.startswith against a percent-quoted
    path, so `Disallow: /search$` becomes the literal prefix `/search%24`
    and matches nothing, and `Disallow: /*?q=` likewise. It also takes the
    first matching line rather than the longest, so an `Allow:` can never
    carve an exception out of a broader `Disallow:`. GitHub's robots.txt
    alone trips all three.

    Overriding parse and can_fetch keeps what stdlib does get right —
    User-agent grouping, Crawl-delay, Sitemap — and replaces the two rules
    that decide whether a fetch is allowed.
    """

    def parse(self, lines):
        # RFC 9309: blank lines are ignored, and a group runs until the next
        # User-agent line. stdlib still follows the 1994 convention where a
        # blank line ends the record, so a file that puts one between
        # `User-agent: *` and its rules loses the whole wildcard group and
        # every rule under it — silently, and github.com is written that way.
        # Dropping blank lines leaves stdlib's other transition (a User-agent
        # line after rules starts a new group) to do the grouping, which is
        # what RFC 9309 asks for.
        super().parse([line for line in lines if line.strip()])

    def _entry_for(self, useragent):
        for entry in self.entries:
            if entry.applies_to(useragent):
                return entry
        return self.default_entry

    def can_fetch(self, useragent, url):
        entry = self._entry_for(useragent)
        if entry is None:
            return True
        path = _url_path(url)
        best, allowed = -1, True
        for line in entry.rulelines:
            # RuleLine.__init__ quoted the pattern on the way in, turning
            # '*' into %2A; undo that to get the author's pattern back
            pattern = unquote(line.path)
            if not _pattern_re(pattern).match(path):
                continue
            # longest pattern wins; on an exact tie Allow does
            if len(pattern) > best or (len(pattern) == best and line.allowance):
                best, allowed = len(pattern), line.allowance
        return allowed


class Robots:
    """Per-host robots.txt rules. One instance per run, shared by all hosts."""

    def __init__(self, fetch, store=None, agent=AGENT):
        """fetch(url) -> requests.Response, and must NOT itself be gated by
        robots (that would recurse). store, when given, persists bodies
        across runs so a daily crawl costs one robots.txt per host per day.
        """
        self.fetch = fetch
        self.store = store
        self.agent = agent
        self._parsers = {}  # host -> RobotFileParser

    def _body(self, scheme, host):
        if self.store:
            cached = self.store.get_robots(host, MAX_AGE)
            if cached is not None:
                return cached
        url = urlunsplit((scheme, host, "/robots.txt", "", ""))
        try:
            r = self.fetch(url)
            # 404 (no robots.txt) and 5xx alike mean "no rules we can honour"
            body = r.text[:MAX_BODY] if r.status_code == 200 else ""
        except Exception as e:
            log.debug("%s: robots.txt fetch failed (%s); allowing", host, e)
            body = ""
        if self.store:
            self.store.set_robots(host, body)
        return body

    def _parser(self, url):
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._parsers:
            parser = Rules()
            # same scheme as the request: an http-only host has no https
            # robots.txt to serve, and a failed fetch here allows everything
            parser.parse(self._body(parts.scheme or "https",
                                    host).splitlines())
            self._parsers[host] = parser
        return self._parsers[host]

    def allowed(self, url):
        try:
            return self._parser(url).can_fetch(self.agent, url)
        except Exception as e:  # a malformed robots.txt must not stop the run
            log.debug("robots.txt check failed for %s (%s); allowing", url, e)
            return True

    def crawl_delay(self, url):
        """Seconds the site asks us to wait between requests, or None.

        Firecrawl reads this too but has it commented out at the call site;
        here it becomes a floor on the existing per-domain throttle, which is
        the whole point of asking.
        """
        try:
            delay = self._parser(url).crawl_delay(self.agent)
        except Exception:
            return None
        try:
            return float(delay) if delay is not None else None
        except (TypeError, ValueError):
            return None

    def sitemaps(self, url):
        """Sitemap: URLs the host declares — free, authoritative seeds for
        discovery (Firecrawl's importRobotsTxt collects these the same way)."""
        try:
            return list(self._parser(url).site_maps() or [])
        except Exception:
            return []
