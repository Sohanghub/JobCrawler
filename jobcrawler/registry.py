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
