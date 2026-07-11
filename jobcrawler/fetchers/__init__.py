from . import greenhouse, html_tier1, lever, spa_tier2, workday

# Every fetcher: fetch(company_cfg, http) -> list[JobPosting].
# Unknown keys are skipped (and logged) by main, so registry entries for
# not-yet-implemented tiers are harmless.
FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "workday": workday.fetch,
    "html": html_tier1.fetch,   # tier 1
    "spa": spa_tier2.fetch,     # tier 2
    # P3: "zyte" (tier 3)
}
