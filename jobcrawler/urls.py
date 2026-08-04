"""URL safety and normalization.

Adapted from Firecrawl's lib/validateUrl.ts (scheme allowlist),
engines/utils/safeFetch.ts (private-address rejection) and
WebScraper/crawler.ts isFile() (binary-link skip list).
"""
import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")

# Firecrawl's isFile() list, minus the formats it keeps for its own parsers
# (pdf/docx/xml). A job description never lives in one of these, and following
# them wastes the per-domain rate budget.
BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".tiff",
    ".css", ".js", ".woff", ".woff2", ".ttf",
    ".zip", ".exe", ".dmg", ".pdf",
    ".mp3", ".mp4", ".wav", ".avi", ".flv",
    ".pptx", ".xlsx", ".docx",
)


class Blocked(Exception):
    """URL refused before any connection was made."""


def is_private_address(host: str) -> bool:
    """True when the host resolves to anything off the public internet.
    Mirrors safeFetch.ts's isIPPrivate, which rejects anything outside
    IPAddr's 'unicast' range.

    ANY private answer blocks, not all of them: a host publishing both a
    public A and a private AAAA record gets to pick which one we connect to,
    and we do not.

    Firecrawl enforces this on the socket at connect time, which also defeats
    DNS rebinding; requests gives us no such hook, so this resolves up front.
    A host that flips to a private answer between this call and the request
    would slip through — acceptable here, where the threat is a model
    following a link into the metadata service, not an attacker who controls
    DNS.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return not ip.is_global
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False  # unresolvable: let the request fail on its own terms
    return any(not ipaddress.ip_address(i[4][0]).is_global for i in infos)


def validate_public_url(url: str) -> str:
    """Raise Blocked unless url is an ordinary http(s) URL on a public host.

    The gate for URLs this project did not choose itself — above all the ones
    an LLM picks while reading a scraped page, which is attacker-controlled
    text one hop away from our HTTP client.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise Blocked(f"scheme {parts.scheme!r} not allowed: {url}")
    if parts.username or parts.password:
        raise Blocked(f"credentials in URL: {url}")
    host = parts.hostname
    if not host:
        raise Blocked(f"no host in URL: {url}")
    if is_private_address(host):
        raise Blocked(f"host {host} resolves to a private address: {url}")
    return url


def is_binary_url(url: str) -> bool:
    """Cheap 'don't bother fetching this' test on the path's extension."""
    return urlsplit(url).path.lower().endswith(BINARY_SUFFIXES)


def normalize_host(url: str) -> str:
    """Registrable-ish host for comparing two URLs: lowercased, no 'www.'.

    Firecrawl's url-utils.ts resolves the real registrable domain through the
    public suffix list; that needs a maintained PSL copy, so this stops at the
    hostname — enough for 'are these two candidates the same company'.
    """
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host
