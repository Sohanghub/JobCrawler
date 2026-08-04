import gzip
from types import SimpleNamespace

from jobcrawler.discovery import sitemap

INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://acme.example/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://acme.example/sitemap-blog.xml</loc></sitemap>
</sitemapindex>"""

PAGES = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://acme.example/</loc></url>
  <url><loc>https://acme.example/about</loc></url>
  <url><loc>https://acme.example/careers/jobs/1234-backend-engineer</loc></url>
  <url><loc>https://acme.example/careers</loc></url>
</urlset>"""

BLOG = """<?xml version="1.0"?>
<urlset><url><loc>https://acme.example/blog/hiring-is-hard</loc></url></urlset>"""


class FakeHttp:
    def __init__(self, pages, sitemaps=()):
        self.pages = pages
        self.robots = SimpleNamespace(sitemaps=lambda url: list(sitemaps))
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        if url not in self.pages:
            raise RuntimeError("404")
        body = self.pages[url]
        content = gzip.compress(body.encode()) if url.endswith(".gz") \
            else body.encode()
        return SimpleNamespace(text=body, content=content,
                               raise_for_status=lambda: None)


PAGE_MAP = {
    "https://acme.example/sitemap.xml": INDEX,
    "https://acme.example/sitemap-pages.xml": PAGES,
    "https://acme.example/sitemap-blog.xml": BLOG,
}


def test_recurses_through_a_sitemap_index():
    http = FakeHttp(PAGE_MAP)
    found = sitemap.collect_urls(http, "https://acme.example/some/page")
    assert "https://acme.example/careers" in found
    assert "https://acme.example/blog/hiring-is-hard" in found
    assert http.requested[0] == "https://acme.example/sitemap.xml"


def test_robots_declared_sitemaps_come_first():
    http = FakeHttp({"https://acme.example/jobs-map.xml": PAGES},
                    sitemaps=["https://acme.example/jobs-map.xml"])
    assert sitemap.collect_urls(http, "https://acme.example/")
    assert http.requested[0] == "https://acme.example/jobs-map.xml"


def test_gzipped_sitemap():
    http = FakeHttp({"https://acme.example/sitemap.xml": INDEX,
                     "https://acme.example/sitemap-pages.xml.gz": PAGES},
                    sitemaps=["https://acme.example/sitemap-pages.xml.gz"])
    assert "https://acme.example/careers" in sitemap.collect_urls(
        http, "https://acme.example/")


def bomb_http(compressed):
    class BombHttp(FakeHttp):
        def get(self, url, **kwargs):
            self.requested.append(url)
            return SimpleNamespace(text="", content=compressed,
                                   raise_for_status=lambda: None)

    return BombHttp({}, sitemaps=["https://acme.example/s.xml.gz"])


def test_gzip_output_is_capped(monkeypatch):
    # 8 MB of zeros compresses to a few KB: small enough to get past the
    # request-size check, ruinous if decompressed whole
    monkeypatch.setattr(sitemap, "MAX_BODY", 64 * 1024)
    body = sitemap._fetch(bomb_http(gzip.compress(b"\0" * 8 * 1024 * 1024)),
                          "https://acme.example/s.xml.gz")
    assert len(body) == 64 * 1024


def test_oversized_gzip_is_refused_and_the_crawl_goes_on(monkeypatch):
    monkeypatch.setattr(sitemap, "MAX_BODY", 64)
    http = bomb_http(gzip.compress(b"\0" * 8 * 1024 * 1024))
    assert sitemap.collect_urls(http, "https://acme.example/") == []


def test_ranking_prefers_the_hub_over_a_single_posting():
    ranked = sitemap.rank_careers_urls([
        "https://acme.example/about",
        "https://acme.example/careers/jobs/1234-backend-engineer",
        "https://acme.example/careers",
        "https://acme.example/blog/hiring-is-hard",
    ])
    assert ranked[0] == "https://acme.example/careers"
    assert "https://acme.example/about" not in ranked


def test_find_careers_urls_end_to_end():
    http = FakeHttp(PAGE_MAP)
    assert sitemap.find_careers_urls(http, "https://acme.example/")[0] == \
        "https://acme.example/careers"


def test_falls_back_to_conventional_paths_without_a_sitemap():
    http = FakeHttp({})
    assert sitemap.find_careers_urls(http, "https://acme.example/") == [
        "https://acme.example/careers", "https://acme.example/careers/",
        "https://acme.example/jobs"]


def test_visited_set_stops_a_self_referential_index():
    loop = """<sitemapindex><sitemap>
      <loc>https://acme.example/sitemap.xml</loc></sitemap></sitemapindex>"""
    http = FakeHttp({"https://acme.example/sitemap.xml": loop})
    assert sitemap.collect_urls(http, "https://acme.example/") == []
    assert http.requested == ["https://acme.example/sitemap.xml"]


def test_sitemap_cap_bounds_the_work():
    many = "<sitemapindex>" + "".join(
        f"<sitemap><loc>https://acme.example/s{i}.xml</loc></sitemap>"
        for i in range(50)) + "</sitemapindex>"
    http = FakeHttp({"https://acme.example/sitemap.xml": many})
    sitemap.collect_urls(http, "https://acme.example/")
    assert len(http.requested) <= sitemap.MAX_SITEMAPS
