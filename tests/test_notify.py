from jobcrawler.models import JobPosting
from jobcrawler.notify import LIMIT, _messages


def test_chunking_stays_under_limit():
    jobs = [JobPosting(id=str(i), company="C" * 100, title="T" * 100,
                       location="L" * 50, url=f"http://x/{i}")
            for i in range(200)]
    msgs = list(_messages(jobs))
    assert len(msgs) > 1
    assert all(len(m) <= LIMIT for m in msgs)
    assert sum(m.count("•") for m in msgs) == 200  # no job dropped
