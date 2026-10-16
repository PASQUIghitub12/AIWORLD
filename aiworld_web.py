"""AIWORLD - launch the whole simulated Internet.

Starts every website in the registry, both **by name** and **by port**:

* by name on port 80, routed by the HTTP ``Host`` header, so the sites answer
  at ``http://omnipedia.localhost/``, ``http://zyphoranherald.localhost/``,
  and so on.  ``*.localhost`` names resolve to this PC in every browser with no
  hosts-file or DNS setup at all (RFC 6761).
* on each site's own port (``http://127.0.0.1:5000/`` ...) as a fallback, so
  the IP addresses keep working too.

Run it with::

    python aiworld_web.py

Then open ``http://omnipedia.localhost/`` (or ``http://127.0.0.1:5000/``) and
follow the "net" bar to the other sites.  Stop everything with Ctrl+C.
"""

import importlib
import threading
import time
from urllib.parse import urlparse

from sites.registry import SITES
from werkzeug.serving import make_server


class HostDispatcher:
    """Route each request to the right site by the ``Host`` header."""

    def __init__(self, mapping, default):
        self.mapping = mapping
        self.default = default

    def __call__(self, environ, start_response):
        host = (environ.get("HTTP_HOST") or "").split(":")[0].lower()
        if host.startswith("www."):
            host = host[4:]
        app = self.mapping.get(host, self.default)
        return app(environ, start_response)


def main():
    host = "127.0.0.1"

    print("=" * 60)
    print("AIWORLD - SIMULATED INTERNET")
    print("=" * 60)

    apps = {}
    for site in SITES:
        module = importlib.import_module(site["module"])
        apps[site["slug"]] = getattr(module, site["app_attr"])

    # 1) Each site on its own port (fallback / direct IP access).
    for site in SITES:
        server = make_server(host, site["port"], apps[site["slug"]],
                             threaded=True)
        threading.Thread(target=server.serve_forever, name=site["slug"],
                         daemon=True).start()
        print(f"[UP] {site['name']:<22} http://{host}:{site['port']}/"
              f"  ({site['kind']})")

    # 2) Every site by name on port 80, routed by the Host header.
    mapping = {}
    for site in SITES:
        name = urlparse(site["url"]).hostname
        mapping[name] = apps[site["slug"]]
    dispatcher = HostDispatcher(mapping, apps["omnipedia"])

    try:
        named = make_server(host, 80, dispatcher, threaded=True)
    except OSError as e:
        print()
        print("[WARN] Could not listen on port 80, so the site names")
        print("       (http://omnipedia.localhost/ ...) will not work:", e)
        print("       The sites are still up on their ports above.")
    else:
        threading.Thread(target=named.serve_forever, name="domains",
                         daemon=True).start()
        print()
        for site in SITES:
            name = urlparse(site["url"]).hostname
            print(f"[UP] {name:<24} {site['url']}")

    print()
    print("Open http://omnipedia.localhost/ (or http://127.0.0.1:5000/)")
    print("and use the 'net' bar to visit sites.")
    print("Press CTRL+C to stop the whole simulated Internet.")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("[SYSTEM] Stopping the simulated Internet.")


if __name__ == "__main__":
    main()
