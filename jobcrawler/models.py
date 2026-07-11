import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "gh_")


@dataclass
class JobPosting:
    id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    posted_at: str = ""
    source_tier: int = 0


def canonical_url(url: str) -> str:
    """Strip tracking params and fragment so the same job dedups."""
    parts = urlsplit(url)
    query = "&".join(p for p in parts.query.split("&")
                     if p and not p.startswith(TRACKING_PREFIXES))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path, query, ""))


def make_id(company: str, native_id: str = "", url: str = "",
            title: str = "", location: str = "") -> str:
    """Stable dedup key: ATS-native id, else canonical URL, else content hash."""
    if native_id:
        key = f"{company}:{native_id}"
    elif url:
        key = canonical_url(url)
    else:
        key = f"{company}|{title}|{location}"
    return hashlib.sha1(key.encode()).hexdigest()
