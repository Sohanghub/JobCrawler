"""Readable text out of an arbitrary HTML page.

Adapted from Firecrawl's scrapeURL/lib/removeUnwantedElements.ts: drop the
chrome (nav, header, footer, cookie banners, share widgets, scripts) and keep
what is left. Firecrawl then renders markdown; a job description only needs
plain text, so this stops one step earlier.

Why it matters here: matching.experience_ok reads job.description for "N+
years" phrases, and Tier 1 only captures a description when the registry
happens to carry a detail.description selector. Without one, every posting on
the site looks experience-neutral and passes the filter.
"""
import re

from bs4 import BeautifulSoup

# Firecrawl's excludeNonMainTags, trimmed to what appears on career pages.
BOILERPLATE_TAGS = ("script", "style", "noscript", "template", "svg",
                    "header", "footer", "nav", "aside", "form", "iframe")
BOILERPLATE_SELECTORS = (
    ".header", "#header", ".footer", "#footer", ".nav", "#nav", ".navbar",
    ".navigation", ".menu", ".sidebar", "#sidebar", ".side", ".aside",
    ".breadcrumbs", "#breadcrumbs", ".modal", ".popup", "#modal", ".overlay",
    ".ad", ".ads", ".advert", "#ad", ".cookie", "#cookie",
    ".social", ".social-media", ".social-links", "#social",
    ".share", "#share", ".widget", "#widget",
    ".lang-selector", ".language", "#language-selector",
)
# Firecrawl's forceIncludeMainTags equivalent: if one of these is present it is
# the posting, and everything outside it is chrome by definition.
MAIN_SELECTORS = ("main", "article", "[role=main]", "#main", "#content",
                  ".job-description", ".posting", "[itemprop=description]")

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")


def clean_text(html, limit=8000):
    """Strip boilerplate from an HTML page and return its text.

    Returns "" rather than raising on unparseable input — a missing
    description costs one imperfect filter decision, a raised exception costs
    the whole company's run.
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return ""
    for el in soup.select(",".join(BOILERPLATE_TAGS + BOILERPLATE_SELECTORS)):
        # select() yields document order, so an ancestor can take a later
        # match down with it; decomposing that corpse again would raise
        if not getattr(el, "_decomposed", False):
            el.decompose()
    root = soup
    for sel in MAIN_SELECTORS:
        node = soup.select_one(sel)
        if node:
            root = node
            break
    text = root.get_text("\n", strip=True)
    text = _BLANK_RE.sub("\n\n", _WS_RE.sub(" ", text))
    return text.strip()[:limit]
