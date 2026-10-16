"""The Zyphoran Herald - fictional news website (port 5001).

The Herald does not invent stories.  Its bulletins are generated from the
canonical facts in the world database and are labelled as such: it is an
in-world newspaper that can only report what the canon already records.

Read-only: it never writes to the database.
"""

from flask import Flask, abort, g, render_template, request, url_for

import database as db
from sites.registry import SITES, site_url


app = Flask(__name__, template_folder="templates/herald",
            static_folder="static/herald")
app.config["SITE_NAME"] = "The Zyphoran Herald"
app.config["SITE_TAGLINE"] = "The world's daily record"


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
    return {"sites": SITES, "current_site": "herald", "site_url": site_url}


@app.template_filter("humanize")
def humanize(value):
    return str(value or "").replace("_", " ").strip().capitalize()


def _headline(fact):
    """A factual, generated headline. Never introduces new information."""
    subject = fact["subject_name"] or fact["subject_id"]
    predicate = humanize(fact["predicate"]).lower()
    obj = fact["object_name"] or fact["value"]
    return f"{subject} — {predicate}: {obj}"


@app.route("/")
def home():
    conn = get_db()
    facts = db.list_facts(conn, limit=100)
    events = db.list_events(conn, limit=20)
    return render_template(
        "index.html",
        facts=facts,
        events=events,
        headline=_headline,
    )


@app.route("/bulletin/<int:fact_id>")
def bulletin(fact_id):
    conn = get_db()
    fact = db.get_fact(conn, fact_id)
    if fact is None:
        abort(404)
    subject = db.get_entity(conn, fact["subject_id"]) if fact["subject_id"] else None
    obj = db.get_entity(conn, fact["object_id"]) if fact["object_id"] else None
    return render_template(
        "bulletin.html",
        fact=fact,
        subject=subject,
        obj=obj,
        headline=_headline,
    )


@app.route("/world")
def world():
    conn = get_db()
    return render_template(
        "world.html",
        types=db.list_entity_types(conn),
        entities=db.list_entities(conn, limit=500),
    )


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404
