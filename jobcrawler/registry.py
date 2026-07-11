import logging

import yaml

log = logging.getLogger(__name__)


def load_companies(path="config/companies.yaml"):
    with open(path, encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []
    valid = []
    for e in entries:
        if not isinstance(e, dict) or not e.get("name") or not e.get("ats"):
            log.warning("skipping malformed registry entry: %r", e)
            continue
        valid.append(e)
    return valid


def append_company(entry, path="config/companies.yaml"):
    """Append an entry without rewriting the file (preserves comments)."""
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + block)


def known_names(paths=("config/pending_review.yaml", "config/candidates.yaml")):
    """Company names already in the registry, pending review, or queued as
    candidates — used by discovery to avoid re-proposing them."""
    names = {e["name"] for e in load_companies()}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                items = yaml.safe_load(f) or []
        except FileNotFoundError:
            continue
        names |= {i.get("name", "") for i in items if isinstance(i, dict)}
    names.discard("")
    return names
