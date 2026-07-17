"""Weekly discovery: find new candidate companies for the target role and
location, and queue them in config/candidates.yaml for the resolution agent.

Sources (all optional; whatever is configured runs, the rest is skipped):
  1. JSearch aggregator API (JSEARCH_API_KEY) — employer names for the target
     role/location.
  2. Targeted `site:` searches against ATS hosts via DuckDuckGo's HTML
     endpoint (key-free, best-effort — datacenter IPs may be blocked).
  3. Bulk board-token import: data/board_tokens.txt (one token or company
     name per line, e.g. from community Greenhouse/Lever token datasets).
     The cheapest route to "all companies": resolve's probe validates each
     against the public ATS APIs, and the location filter does the rest.

Run: python -m jobcrawler.discovery.search [--notify]
"""
import argparse
import logging
import os

import yaml

from .. import matching, notify, registry
from .resolve import CANDIDATES, PENDING, _http, _load, _save, norm_token

log = logging.getLogger(__name__)

TOKENS_FILE = "data/board_tokens.txt"
ATS_HOSTS = ("boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")
BOARD_URL = {"greenhouse": "https://boards.greenhouse.io/{}",
             "lever": "https://jobs.lever.co/{}",
             "ashby": "https://jobs.ashbyhq.com/{}"}


def jsearch_candidates(http, filters):
    key = os.environ.get("JSEARCH_API_KEY")
    if not key:
        log.info("JSEARCH_API_KEY not set; skipping JSearch")
        return []
    out = []
    # JSearch free tier is 200 requests/MONTH: 2 roles x 1 page x weekly run
    # ~= 9/month. Widen the slice only with that budget in mind.
    for role in filters["roles"][:2]:
        query = f"{role} in {filters['locations'][0]}"
        try:
            r = http.get("https://jsearch.p.rapidapi.com/search",
                         params={"query": query, "num_pages": "1"},
                         headers={"X-RapidAPI-Key": key,
                                  "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
            r.raise_for_status()
        except Exception as e:
            log.warning("JSearch query %r failed: %s", query, e)
            continue
        for item in r.json().get("data", []):
            name = item.get("employer_name")
            if name:
                out.append({"name": name,
                            "url": item.get("employer_website") or ""})
    return out


def extract_board_links(html):
    """Pull ATS board URLs (and thus candidates) out of arbitrary HTML."""
    from .resolve import ATS_URL_RES, NOT_TOKENS
    out, seen = [], set()
    for ats, rx in ATS_URL_RES:
        for token in rx.findall(html):
            token_l = token.lower()
            if token_l in NOT_TOKENS or token_l in seen:
                continue
            seen.add(token_l)
            out.append({"name": token, "url": BOARD_URL[ats].format(token)})
    return out


def site_search_candidates(http, filters):
    # ponytail: DuckDuckGo HTML scrape — flakiest source, wrapped best-effort;
    # the token-file import below is the reliable "find everything" mechanism
    out = []
    location = filters["locations"][0]
    for host in ATS_HOSTS:
        try:
            r = http.get("https://html.duckduckgo.com/html/",
                         params={"q": f"site:{host} {location}"}, timeout=30)
            r.raise_for_status()
            found = extract_board_links(r.text)
            log.info("site:%s search -> %d board link(s)", host, len(found))
            out += found
        except Exception as e:
            log.warning("site search failed for %s: %s", host, e)
    return out


def token_file_candidates(path=TOKENS_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
    except FileNotFoundError:
        return []
    # bare names/tokens, no URL: resolve's probe tries them against the
    # public Greenhouse/Lever/Ashby APIs
    return [{"name": ln, "url": ""} for ln in lines
            if ln and not ln.startswith("#")]


def dedup_candidates(found, known_names):
    known = {norm_token(n) for n in known_names}
    fresh = []
    for cand in found:
        key = norm_token(cand["name"])
        if key and key not in known:
            known.add(key)
            fresh.append(cand)
    return fresh


def run(do_notify=False):
    filters = matching.load_filters()
    http = _http()
    found = (jsearch_candidates(http, filters)
             + site_search_candidates(http, filters)
             + token_file_candidates())
    fresh = dedup_candidates(found, registry.known_names())
    if fresh:
        candidates = _load(CANDIDATES) + fresh
        _save(CANDIDATES, candidates)
    pending_count = len(_load(PENDING))
    summary = (f"Discovery: {len(fresh)} new candidate(s) queued "
               f"({len(found)} found before dedup); "
               f"{pending_count} entr(ies) awaiting your approval")
    log.info(summary)
    if do_notify:
        notify.send_text(summary)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    from ..main import load_env
    load_env()
    parser = argparse.ArgumentParser(prog="jobcrawler.discovery.search")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    run(do_notify=args.notify)


if __name__ == "__main__":
    main()
