"""AIWORLD - the simulated Internet: site registry.

Every fictional website on the local simulated Internet is listed here with
the address it is served from.  This module is the single description of
"what websites exist", used by:

* the launcher (:mod:`aiworld_web`) to know what to start, and
* the browsing client (:mod:`web_client`) to know which hosts are inside the
  simulation and which must be refused.

Nothing here invents lore; it only describes websites.
"""

# The one true encyclopedia, also runnable on its own via omnipedia.py.
#
# The sites are addressed by name, not by 127.0.0.1:port.  These are
# ".localhost" names, which every browser resolves to this PC by design
# (RFC 6761), so no hosts-file or DNS change is ever needed.  aiworld_web
# serves every name on port 80, routed by the Host header.  The "port" below
# is only the fallback port each site also answers on, so
# http://127.0.0.1:5000/ keeps working too.
OMNIPEDIA_URL = "http://omnipedia.localhost/"

SITES = [
    {
        "slug": "omnipedia",
        "name": "Omnipedia",
        "kind": "encyclopedia",
        "port": 5000,
        "url": OMNIPEDIA_URL,
        "description": "The free encyclopedia of the AIWORLD universe.",
        "module": "omnipedia",
        "app_attr": "app",
    },
    {
        "slug": "herald",
        "name": "The Zyphoran Herald",
        "kind": "news",
        "port": 5001,
        "url": "http://zyphoranherald.localhost/",
        "description": "Daily bulletins and the world desk, from the canon records.",
        "module": "sites.herald",
        "app_attr": "app",
    },
    {
        "slug": "almanac",
        "name": "Navigator's Almanac",
        "kind": "reference",
        "port": 5002,
        "url": "http://navigatorsalmanac.localhost/",
        "description": "Places of the world and the connections between them.",
        "module": "sites.almanac",
        "app_attr": "app",
    },
    {
        "slug": "farsight",
        "name": "Farsight Search",
        "kind": "portal",
        "port": 5003,
        "url": "http://farsight.localhost/",
        "description": "The world's search engine, spanning every local site.",
        "module": "sites.farsight",
        "app_attr": "app",
    },
]

SITES_BY_SLUG = {s["slug"]: s for s in SITES}


def site_url(slug):
    site = SITES_BY_SLUG.get(slug)
    return site["url"] if site else None


def allowed_hosts():
    """Hostname:port pairs the browsing client may contact."""
    from urllib.parse import urlparse
    return {urlparse(s["url"]).netloc for s in SITES}
