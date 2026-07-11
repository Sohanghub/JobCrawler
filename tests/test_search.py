from jobcrawler.discovery import search

HTML = """
<a href="https://boards.greenhouse.io/acme">Acme</a>
<a href="https://boards.greenhouse.io/acme?src=x">Acme dup</a>
<a href="https://jobs.lever.co/rocketco">Rocket</a>
<a href="https://jobs.ashbyhq.com/coolstartup">Cool</a>
<a href="https://example.com/other">noise</a>
"""


def test_extract_board_links():
    found = search.extract_board_links(HTML)
    assert {c["name"] for c in found} == {"acme", "rocketco", "coolstartup"}
    urls = {c["url"] for c in found}
    assert "https://jobs.lever.co/rocketco" in urls


def test_dedup_candidates():
    found = [{"name": "Acme", "url": ""}, {"name": "acme!", "url": ""},
             {"name": "NewCo", "url": ""}, {"name": "", "url": ""}]
    fresh = search.dedup_candidates(found, known_names={"Acme Inc"})
    # "Acme" survives ("Acme Inc" normalizes differently), its dup doesn't
    assert [c["name"] for c in fresh] == ["Acme", "NewCo"]


def test_token_file_candidates(tmp_path):
    p = tmp_path / "tokens.txt"
    p.write_text("# comment\nstripe\n\nrazorpay\n", encoding="utf-8")
    cands = search.token_file_candidates(str(p))
    assert [c["name"] for c in cands] == ["stripe", "razorpay"]
    assert search.token_file_candidates(str(tmp_path / "missing.txt")) == []
