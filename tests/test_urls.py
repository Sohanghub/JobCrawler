import pytest

from jobcrawler import urls
from jobcrawler.http import is_ats_api


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "gopher://example.com",
    "http://user:pass@example.com/",
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata service
    "http://127.0.0.1:8000/admin",
    "http://10.0.0.5/internal",
    "http://[::1]/",
])
def test_blocked_urls(url):
    with pytest.raises(urls.Blocked):
        urls.validate_public_url(url)


def test_public_url_passes(monkeypatch):
    monkeypatch.setattr(urls, "is_private_address", lambda host: False)
    assert urls.validate_public_url("https://boards.greenhouse.io/stripe")


def test_private_address_by_dns(monkeypatch):
    # a public-looking hostname whose DNS answer is internal
    monkeypatch.setattr(urls.socket, "getaddrinfo",
                        lambda *a, **kw: [(0, 0, 0, "", ("192.168.1.9", 0))])
    assert urls.is_private_address("internal.example.com")
    with pytest.raises(urls.Blocked):
        urls.validate_public_url("http://internal.example.com/")


def test_one_private_answer_among_several_blocks(monkeypatch):
    # a host publishing both a public A and a private AAAA record chooses
    # which one we connect to; we do not, so any private answer blocks
    monkeypatch.setattr(urls.socket, "getaddrinfo", lambda *a, **kw: [
        (0, 0, 0, "", ("93.184.216.34", 0)),
        (0, 0, 0, "", ("127.0.0.1", 0)),
    ])
    assert urls.is_private_address("split-horizon.example.com")


def test_unresolvable_host_is_not_treated_as_private(monkeypatch):
    import socket as _socket
    monkeypatch.setattr(urls.socket, "getaddrinfo",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            _socket.gaierror("nope")))
    assert urls.is_private_address("nx.example.invalid") is False


@pytest.mark.parametrize("url,binary", [
    ("https://x.example/jobs/1", False),
    ("https://x.example/jobs/1/", False),
    ("https://x.example/brochure.PDF", True),
    ("https://x.example/logo.svg", True),
    ("https://x.example/app.js?v=2", True),   # query ignored
])
def test_is_binary_url(url, binary):
    assert urls.is_binary_url(url) is binary


def test_normalize_host():
    assert urls.normalize_host("https://WWW.Example.com/careers") == "example.com"
    assert urls.normalize_host("http://jobs.example.com") == "jobs.example.com"


@pytest.mark.parametrize("url,exempt", [
    ("https://boards-api.greenhouse.io/v1/boards/stripe/jobs", True),
    ("https://api.lever.co/v0/postings/spotify", True),
    ("https://api.ashbyhq.com/posting-api/job-board/linear", True),
    ("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/x/y/jobs", True),
    ("https://boards.greenhouse.io/stripe", False),  # the HTML board, not the API
    ("https://example.com/careers", False),
])
def test_ats_api_exemption(url, exempt):
    assert is_ats_api(url) is exempt
