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

    alerts = store.health_alerts()
    assert len(alerts) == 2
    assert any("Broken" in a and "2 consecutive" in a for a in alerts)
    assert any("ZeroDrop" in a and "was 50" in a for a in alerts)
