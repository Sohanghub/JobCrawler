import hashlib
from dataclasses import dataclass


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


def make_id(company: str, native_id: str = "", url: str = "") -> str:
    """Stable dedup key: ATS-native job id when present, else the URL."""
    key = f"{company}:{native_id}" if native_id else url
    return hashlib.sha1(key.encode()).hexdigest()
