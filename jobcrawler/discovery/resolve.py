"""Resolution agent: turn candidate companies into validated registry entries.

Pipeline (cheap deterministic checks first, LLM only for the leftovers, human
approval before anything reaches the live registry):

  python -m jobcrawler.discovery.resolve probe
      Deterministic ATS detection for config/candidates.yaml: recognize
      Greenhouse/Lever/Ashby/Workday from the careers URL or page HTML, and
      probe name-derived board tokens against the public ATS APIs. Anything
      that live-validates moves to config/pending_review.yaml.

  python -m jobcrawler.discovery.resolve infer
      Submit the still-unresolved candidates (with a careers URL) to Claude
      via the Message Batches API (50% off, off the daily path): classify the
      ATS or propose Tier 1 selectors / a Tier 2 XHR endpoint from the page
      HTML. Prints the batch id.

  python -m jobcrawler.discovery.resolve collect [batch_id]
      Fetch a finished batch's results into pending_review.yaml.

  python -m jobcrawler.discovery.resolve approve [name ...]
      Live-validate pending entries (must parse >=1 job) and merge the
      successes into config/companies.yaml; failures stay pending with the
      error attached. No names = try all pending.
"""
import argparse
import json
import logging
import re
import sys

import yaml

from .. import registry
from ..fetchers import FETCHERS
from ..http import Http

log = logging.getLogger(__name__)

CANDIDATES = "config/candidates.yaml"
PENDING = "config/pending_review.yaml"
LAST_BATCH = "data/last_batch_id.txt"
RESOLVE_MODEL = "claude-opus-4-8"
HTML_LIMIT = 40000  # chars of page HTML sent to the model

WORKDAY_RE = re.compile(
    r"https?://([a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)"
    r"/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")
ATS_URL_RES = [
    ("greenhouse",
     re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)")),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([A-Za-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)")),
]
NOT_TOKENS = {"embed", "job_board", "jobs", "js", "css", "img"}


def norm_token(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def detect_ats(text):
    """Recognize a known ATS from a URL or page HTML.

    Returns ("workday", (host, site)) or (ats, token), or None.
    """
    m = WORKDAY_RE.search(text)
    if m:
        return "workday", (m.group(1), m.group(2))
    for ats, rx in ATS_URL_RES:
        for token in rx.findall(text):
            if token.lower() not in NOT_TOKENS:
                return ats, token
    return None


def build_entry(name, ats, cfg):
    if ats == "workday":
        host, site = cfg
        return {"name": name, "tier": 0, "ats": "workday",
                "workday": {"host": host, "site": site}}
    return {"name": name, "tier": 0, "ats": ats, "token": cfg}


def validate_entry(entry, http):
    """Live-fetch an entry; the approval gate requires >=1 parsed job."""
    jobs = FETCHERS[entry["ats"]](entry, http)
    return jobs


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or []
    except FileNotFoundError:
        return []


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _evidence(jobs):
    sample = "; ".join(j.title for j in jobs[:3])
    return f"{len(jobs)} jobs live; sample: {sample}"


def resolve_deterministic(cand, http):
    """URL/HTML pattern match, else name-derived token probes. Returns a
    live-validated (entry, evidence) or (None, None)."""
    url = cand.get("url") or ""
    hit = detect_ats(url) if url else None
    if not hit and url:
        try:
            hit = detect_ats(http.get(url).text)
        except Exception as e:
            log.warning("%s: could not fetch %s: %s", cand["name"], url, e)
    if hit:
        tries = [hit]
    else:
        token = norm_token(cand["name"])
        tries = [("greenhouse", token), ("lever", token), ("ashby", token)]
    for ats, cfg in tries:
        entry = build_entry(cand["name"], ats, cfg)
        try:
            jobs = validate_entry(entry, http)
        except Exception:
            continue
        if jobs:
            return entry, _evidence(jobs)
    return None, None


def _http():
    # No store: discovery must never write the page cache, or the daily
    # loop's first fetch of a just-approved company would see "unchanged"
    # and silently ingest nothing.
    return Http()


def cmd_probe(args):
    http = _http()
    candidates = _load(CANDIDATES)
    pending = _load(PENDING)
    resolved = 0
    for cand in list(candidates):
        entry, evidence = resolve_deterministic(cand, http)
        if entry:
            pending.append({"name": cand["name"], "entry": entry,
                            "evidence": evidence, "source": "probe"})
            candidates.remove(cand)
            resolved += 1
            log.info("%s: resolved -> %s (%s)", cand["name"], entry["ats"],
                     evidence)
        else:
            log.info("%s: unresolved (candidate for LLM inference)",
                     cand["name"])
    _save(CANDIDATES, candidates)
    _save(PENDING, pending)
    summary = (f"Discovery probe: {resolved} resolved -> pending review "
               f"({len(pending)} total pending), {len(candidates)} unresolved")
    log.info(summary)
    if args.notify:
        from .. import notify
        notify.send_text(summary)


SCHEMA = {
    "type": "object",
    "properties": {
        "ats": {"type": "string",
                "enum": ["greenhouse", "lever", "ashby", "workday",
                         "custom_html", "custom_spa", "unknown"]},
        "token": {"type": "string"},
        "workday_host": {"type": "string"},
        "workday_site": {"type": "string"},
        "selectors": {
            "type": "object",
            "properties": {"job_item": {"type": "string"},
                           "title": {"type": "string"},
                           "location": {"type": "string"},
                           "link": {"type": "string"}},
            "required": ["job_item", "title", "location", "link"],
            "additionalProperties": False},
        "xhr_url": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["ats", "notes"],
    "additionalProperties": False,
}

PROMPT = """You are classifying a company careers page for a job-scraping \
registry. Company: {name}. Careers URL: {url}.

Decide how its job postings can be fetched:
- If it embeds or links a known ATS, return ats=greenhouse/lever/ashby with \
the board token, or ats=workday with workday_host (the *.myworkdayjobs.com \
host) and workday_site (the site path segment).
- If jobs are present in this server-rendered HTML, return ats=custom_html \
with CSS selectors: job_item (one per posting), and title/location/link \
selectors relative to job_item.
- If the page is a JS shell that loads jobs via XHR, return ats=custom_spa \
and, if the HTML reveals it, the JSON endpoint as xhr_url.
- Otherwise ats=unknown.

Explain your reasoning briefly in notes.

Page HTML (truncated):
{html}"""


def cmd_infer(args):
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    http = _http()
    candidates = [c for c in _load(CANDIDATES) if c.get("url")]
    if not candidates:
        log.info("no unresolved candidates with a careers URL")
        return
    requests_ = []
    for cand in candidates:
        try:
            page = http.get(cand["url"]).text[:HTML_LIMIT]
        except Exception as e:
            log.warning("%s: could not fetch %s: %s", cand["name"],
                        cand["url"], e)
            continue
        custom_id = re.sub(r"[^A-Za-z0-9_-]", "-", cand["name"])[:64]
        requests_.append(Request(
            custom_id=custom_id,
            params=MessageCreateParamsNonStreaming(
                model=RESOLVE_MODEL,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema",
                                          "schema": SCHEMA}},
                messages=[{"role": "user", "content": PROMPT.format(
                    name=cand["name"], url=cand["url"], html=page)}],
            )))
    if not requests_:
        log.info("nothing to submit")
        return
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=requests_)
    with open(LAST_BATCH, "w", encoding="utf-8") as f:
        f.write(batch.id)
    log.info("submitted batch %s with %d request(s); run "
             "'resolve collect' once it ends (usually <1h)",
             batch.id, len(requests_))


def _entry_from_llm(cand, data):
    name, url = cand["name"], cand.get("url", "")
    ats = data["ats"]
    if ats in ("greenhouse", "lever", "ashby") and data.get("token"):
        return build_entry(name, ats, data["token"])
    if ats == "workday" and data.get("workday_host") and data.get("workday_site"):
        return build_entry(name, "workday",
                           (data["workday_host"], data["workday_site"]))
    if ats == "custom_html" and data.get("selectors"):
        return {"name": name, "tier": 1, "ats": "html", "url": url,
                "selectors": data["selectors"]}
    if ats == "custom_spa" and data.get("xhr_url"):
        # fields/jobs_path need a human look at the JSON before approval
        return {"name": name, "tier": 2, "ats": "spa",
                "xhr": {"url": data["xhr_url"], "jobs_path": "",
                        "fields": {"title": "title", "location": "location",
                                   "url": "url", "id": "id"}}}
    return None


def cmd_collect(args):
    import anthropic

    batch_id = args.batch_id
    if not batch_id:
        try:
            with open(LAST_BATCH, encoding="utf-8") as f:
                batch_id = f.read().strip()
        except FileNotFoundError:
            sys.exit("no batch id given and no data/last_batch_id.txt")
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        log.info("batch %s still %s (%s processing) — try again later",
                 batch_id, batch.processing_status,
                 batch.request_counts.processing)
        return
    candidates = _load(CANDIDATES)
    by_custom_id = {re.sub(r"[^A-Za-z0-9_-]", "-", c["name"])[:64]: c
                    for c in candidates}
    pending = _load(PENDING)
    added = 0
    for result in client.messages.batches.results(batch_id):
        cand = by_custom_id.get(result.custom_id)
        if result.result.type != "succeeded" or cand is None:
            log.warning("%s: batch result %s", result.custom_id,
                        result.result.type)
            continue
        msg = result.result.message
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("%s: unparseable model output", result.custom_id)
            continue
        entry = _entry_from_llm(cand, data)
        if entry is None:
            log.info("%s: model says %s (%s)", cand["name"], data.get("ats"),
                     data.get("notes", "")[:200])
            continue
        pending.append({"name": cand["name"], "entry": entry,
                        "evidence": f"LLM: {data.get('notes', '')[:300]}",
                        "source": "llm"})
        candidates.remove(cand)
        added += 1
    _save(CANDIDATES, candidates)
    _save(PENDING, pending)
    log.info("collected %d proposal(s) into %s — review, then run "
             "'resolve approve'", added, PENDING)


def cmd_approve(args):
    http = _http()
    pending = _load(PENDING)
    names = set(args.names)
    merged = 0
    for item in list(pending):
        if names and item["name"] not in names:
            continue
        entry = item["entry"]
        try:
            jobs = validate_entry(entry, http)
            if not jobs:
                raise RuntimeError("validation fetch parsed 0 jobs")
        except Exception as e:
            item["error"] = str(e)
            log.warning("%s: NOT merged — %s", item["name"], e)
            continue
        registry.append_company(entry)
        pending.remove(item)
        merged += 1
        log.info("%s: merged into companies.yaml (%s)", item["name"],
                 _evidence(jobs))
    _save(PENDING, pending)
    log.info("approved %d entr(ies); %d still pending", merged, len(pending))


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    from ..main import load_env
    load_env()
    parser = argparse.ArgumentParser(prog="jobcrawler.discovery.resolve")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--notify", action="store_true")
    p.set_defaults(func=cmd_probe)
    p = sub.add_parser("infer")
    p.set_defaults(func=cmd_infer)
    p = sub.add_parser("collect")
    p.add_argument("batch_id", nargs="?")
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser("approve")
    p.add_argument("names", nargs="*")
    p.set_defaults(func=cmd_approve)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
