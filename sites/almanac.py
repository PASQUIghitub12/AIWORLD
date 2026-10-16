"""Navigator's Almanac - fictional reference website (port 5002).

A traveler's gazetteer of the world: the places the canon records and the
connections between them.  Everything is derived from the canonical
database; anything not recorded is shown as unknown rather than guessed.

Read-only.
"""

from flask import Flask, abort, g, render_template, url_for

import database as db
from sites.registry import SITES, site_url


app = Flask(__name__, template_folder="templates/almanac",
            static_folder="static/almanac")
app.config["SITE_NAME"] = "Navigator's Almanac"
app.config["SITE_TAGLINE"] = "Places and the ways between them"


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
    return {"sites": SITES, "current_site": "almanac", "site_url": site_url}


@app.template_filter("humanize")
def humanize(value):
    return str(value or "").replace("_", " ").strip().capitalize()


@app.route("/")
def home():
    conn = get_db()
    return render_template(
        "index.html",
        types=db.list_entity_types(conn),
        entities=db.list_entities(conn, limit=500),
    )


@app.route("/place/<entity_id>")
def place(entity_id):
    conn = get_db()
    data = db.article_for_entity(conn, entity_id)
    if data is None:
        abort(404)

    # Outbound connections where the canon points at another place/entity.
    connections = [f for f in data["facts"] if f["object_id"]]
    values = [f for f in data["facts"] if not f["object_id"]]
    routes = data["relationships"]

    return render_template(
        "place.html",
        entity=data["entity"],
        connections=connections,
        values=values,
        routes=routes,
        backlinks=data["backlinks"],
    )


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404
