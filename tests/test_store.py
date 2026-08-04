from jobcrawler.models import JobPosting
from jobcrawler.store import Store


def job(i):
    return JobPosting(id=f"id-{i}", company="C", title=f"T{i}",
                      location="Remote", url=f"http://x/{i}")


def test_dedup_and_seed_mode(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    assert store.is_empty()

    new = store.insert_new([job(1), job(2)], matched_ids={"id-1"})
    assert [j.id for j in new] == ["id-1", "id-2"]
    assert not store.is_empty()

    # same jobs again -> nothing new; one genuinely new -> only it returns
    new = store.insert_new([job(1), job(2), job(3)], matched_ids=set())
    assert [j.id for j in new] == ["id-3"]

    # unmatched jobs were stored too: re-inserting id-2 as matched is not "new"
    new = store.insert_new([job(2)], matched_ids={"id-2"})
    assert new == []


def test_matched_flag_follows_filter_changes(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))
    store.insert_new([job(1), job(2)], matched_ids={"id-1"})

    def flags():
        return dict(store.db.execute("SELECT id, matched FROM jobs"))

    assert flags() == {"id-1": 1, "id-2": 0}

    # filters changed: id-1 no longer matches, id-2 now does
    store.insert_new([job(1), job(2)], matched_ids={"id-2"})
    assert flags() == {"id-1": 0, "id-2": 1}


def test_health_alerts(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))

    store.log_run("Broken", "ok", 10)
    store.log_run("Broken", "error", 0, "boom")
    store.log_run("Broken", "error", 0, "boom")

    store.log_run("ZeroDrop", "ok", 50)
    store.log_run("ZeroDrop", "unchanged", 0)  # must not count as a real 0
    store.log_run("ZeroDrop", "ok", 0)

    store.log_run("OneBlip", "ok", 5)
    store.log_run("OneBlip", "error", 0, "transient")  # single error: no alert

    store.log_run("Healthy", "ok", 5)
    store.log_run("Healthy", "unchanged", 0)

    # an old "ok 0" must keep alerting even after 10 'unchanged' runs
    # push the ok rows past any recent-rows window
    store.log_run("StaleZero", "ok", 50)
    store.log_run("StaleZero", "ok", 0)
    for _ in range(10):
        store.log_run("StaleZero", "unchanged", 0)

    alerts = store.health_alerts()
    assert len(alerts) == 3
    assert any("Broken" in a and "2 consecutive" in a for a in alerts)
    assert any("ZeroDrop" in a and "was 50" in a for a in alerts)
    assert any("StaleZero" in a and "was 50" in a for a in alerts)


def test_blocked_alerts_only_for_companies_that_used_to_work(tmp_path):
    store = Store(str(tmp_path / "jobs.db"))

    # was delivering, now robots-blocked: worth telling the user about
    store.log_run("WasWorking", "ok", 12)
    store.log_run("WasWorking", "blocked", 0, "robots.txt disallows /jobs")

    # never parsed anything, so nothing went quiet — approving it was the
    # mistake, and one alert a day forever won't help
    store.log_run("NeverWorked", "blocked", 0, "robots.txt disallows /jobs")

    # blocked is not an error: it must not feed the consecutive-failure count
    store.log_run("Mixed", "ok", 3)
    store.log_run("Mixed", "error", 0, "boom")
    store.log_run("Mixed", "error", 0, "boom")
    store.log_run("Mixed", "blocked", 0, "robots.txt disallows /jobs")

    alerts = store.health_alerts()
    assert len(alerts) == 2
    assert any("WasWorking" in a and "blocked" in a for a in alerts)
    assert not any("NeverWorked" in a for a in alerts)
    # Mixed is reported as blocked, not as two consecutive failures
    assert any("Mixed" in a and "blocked" in a for a in alerts)
    assert not any("consecutive" in a for a in alerts)
