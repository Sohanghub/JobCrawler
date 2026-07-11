from . import ashby, greenhouse, html_tier1, lever, spa_tier2, workday, zyte_tier3

# Every fetcher: fetch(company_cfg, http) -> list[JobPosting].
# Unknown keys are skipped (and logged) by main, so registry entries for
# unrecognized sources are harmless.
FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "workday": workday.fetch,
    "ashby": ashby.fetch,
    "html": html_tier1.fetch,      # tier 1
    "spa": spa_tier2.fetch,        # tier 2
    "zyte": zyte_tier3.fetch,      # tier 3
}
