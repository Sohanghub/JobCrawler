import pytest

from jobcrawler import semantic
from jobcrawler.models import JobPosting

pytestmark = pytest.mark.skipif(not semantic.available(),
                                reason="ml deps not installed")


def job(i, title):
    return JobPosting(id=f"id-{i}", company="C", title=title,
                      location="Remote", url=f"http://x/{i}")


def test_semantic_title_match(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    jobs = [job(1, "Backend Developer"),        # no fuzzy overlap with roles
            job(2, "Account Executive"),
            job(3, "Software Engineer II")]
    filters = {"roles": ["Software Engineer"], "semantic_threshold": 0.45}
    matched = semantic.title_match_ids(jobs, filters)
    assert "id-3" in matched
    assert "id-1" in matched          # semantically close despite no keyword
    assert "id-2" not in matched      # sales role stays out
    # second call served from the Chroma embedding cache, same result
    assert semantic.title_match_ids(jobs, filters) == matched
    assert semantic.title_match_ids([], filters) == set()
