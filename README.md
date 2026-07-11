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

Tier 1 (server-rendered HTML) adds `url` + `selectors:`, Tier 2 (SPA) adds
`xhr:` or `playwright:`, Tier 3 (anti-bot) uses `ats: zyte` + selectors and
needs `ZYTE_API_KEY` (capped by `MAX_ZYTE_REQUESTS_PER_RUN`, default 20).

## Growing the registry (discovery loop)

```
python -m jobcrawler.discovery.search            # find candidates (JSearch /
                                                 #  site: search / data/board_tokens.txt)
python -m jobcrawler.discovery.resolve probe     # deterministic ATS detection
python -m jobcrawler.discovery.resolve infer     # LLM (Claude batch) for the rest
python -m jobcrawler.discovery.resolve collect   # batch results -> pending_review.yaml
python -m jobcrawler.discovery.resolve approve   # live-validate + merge into registry
```

Nothing reaches `companies.yaml` without passing the approve step's live
validation (>=1 job parsed). The weekly workflow runs search + probe and
tells you on Telegram how many entries await approval.

Optional env vars / repo secrets: `ANTHROPIC_API_KEY` (LLM inference + the
`ai_digest` flag in filters.yaml), `JSEARCH_API_KEY`, `ZYTE_API_KEY`.

## Semantic matching

Installing `requirements-ml.txt` enables sentence-transformers + Chroma title
matching alongside rapidfuzz; digest entries are tagged `[fuzzy]`,
`[semantic]`, or `[fuzzy+semantic]` so the two can be compared. Tune
`semantic_threshold` in `config/filters.yaml`. Without those packages the run
is fuzzy-only.

## Tests

```
pytest
```
