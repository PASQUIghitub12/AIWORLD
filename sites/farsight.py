"""Farsight Search - fictional search engine (port 5003).

A portal that searches the local simulated Internet and returns links to the
pages of the other sites.  It is an index over the canon-backed websites.

It does not invent knowledge while it can find a record.  When a search finds
nothing at all, it asks the world to imagine the term (the same generator the
encyclopedia uses) and sends the visitor straight to the new article, so a
search for something unknown never dead-ends.
"""

from flask import Flask, g, redirect, render_template, request, url_for

import database as db
from sites.registry import SITES, site_url


app = Flask(__name__, template_folder="templates/farsight",
            static_folder="static/farsight")
app.config["SITE_NAME"] = "Farsight Search"


def get_db():
    if "db" not in g:
        g.db = db.connect_db()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.context_processor
def inject_sites():
    return {"sites": SITES, "current_site": "farsight", "site_url": site_url}


@app.template_filter("humanize")
def humanize(value):
    return str(value or "").replace("_", " ").strip().capitalize()


@app.route("/")
def home():
    conn = get_db()
    query = request.args.get("q", "").strip()
    results = db.search_all(conn, query)
    total = (len(results["entities"]) + len(results["facts"])
             + len(results["events"]))

    # A search that finds nothing makes the world imagine the term.
    if query and total == 0:
        import world_generation
        res = world_generation.generate(conn, query)
        if res.get("ok") and res.get("entity"):
            return redirect(site_url("omnipedia") + "article/"
                            + res["entity"]["id"])
        return render_template(
            "index.html",
            results=results,
            total=total,
            query=query,
            gen_error=res.get("error"),
        )

    return render_template(
        "index.html",
        results=results,
        total=total,
        query=query,
    )
