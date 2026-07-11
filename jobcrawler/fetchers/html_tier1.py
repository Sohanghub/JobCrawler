import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import JobPosting, make_id

log = logging.getLogger(__name__)


def _text(el, selector):
    node = el.select_one(selector) if selector else None
    return node.get_text(strip=True) if node else ""


def fetch(company, http):
    """Tier 1: server-rendered HTML, selectors from the registry.

    Bounded 2-hop crawl: the listing page, then (optionally) up to
    detail_limit detail pages linked from it.
    """
    sel = company["selectors"]
    r = http.get(company["url"], cache=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    jobs = []
    for item in soup.select(sel["job_item"]):
        link = item.select_one(sel.get("link", "a"))
        url = (urljoin(company["url"], link["href"])
               if link and link.has_attr("href") else "")
        title = _text(item, sel.get("title")) or (
            link.get_text(strip=True) if link else "")
        location = _text(item, sel.get("location"))
        if not title:
            continue
        jobs.append(JobPosting(
            id=make_id(company["name"], url=url, title=title,
                       location=location),
            company=company["name"], title=title, location=location,
            url=url, source_tier=1))

    detail = sel.get("detail")
    if detail and detail.get("description"):
        for j in jobs[:company.get("detail_limit", 20)]:
            if not j.url:
                continue
            try:
                d = http.get(j.url)
                d.raise_for_status()
                j.description = _text(BeautifulSoup(d.text, "lxml"),
                                      detail["description"])[:2000]
            except Exception as e:
                log.warning("%s: detail fetch failed for %s: %s",
                            company["name"], j.url, e)
    return jobs
