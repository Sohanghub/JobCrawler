import logging
import os

from . import html_tier1

log = logging.getLogger(__name__)
ZYTE_API = "https://api.zyte.com/v1/extract"

_used = 0  # per-run request counter, enforced against MAX_ZYTE_REQUESTS_PER_RUN


def fetch(company, http):
    """Tier 3: anti-bot sites, fetched through the Zyte API (browser-rendered
    HTML), then parsed with the same registry selectors as Tier 1.

    Only companies explicitly marked in the registry reach this fetcher, and a
    hard per-run request cap keeps Zyte spend bounded.
    """
    global _used
    cap = int(os.environ.get("MAX_ZYTE_REQUESTS_PER_RUN", "20"))
    if _used >= cap:
        raise RuntimeError(f"Zyte request cap reached ({cap}/run)")
    key = os.environ.get("ZYTE_API_KEY")
    if not key:
        raise RuntimeError("ZYTE_API_KEY not set")
    _used += 1
    r = http.post(ZYTE_API, auth=(key, ""),
                  json={"url": company["url"], "browserHtml": True},
                  timeout=120)
    r.raise_for_status()
    # ponytail: no detail-page hop in Zyte mode — each hop costs a paid request
    return html_tier1.parse_listing(company, r.json()["browserHtml"])
