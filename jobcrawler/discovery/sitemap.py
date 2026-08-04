"""Find a company's careers page from its sitemaps.

Adapted from Firecrawl's WebScraper/crawler.ts (tryFetchSitemapLinks +
importRobotsTxt's getSitemaps) and crawler/sitemap.ts: read the Sitemap:
lines out of robots.txt, fall back to the conventional /sitemap.xml, recurse
through sitemap indexes with a visited-set and a hard cap, then filter.

This is the deterministic answer to a question resolve currently puts to a
DuckDuckGo HTML scrape and then to an LLM: "where does this company list its
jobs?" A homepage rarely matches detect_ats — the Greenhouse iframe lives on
/careers — so a JSearch candidate that only carries employer_website needs
one hop before it can be classified at all.
"""
import logging
import re
import zlib
from urllib.parse import urljoin, urlsplit

log = logging.getLogger(__name__)

# Firecrawl's SITEMAP_LIMIT equivalents: a sitemap index can fan out to
# thousands of files, and we want one careers URL, not the whole site.
MAX_SITEMAPS = 10
MAX_URLS = 20000
MAX_BODY = 10 * 1024 * 1024

CAREERS_RE = re.compile(
    r"career|/jobs?\b|job-openings|joinus|join-us|work-with-us|"
    r"opening|vacanc|opportunit", re.I)
# <loc> scraped with a regex rather than an XML parser: sitemaps come from
# unvetted hosts, and stdlib ElementTree has no defence against entity-
# expansion bombs. Firecrawl parses XML properly, in Rust, behind a service.
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
INDEX_RE = re.compile(r"<sitemapindex", re.I)


def _fetch(http, url):
    r = http.get(url)
    r.raise_for_status()
    if not url.lower().endswith(".gz"):
        return r.text[:MAX_BODY]
    if len(r.content) > MAX_BODY:
        raise ValueError(f"gzipped sitemap too large: {len(r.content)} bytes")
    # decompressobj with a max_length, not gzip.decompress: an unvetted host
    # can serve a few KB that inflate to gigabytes. wbits=31 is gzip framing.
    body = zlib.decompressobj(31).decompress(r.content, MAX_BODY)
    return body.decode("utf-8", "replace")


def seed_sitemaps(http, url):
    """Sitemap URLs to start from: whatever robots.txt declares, then the
    conventional /sitemap.xml. Deduped, robots.txt's own order preserved."""
    parts = urlsplit(url)
    root = f"{parts.scheme or 'https'}://{parts.netloc}"
    seeds = []
    robots = getattr(http, "robots", None)
    if robots is not None:
        seeds.extend(robots.sitemaps(root + "/"))
    seeds.append(root + "/sitemap.xml")
    seen, out = set(), []
    for s in seeds:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def collect_urls(http, url, max_sitemaps=MAX_SITEMAPS, max_urls=MAX_URLS):
    """Every page URL reachable from the site's sitemaps, breadth-first.

    A document containing <sitemapindex> holds sitemaps to recurse into;
    anything else holds pages. That is Firecrawl's recurse/process split,
    decided from the one marker a regex can see.
    """
    queue = seed_sitemaps(http, url)
    visited, urls = set(), []
    while queue and len(visited) < max_sitemaps and len(urls) < max_urls:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        try:
            body = _fetch(http, current)
        except Exception as e:
            log.debug("sitemap %s unavailable: %s", current, e)
            continue
        locs = LOC_RE.findall(body)
        if INDEX_RE.search(body):
            queue.extend(loc for loc in locs if loc not in visited)
        else:
            urls.extend(locs[:max_urls - len(urls)])
    return urls


def rank_careers_urls(urls, limit=5):
    """Careers-looking URLs, shallowest path first.

    Depth is the tiebreaker because the hub page ("/careers") is what carries
    the ATS embed; a single posting ("/careers/jobs/1234-backend-eng") does
    not, and there are hundreds of those.
    """
    hits = [u for u in urls if CAREERS_RE.search(urlsplit(u).path)]
    hits.sort(key=lambda u: (urlsplit(u).path.strip("/").count("/"), len(u)))
    out, seen = [], set()
    for u in hits:
        key = u.rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(u)
        if len(out) >= limit:
            break
    return out


def find_careers_urls(http, url, limit=5):
    """Best-guess careers pages for a company, given any URL on its site.

    Falls back to the conventional paths when the site has no usable sitemap,
    so a candidate is never worse off for having tried.
    """
    found = rank_careers_urls(collect_urls(http, url), limit)
    if found:
        return found
    parts = urlsplit(url)
    root = f"{parts.scheme or 'https'}://{parts.netloc}"
    return [urljoin(root, p) for p in ("/careers", "/careers/", "/jobs")][:limit]
