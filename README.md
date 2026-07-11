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
  ats: greenhouse   # or lever
  token: example    # board token from the company's careers URL
```

## Tests

```
pytest
```
