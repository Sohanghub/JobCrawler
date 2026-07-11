import pytest

from jobcrawler.http import Http, Unchanged
from jobcrawler.store import Store


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.sent_headers = []

    def get(self, url, headers=None, **kwargs):
        self.sent_headers.append(headers or {})
        return self.responses.pop(0)


def make_http(tmp_path, responses):
    store = Store(str(tmp_path / "jobs.db"))
    return Http(store, session=FakeSession(responses), min_interval=0)


def test_body_hash_short_circuit(tmp_path):
    http = make_http(tmp_path, [FakeResponse(content=b"same"),
                                FakeResponse(content=b"same"),
                                FakeResponse(content=b"different")])
    assert http.get("http://x/a", cache=True).content == b"same"
    with pytest.raises(Unchanged):
        http.get("http://x/a", cache=True)
    assert http.get("http://x/a", cache=True).content == b"different"


def test_304_and_conditional_headers(tmp_path):
    http = make_http(tmp_path, [
        FakeResponse(content=b"v1", headers={"ETag": '"e1"'}),
        FakeResponse(status_code=304),
    ])
    http.get("http://x/a", cache=True)
    with pytest.raises(Unchanged):
        http.get("http://x/a", cache=True)
    assert http.session.sent_headers[1].get("If-None-Match") == '"e1"'


def test_no_cache_flag_never_raises(tmp_path):
    http = make_http(tmp_path, [FakeResponse(content=b"same"),
                                FakeResponse(content=b"same")])
    http.get("http://x/a")
    http.get("http://x/a")  # identical body but cache=False: no Unchanged
