"""AIWORLD - controlled browsing client for the simulated Internet.

The World Resident (and any future in-world program) reads the simulated
Internet only through this module.  It performs plain HTTP requests against
the local websites listed in :mod:`sites.registry` - exactly like a browser -
and turns the returned HTML into readable text with its links.

Design rules:

* It has **no access to the canonical database**; it can only see what the
  websites render.
* It refuses any host that is not a registered local site, so the resident
  can never wander onto the real Internet.
* Links inside a page are rewritten to absolute local URLs, so the resident
  can follow them like a real visitor without guessing paths.
"""

import http.client
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from sites.registry import SITES, allowed_hosts, site_url


DEFAULT_BASE = site_url("omnipedia") or "http://127.0.0.1:5000/"
SEARCH_SITE = "farsight"

_ALLOWED_HOSTS = allowed_hosts()
_EXTRA = os.environ.get("OMNI_ALLOWED_HOSTS", "")
if _EXTRA:
    _ALLOWED_HOSTS |= {h.strip() for h in _EXTRA.split(",") if h.strip()}


# ============================================================
# REACHING THE SIMULATED NET
# ============================================================
# The sites are addressed by ".localhost" names.  A browser resolves those to
# this PC on its own, but the operating system's resolver (which urllib uses)
# does not.  So we keep the site's name on the request (for the Host header and
# for resolving relative links), but dial loopback ourselves instead of asking
# DNS.  Nothing here can ever leave this PC.

class _LoopbackHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = self._create_connection(
            ("127.0.0.1", self.port), self.timeout, self.source_address
        )


class _LocalHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_LoopbackHTTPConnection, req)


_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _LocalHTTPHandler
)


# ============================================================
# HTML -> TEXT (+ LINKS)
# ============================================================

class _TextExtractor(HTMLParser):
    """Collect readable text and absolutised links from a page."""

    SKIP = {"script", "style", "noscript", "head"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.buffers = []
        self.skip_depth = 0
        self.title = None
        self._in_title = False
        self.links = []
        self._href = None
        self._anchor = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []
        if tag in {"p", "div", "section", "article", "li", "tr", "h1",
                   "h2", "h3", "h4", "dt", "dd", "br"}:
            self.buffers.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            text = "".join(self._anchor).strip()
            href = urllib.parse.urljoin(self.base_url, self._href)
            if href.startswith("http"):
                self.links.append((text or href, href))
            self._href = None
            self._anchor = []
        if tag in {"p", "div", "section", "article", "li", "tr", "h1",
                   "h2", "h3", "h4"}:
            self.buffers.append("\n")

    def handle_data(self, data):
        if self._href is not None:
            self._anchor.append(data)
        if self.skip_depth > 0:
            return
        if self._in_title:
            self.title = (self.title or "") + data
        text = data.strip()
        if text:
            self.buffers.append(text + " ")

    def text(self):
        raw = "".join(self.buffers)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
        raw = raw.strip()

        seen = set()
        lines = []
        for label, href in self.links:
            if href in seen:
                continue
            seen.add(href)
            lines.append(f"- {label} -> {href}")
        if lines:
            raw += "\n\nLINKS ON THIS PAGE:\n" + "\n".join(lines)
        return raw


def html_to_text(html, base_url):
    parser = _TextExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        stripped = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", stripped).strip()
    return parser.text()


# ============================================================
# BROWSE
# ============================================================

def resolve(target, base=DEFAULT_BASE):
    """Resolve a path or absolute URL to an allowed local URL.

    Raises ``ValueError`` for any host outside the simulated Internet.
    """
    if target is None:
        target = "/"
    target = str(target).strip()

    if target.startswith("http://") or target.startswith("https://"):
        full = target
    else:
        full = urllib.parse.urljoin(base, target)

    host = urllib.parse.urlparse(full).netloc
    if host not in _ALLOWED_HOSTS:
        raise ValueError(
            f"Refusing to browse outside the simulated Internet ({host})"
        )
    return full


def is_reachable(timeout=3, base=DEFAULT_BASE):
    try:
        with _opener.open(base, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def fetch(target, base=DEFAULT_BASE, timeout=20):
    """Fetch one page. Returns a dict; expected failures do not raise."""
    try:
        url = resolve(target, base=base)
    except ValueError as e:
        return {"ok": False, "url": str(target), "status": 0, "error": str(e)}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AIWORLD-Resident"})
        with _opener.open(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return {"ok": True, "url": url, "status": 200,
                "text": html_to_text(html, url)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "url": url, "status": e.code,
                "error": f"HTTP {e.code}",
                "text": "This page does not exist on the site."}
    except Exception as e:
        return {"ok": False, "url": url, "status": 0,
                "error": type(e).__name__,
                "text": "The site could not be reached."}


def browse(target, base=DEFAULT_BASE, timeout=20):
    """Public browsing entry point used by the World Resident."""
    result = fetch(target, base=base, timeout=timeout)
    return {
        "path": result["url"],
        "status": result["status"],
        "error": result.get("error"),
        "content": result.get("text", ""),
    }


def search(query, timeout=20):
    """Use the simulated net's own search engine, like a visitor would."""
    base = site_url(SEARCH_SITE) or DEFAULT_BASE
    return browse("?q=" + urllib.parse.quote(query), base=base, timeout=timeout)


def list_sites():
    """The directory of known sites, for the resident to choose from."""
    return [
        {"name": s["name"], "kind": s["kind"], "url": s["url"],
         "description": s["description"]}
        for s in SITES
    ]
