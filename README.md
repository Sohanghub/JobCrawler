# JobCrawler

Self-hosted daily job-finder. Scrapes fresh postings directly from company
career sites via a tiered, registry-driven fetcher system, dedups in SQLite,
and notifies via Telegram. Runs free on GitHub Actions.

## Setup

1. `pip install -r requirements.txt`
2. **Edit `config/filters.yaml`** — role keywords, locations (placeholders shipped).
3. Telegram: create a bot with [@BotFather](https://t.me/BotFather), grab the
   token; message the bot once, then get your chat ID from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. Locally: put both in `.env` (gitignored):
   ```
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   ```
   On GitHub: add the same two names as Actions repo secrets.

## Run

```
python -m jobcrawler.main
```

First run seeds the DB silently (no notification storm). Later runs notify
only never-seen-before postings that match your filters. Without Telegram
env vars the digest prints to stdout.

The crawler honours each site's `robots.txt` (fetched once per host per day,
cached in `data/jobs.db`) and any `Crawl-delay` it declares, which raises the
default 1 req/s floor. Public ATS JSON APIs — Greenhouse, Lever, Ashby,
Workday — are exempt: those are endpoints the registry names outright, not
pages we discover by crawling. A company whose `robots.txt` closes the door
is logged as `blocked` rather than `error`, so it never looks like a broken
parser; if it used to work, the digest says so. `Http(check_robots=False)`
turns the gate off entirely.

Web UI (browse the DB): `cd webui && npm install && npm run build`, then
`python webui/server.py` → http://localhost:8765. For UI development,
`npm run dev` in `webui/` proxies `/api` to that server.

CI: `.github/workflows/daily.yml` runs daily at 08:00 IST and commits
`data/jobs.db` back to the repo (that's how dedup state survives stateless
runners).

## Adding a company

One YAML entry in `config/companies.yaml` — no code:

```yaml
- name: Example
  tier: 0
  ats: greenhouse   # or lever / ashby / workday
  token: example    # board token from the company's careers URL
```

Tier 1 (server-rendered HTML) adds `url` + `selectors:`; Tier 2 (SPA) adds
`xhr:` — the site's own JSON endpoint, replayed over plain HTTP.

Tier 1 can also follow each posting to its own page. Add `detail: {}` inside
`selectors:` and the page's text is extracted with the boilerplate (nav,
footer, cookie banners, share widgets) stripped out — enough for the
experience filter to read "3+ years" off a description without you finding a
CSS selector for it. Add `detail: {description: "..."}` when you have one and
want it exact. `detail_limit` (default 20) bounds the hop.

## Growing the registry (discovery loop)

```
python -m jobcrawler.discovery.search            # find candidates (JSearch /
                                                 #  site: search / data/board_tokens.txt)
python -m jobcrawler.discovery.resolve probe     # deterministic ATS detection
python -m jobcrawler.discovery.resolve infer     # LLM (via OpenRouter) for the rest
                                                 #  -> pending_review.yaml
python -m jobcrawler.discovery.resolve approve   # live-validate + merge into registry
```

Nothing reaches `companies.yaml` without passing the approve step's live
validation (>=1 job parsed). The weekly workflow runs search + probe and
tells you on Telegram how many entries await approval.

`probe` resolves more candidates than it used to: when a company's own page
names no ATS — the usual case for a homepage, since the Greenhouse iframe
lives on `/careers` — it reads the site's sitemaps (via `robots.txt`, then
`/sitemap.xml`) and retries on the careers pages it finds. The LLM step has
the same lookup as a `find_careers_page` tool.

Every URL discovery touches is checked before connecting: http(s) only, no
credentials, no private or link-local addresses. That matters most for the
LLM's `fetch_url` tool, which picks its URL after reading a scraped page —
i.e. from text a third party controls. The `site:` search source is now
subject to the robots.txt gate too, which DuckDuckGo's file closes on
`/html/`; `data/board_tokens.txt` and the sitemap lookup carry discovery
instead.

Optional env vars / repo secrets: `OPENROUTER_API_KEY` (LLM inference + the
`ai_digest` flag in filters.yaml; models via `RESOLVE_MODEL`/`DIGEST_MODEL`),
`JSEARCH_API_KEY`.

## Tests

```
pip install -r requirements-dev.txt
pytest
```
