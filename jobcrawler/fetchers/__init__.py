from . import greenhouse, lever

# Every fetcher: fetch(company_cfg, http_session) -> list[JobPosting].
# Unknown keys are skipped (and logged) by main, so registry entries for
# not-yet-implemented tiers are harmless.
FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    # P2: "workday", "html" (tier 1), "spa" (tier 2); P3: "zyte" (tier 3)
}
