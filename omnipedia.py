"""AIWORLD - Omnipedia.

A small local, read-only web encyclopedia over the canonical fictional
world database.  It is built with Flask and Jinja2, renders ordinary
server-side HTML with no JavaScript at all, and reads exclusively through
:mod:`database` so it can never contradict the canon.

Run it with::

    python omnipedia.py

and open http://localhost:5000/
"""

import os

from flask import Flask, abort, g, redirect, render_template, request, url_for

import database as db
from sites.registry import SITES, site_url

# The site is read-only: it never inserts, updates or deletes rows.  New
# canonical facts must be created through the World Builder instead.

app = Flask(__name__)
app.config["SITE_NAME"] = "Omnipedia"
app.config["SITE_TAGLINE"] = "The free encyclopedia of the AIWORLD universe"


@app.context_processor
def inject_net():
    """Expose the other sites so every page carries the simulated net bar."""
    return {"sites": SITES, "current_site": "omnipedia", "site_url": site_url}


# ============================================================
# DATABASE PER REQUEST
# ============================================================

def get_db():
    if "db" not in g:
        g.db = db.connect_db()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# ============================================================
# TEMPLATE HELPERS
# ============================================================

@app.template_filter("humanize")
def humanize(value):
    """Turn a predicate like ``has_capital`` into ``Has capital``."""
    if value is None:
        return ""
    return str(value).replace("_", " ").strip().capitalize()


@app.template_filter("pretty_type")
def pretty_type(value):
    if value is None:
        return "Uncategorised"
    return str(value).replace("_", " ").strip().capitalize()


def article_url(entity_id):
    return url_for("article", entity_id=entity_id)


app.jinja_env.globals["article_url"] = article_url


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    conn = get_db()
    types = db.list_entity_types(conn)
    entities = db.list_entities(conn, limit=1000)
    events = db.list_events(conn, limit=10)

    return render_template(
        "index.html",
        types=types,
        entities=entities,
        events=events,
        entity_count=db.count_entities(conn),
    )


@app.route("/search")
def search():
    conn = get_db()
    query = request.args.get("q", "").strip()
    results = db.search_all(conn, query)
    total = (len(results["entities"])
             + len(results["facts"])
             + len(results["events"]))

    # Nothing in the world matches: invent it automatically, then hand the
    # visitor straight to the new article (a redirect, so refreshing the
    # result does not create it again).
    if query and total == 0:
        import world_generation
        result = world_generation.generate(conn, query)
        if result["ok"] and result["entity"]:
            return redirect(article_url(result["entity"]["id"]))
        return render_template(
            "create_failed.html",
            topic=query,
            answer=result.get("answer"),
            error=result.get("error"),
        ), 200

    return render_template("search.html", results=results, total=total)


@app.route("/article/<entity_id>")
def article(entity_id):
    conn = get_db()
    data = db.article_for_entity(conn, entity_id)
    if data is None:
        abort(404)
    return render_template("entity.html", data=data)


@app.route("/category/<path:type_name>")
def category(type_name):
    conn = get_db()
    entities = db.list_entities(conn, type=type_name, limit=1000)
    if not entities:
        abort(404)
    return render_template(
        "category.html",
        type_name=type_name,
        entities=entities,
    )


@app.route("/articles")
def articles():
    conn = get_db()
    entities = db.list_entities(conn, limit=2000)
    return render_template("articles.html", entities=entities)


@app.route("/events")
def events():
    conn = get_db()
    return render_template("events.html", events=db.list_events(conn, limit=500))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/go")
def go():
    """Redirect a search-style link straight to an exact article."""
    conn = get_db()
    query = request.args.get("q", "").strip()
    matches = db.find_entity(conn, query)
    if len(matches) == 1:
        return redirect(article_url(matches[0]["id"]))
    return redirect(url_for("search", q=query))


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


# ============================================================
# MAIN
# ============================================================

def main():
    db.init_database()
    host = os.environ.get("OMNI_HOST", "127.0.0.1")
    port = int(os.environ.get("OMNI_PORT", "5000"))

    print("=" * 60)
    print("AIWORLD - OMNIPEDIA")
    print("=" * 60)
    print("Database canonico: " + os.path.abspath(db.DATABASE))
    print(f"Server locale:     http://{host}:{port}/")
    print("Premi CTRL+C per fermare il server.")
    print()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
