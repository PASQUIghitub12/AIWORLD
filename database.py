"""AIWORLD - canonical data layer.

This module is the single source of truth for all access to the fictional
world database (``world.db``).  Both the World Builder agent and the
Omnipedia website read and write through here, so there is exactly one
implementation of the database logic.

The schema defined in :func:`init_database` matches the real, existing
``world.db``.  It is created with ``CREATE TABLE IF NOT EXISTS`` so running
it against the current database never alters or destroys existing data.
"""

import os
import random
import sqlite3
import string
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "world.db")


# ============================================================
# CONNECTION
# ============================================================

def connect_db(database=None):
    """Open a connection with row access by column name.

    A busy timeout is set so that a website reading the database and an AI
    writing to it at the same time wait for each other instead of failing
    with "database is locked".
    """
    conn = sqlite3.connect(database or DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(database=None):
    """Create the canonical schema if it does not already exist.

    Harmless on the existing database: every statement is guarded by
    ``IF NOT EXISTS`` and no column is ever changed or dropped.
    """
    conn = connect_db(database)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS aliases (
            alias TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_id TEXT,
            value TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES entities(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(subject_id) REFERENCES entities(id),
            FOREIGN KEY(object_id) REFERENCES entities(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            year INTEGER,
            description TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            change_type TEXT NOT NULL,
            target_id TEXT,
            details TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_fact
        ON facts(subject_id, predicate, object_id, value)
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_relationship
        ON relationships(subject_id, predicate, object_id)
    """)

    conn.commit()
    conn.close()


def generate_id(prefix):
    chars = string.ascii_lowercase + string.digits
    return prefix + "_" + "".join(random.choices(chars, k=6))


# ============================================================
# LOW-LEVEL HELPERS
# ============================================================

def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def entity_exists(conn, entity_id):
    cur = conn.cursor()
    cur.execute("SELECT id FROM entities WHERE id = ?", (entity_id,))
    return cur.fetchone() is not None


def _change_log_columns(conn):
    """Return the set of column names present in change_log."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(change_log)")
    return {row["name"] for row in cur.fetchall()}


def save_change_log(conn, change_type, target_id, details, status="applied"):
    """Record a change, tolerant of both canonical and legacy schemas.

    Canonical schema:  (change_type, target_id, details, status, created_at)
    Legacy schema:     (action, object_type, object_id, details)
    """
    cols = _change_log_columns(conn)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    detail_text = details if isinstance(details, str) else _json(details)

    if "change_type" in cols:
        cur.execute("""
            INSERT INTO change_log
                (change_type, target_id, details, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (change_type, target_id, detail_text, status, now))
    else:
        cur.execute("""
            INSERT INTO change_log
                (timestamp, action, object_type, object_id, details)
            VALUES (?, ?, ?, ?, ?)
        """, (now, change_type, None, target_id, detail_text))


def _json(value):
    import json
    return json.dumps(value, ensure_ascii=False, default=str)


# ============================================================
# QUERY ENGINE (read-only)
# ============================================================

def find_entity(conn, query):
    query = normalize_text(query)
    if not query:
        return []

    cur = conn.cursor()

    cur.execute("""
        SELECT id, name, type, description
        FROM entities
        WHERE LOWER(name) = ?
        LIMIT 10
    """, (query,))
    exact = [dict(row) for row in cur.fetchall()]
    if exact:
        return exact

    cur.execute("""
        SELECT e.id, e.name, e.type, e.description
        FROM aliases a
        JOIN entities e ON e.id = a.entity_id
        WHERE LOWER(a.alias) = ?
        LIMIT 10
    """, (query,))
    alias_matches = [dict(row) for row in cur.fetchall()]
    if alias_matches:
        return alias_matches

    pattern = "%" + query + "%"

    cur.execute("""
        SELECT id, name, type, description
        FROM entities
        WHERE LOWER(name) LIKE ?
           OR LOWER(COALESCE(description, '')) LIKE ?
        ORDER BY name
        LIMIT 20
    """, (pattern, pattern))
    results = [dict(row) for row in cur.fetchall()]

    cur.execute("""
        SELECT DISTINCT e.id, e.name, e.type, e.description
        FROM aliases a
        JOIN entities e ON e.id = a.entity_id
        WHERE LOWER(a.alias) LIKE ?
        ORDER BY e.name
        LIMIT 20
    """, (pattern,))
    for row in cur.fetchall():
        item = dict(row)
        if not any(x["id"] == item["id"] for x in results):
            results.append(item)

    return results[:20]


def get_entity(conn, entity_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, type, description, created_at
        FROM entities
        WHERE id = ?
    """, (entity_id,))
    row = cur.fetchone()
    if not row:
        return None

    entity = dict(row)

    cur.execute("""
        SELECT alias FROM aliases WHERE entity_id = ? ORDER BY alias
    """, (entity_id,))
    entity["aliases"] = [r["alias"] for r in cur.fetchall()]

    return entity


def _resolve_object(conn, object_id):
    if not object_id:
        return None, None
    obj = get_entity(conn, object_id)
    if not obj:
        return None, None
    return obj["name"], obj["type"]


def get_facts(conn, entity_id):
    if not get_entity(conn, entity_id):
        return None

    cur = conn.cursor()
    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        WHERE subject_id = ?
        ORDER BY predicate
    """, (entity_id,))

    facts = []
    for row in cur.fetchall():
        name, rtype = _resolve_object(conn, row["object_id"])
        facts.append({
            "id": row["id"],
            "subject_id": row["subject_id"],
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "object_name": name,
            "object_type": rtype,
            "value": row["value"],
        })
    return facts


def get_relations(conn, entity_id):
    entity = get_entity(conn, entity_id)
    if not entity:
        return None

    cur = conn.cursor()
    outgoing = []
    incoming = []

    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        WHERE subject_id = ?
        ORDER BY predicate
    """, (entity_id,))
    for row in cur.fetchall():
        name, rtype = _resolve_object(conn, row["object_id"])
        outgoing.append({
            "kind": "fact",
            "id": row["id"],
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "object_name": name,
            "object_type": rtype,
            "value": row["value"],
        })

    cur.execute("""
        SELECT id, subject_id, predicate, object_id
        FROM relationships
        WHERE subject_id = ?
        ORDER BY predicate
    """, (entity_id,))
    for row in cur.fetchall():
        name, rtype = _resolve_object(conn, row["object_id"])
        outgoing.append({
            "kind": "relationship",
            "id": row["id"],
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "object_name": name,
            "object_type": rtype,
        })

    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        WHERE object_id = ?
        ORDER BY predicate
    """, (entity_id,))
    for row in cur.fetchall():
        subject = get_entity(conn, row["subject_id"])
        incoming.append({
            "kind": "fact",
            "id": row["id"],
            "subject_id": row["subject_id"],
            "subject_name": subject["name"] if subject else None,
            "subject_type": subject["type"] if subject else None,
            "predicate": row["predicate"],
            "value": row["value"],
        })

    cur.execute("""
        SELECT id, subject_id, predicate, object_id
        FROM relationships
        WHERE object_id = ?
        ORDER BY predicate
    """, (entity_id,))
    for row in cur.fetchall():
        subject = get_entity(conn, row["subject_id"])
        incoming.append({
            "kind": "relationship",
            "id": row["id"],
            "subject_id": row["subject_id"],
            "subject_name": subject["name"] if subject else None,
            "subject_type": subject["type"] if subject else None,
            "predicate": row["predicate"],
        })

    return {"entity": entity, "outgoing": outgoing, "incoming": incoming}


def search_entities(conn, query):
    return find_entity(conn, query)


def search_facts(conn, query):
    query = normalize_text(query)
    if not query:
        return []

    pattern = "%" + query + "%"
    cur = conn.cursor()
    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        WHERE LOWER(predicate) LIKE ?
           OR LOWER(COALESCE(value, '')) LIKE ?
        ORDER BY predicate
        LIMIT 50
    """, (pattern, pattern))

    results = []
    for row in cur.fetchall():
        subject = get_entity(conn, row["subject_id"])
        name, rtype = _resolve_object(conn, row["object_id"])
        results.append({
            "id": row["id"],
            "subject_id": row["subject_id"],
            "subject_name": subject["name"] if subject else None,
            "subject_type": subject["type"] if subject else None,
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "object_name": name,
            "object_type": rtype,
            "value": row["value"],
        })
    return results


def search_events(conn, query):
    query = normalize_text(query)
    pattern = "%" + query + "%"
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, year, description, created_at
        FROM events
        WHERE LOWER(name) LIKE ?
           OR LOWER(COALESCE(description, '')) LIKE ?
        ORDER BY
            CASE WHEN year IS NULL THEN 1 ELSE 0 END,
            year
        LIMIT 50
    """, (pattern, pattern))
    return [dict(row) for row in cur.fetchall()]


def execute_query_tool(conn, tool_name, arguments):
    if not isinstance(arguments, dict):
        arguments = {}

    if tool_name == "find_entity":
        return {"tool": tool_name, "results": find_entity(conn, arguments.get("query", ""))}
    if tool_name == "get_entity":
        return {"tool": tool_name, "result": get_entity(conn, arguments.get("entity_id", ""))}
    if tool_name == "get_relations":
        return {"tool": tool_name, "result": get_relations(conn, arguments.get("entity_id", ""))}
    if tool_name == "get_facts":
        return {"tool": tool_name, "results": get_facts(conn, arguments.get("entity_id", ""))}
    if tool_name == "search_entities":
        return {"tool": tool_name, "results": search_entities(conn, arguments.get("query", ""))}
    if tool_name == "search_facts":
        return {"tool": tool_name, "results": search_facts(conn, arguments.get("query", ""))}
    if tool_name == "search_events":
        return {"tool": tool_name, "results": search_events(conn, arguments.get("query", ""))}

    return {"error": "Unknown tool", "tool": tool_name}


# ============================================================
# WORLD MODIFICATIONS (validated, non-destructive)
# ============================================================

# Strong real-world "tells": if a proposed description contains one of these,
# it is almost certainly the model reciting real-world knowledge instead of
# inventing.  We refuse to persist it so the fictional canon stays fiction.
#
# Keep this to unmistakable signals (real companies/products and explicit
# "this is the real world" phrasing).  Generic verbs like "developed by" or
# "released in" are NOT tells on their own -- an invented entry can perfectly
# well say a thing "was developed by the Whispering Engineers".
REAL_WORLD_TELLS = (
    "in the real world", "real-world", "in real life", "real life",
    "is a real", "are a real", "based on the real",
    # real companies, studios and products
    "mojang", "valve corporation", "nintendo", "microsoft", "sony",
    "google", "apple inc", "amazon.com", "bethesda", "rockstar games",
    "ubisoft", "blizzard entertainment", "activision", "electronic arts",
    "epic games", "sega", "capcom", "tencent", "facebook", "meta platforms",
    "gabe newell", "mark zuckerberg",
    # real media/services/tech brands
    "netflix", "spotify", "hulu", "disney", "pixar", "youtube", "twitter",
    "tiktok", "instagram", "whatsapp", "samsung", "playstation", "xbox",
    "nvidia", "intel", "roblox",
)


def find_real_world_tells(text):
    """Return the real-world tells present in ``text`` (possibly empty)."""
    if not text:
        return []
    low = str(text).lower()
    return [tell for tell in REAL_WORLD_TELLS if tell in low]


def delete_entity(conn, entity_id):
    """Remove one entity and everything that depends on it.

    Used only to undo a just-created entry (for example one that turned out
    to be real-world content).  Returns a small summary of what was removed.
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM facts WHERE subject_id=? OR object_id=?",
                (entity_id, entity_id))
    fact_ids = [r["id"] for r in cur.fetchall()]
    cur.execute("DELETE FROM facts WHERE subject_id=? OR object_id=?",
                (entity_id, entity_id))
    cur.execute("DELETE FROM relationships WHERE subject_id=? OR object_id=?",
                (entity_id, entity_id))
    cur.execute("DELETE FROM aliases WHERE entity_id=?", (entity_id,))
    cur.execute("DELETE FROM entities WHERE id=?", (entity_id,))
    cur.execute("DELETE FROM change_log WHERE target_id=?", (entity_id,))
    for fid in fact_ids:
        cur.execute("DELETE FROM change_log WHERE target_id=?", (str(fid),))
    conn.commit()
    return {"entity": entity_id, "facts": len(fact_ids)}


def apply_world_changes(conn, data):
    """Validate and persist a change proposal from the World Builder.

    Every insert is validated (referenced entities must exist, names are
    de-duplicated) and logged.  Existing records are never modified or
    deleted here.  Proposals that carry real-world content are rejected
    outright, so the model has to invent instead.
    """
    if not isinstance(data, dict):
        return {"success": False, "error": "Invalid change data"}

    entities = data.get("entities", []) or []
    aliases = data.get("aliases", []) or []
    facts = data.get("facts", []) or []
    relationships = data.get("relationships", []) or []
    events = data.get("events", []) or []

    # ---------------- REAL-WORLD GUARD ----------------
    # Never let real-world knowledge into the fictional canon.  We ignore each
    # entry's OWN name, so a topic that is itself a real brand (e.g. the entry
    # "Nintendo") is not refused just for containing its own name.
    suspects = []

    def _tells(text, ignore_name=None):
        if not text:
            return []
        low = str(text).lower()
        if ignore_name:
            low = low.replace(str(ignore_name).lower(), " ")
        return [t for t in REAL_WORLD_TELLS if t in low]

    subject_names = {}
    for entity in entities:
        if isinstance(entity, dict) and entity.get("id"):
            subject_names[entity["id"]] = entity.get("name")

    for entity in entities:
        if isinstance(entity, dict):
            for tell in _tells(entity.get("description"), entity.get("name")):
                suspects.append({"name": entity.get("name"), "tell": tell})
    for event in events:
        if isinstance(event, dict):
            for tell in _tells(event.get("description"), event.get("name")):
                suspects.append({"name": event.get("name"), "tell": tell})
    for fact in facts:
        if isinstance(fact, dict):
            ignore = subject_names.get(fact.get("subject_id"))
            for tell in _tells(fact.get("value"), ignore):
                suspects.append({"name": fact.get("predicate"), "tell": tell})
    if suspects:
        return {
            "success": False,
            "error": ("Real-world content detected. Nothing was saved. "
                      "Do not describe anything from the real world: invent "
                      "a completely fictional AIWORLD entry that merely "
                      "shares the name, and resubmit."),
            "real_world_tells": suspects,
        }

    cur = conn.cursor()
    created = {"entities": [], "aliases": [], "facts": [],
               "relationships": [], "events": []}

    # ---------------- ENTITIES ----------------
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = entity.get("name")
        if not name:
            continue

        entity_id = entity.get("id") or generate_id("ent")
        if entity_exists(conn, entity_id):
            continue

        cur.execute("""
            SELECT id FROM entities WHERE LOWER(name) = LOWER(?) LIMIT 1
        """, (name,))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO entities (id, name, type, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            entity_id,
            name,
            entity.get("type", "unknown"),
            entity.get("description"),
            datetime.now().isoformat(),
        ))
        save_change_log(conn, "create", entity_id, entity)
        created["entities"].append(entity_id)

    # ---------------- ALIASES ----------------
    for alias in aliases:
        if not isinstance(alias, dict):
            continue
        alias_text = alias.get("alias")
        entity_id = alias.get("entity_id")
        if not alias_text or not entity_id:
            continue
        if not entity_exists(conn, entity_id):
            continue

        cur.execute("SELECT alias FROM aliases WHERE LOWER(alias) = LOWER(?)", (alias_text,))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO aliases (alias, entity_id) VALUES (?, ?)
        """, (alias_text, entity_id))
        save_change_log(conn, "create", entity_id, alias)
        created["aliases"].append(alias_text)

    # ---------------- FACTS ----------------
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        subject_id = fact.get("subject_id")
        predicate = fact.get("predicate")
        if not subject_id or not predicate:
            continue
        if not entity_exists(conn, subject_id):
            continue

        object_id = fact.get("object_id")
        value = fact.get("value")
        if object_id and not entity_exists(conn, object_id):
            continue

        try:
            cur.execute("""
                INSERT OR IGNORE INTO facts
                    (subject_id, predicate, object_id, value, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (subject_id, predicate, object_id, value, datetime.now().isoformat()))
        except sqlite3.IntegrityError:
            continue

        if cur.rowcount > 0:
            save_change_log(conn, "create", str(cur.lastrowid), fact)
            created["facts"].append(cur.lastrowid)

    # ---------------- RELATIONSHIPS ----------------
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        subject_id = relationship.get("subject_id")
        predicate = relationship.get("predicate")
        object_id = relationship.get("object_id")
        if not subject_id or not predicate or not object_id:
            continue
        if not entity_exists(conn, subject_id):
            continue
        if not entity_exists(conn, object_id):
            continue

        try:
            cur.execute("""
                INSERT OR IGNORE INTO relationships
                    (subject_id, predicate, object_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (subject_id, predicate, object_id, datetime.now().isoformat()))
        except sqlite3.IntegrityError:
            continue

        if cur.rowcount > 0:
            save_change_log(conn, "create", str(cur.lastrowid), relationship)
            created["relationships"].append(cur.lastrowid)

    # ---------------- EVENTS ----------------
    for event in events:
        if not isinstance(event, dict):
            continue
        name = event.get("name")
        if not name:
            continue

        event_id = event.get("id") or generate_id("event")
        cur.execute("""
            INSERT OR IGNORE INTO events (id, name, year, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            event_id,
            name,
            event.get("year"),
            event.get("description"),
            datetime.now().isoformat(),
        ))
        if cur.rowcount > 0:
            save_change_log(conn, "create", event_id, event)
            created["events"].append(event_id)

    conn.commit()
    return {"success": True, "created": created}


# ============================================================
# WEBSITE / OMNIPEDIA READ HELPERS
# ============================================================

def list_entity_types(conn):
    """Return [(type, count), ...] ordered by type."""
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(type, 'unknown') AS type, COUNT(*) AS count
        FROM entities
        GROUP BY COALESCE(type, 'unknown')
        ORDER BY type
    """)
    return [{"type": r["type"], "count": r["count"]} for r in cur.fetchall()]


def list_entities(conn, type=None, limit=200, offset=0):
    cur = conn.cursor()
    if type:
        cur.execute("""
            SELECT id, name, type, description
            FROM entities
            WHERE LOWER(COALESCE(type, 'unknown')) = LOWER(?)
            ORDER BY name
            LIMIT ? OFFSET ?
        """, (type, limit, offset))
    else:
        cur.execute("""
            SELECT id, name, type, description
            FROM entities
            ORDER BY name
            LIMIT ? OFFSET ?
        """, (limit, offset))
    return [dict(r) for r in cur.fetchall()]


def count_entities(conn, type=None):
    cur = conn.cursor()
    if type:
        cur.execute("""
            SELECT COUNT(*) AS c FROM entities
            WHERE LOWER(COALESCE(type, 'unknown')) = LOWER(?)
        """, (type,))
    else:
        cur.execute("SELECT COUNT(*) AS c FROM entities")
    return cur.fetchone()["c"]


def list_events(conn, limit=100):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, year, description
        FROM events
        ORDER BY CASE WHEN year IS NULL THEN 1 ELSE 0 END, year
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in cur.fetchall()]


def list_facts(conn, limit=200):
    """Return facts with resolved subject and object names, for the websites."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        ORDER BY predicate, subject_id
        LIMIT ?
    """, (limit,))

    results = []
    for row in cur.fetchall():
        subject = get_entity(conn, row["subject_id"])
        name, rtype = _resolve_object(conn, row["object_id"])
        results.append({
            "id": row["id"],
            "subject_id": row["subject_id"],
            "subject_name": subject["name"] if subject else None,
            "subject_type": subject["type"] if subject else None,
            "predicate": row["predicate"],
            "object_id": row["object_id"],
            "object_name": name,
            "object_type": rtype,
            "value": row["value"],
        })
    return results


def get_fact(conn, fact_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, subject_id, predicate, object_id, value
        FROM facts
        WHERE id = ?
    """, (fact_id,))
    row = cur.fetchone()
    if not row:
        return None

    subject = get_entity(conn, row["subject_id"])
    name, rtype = _resolve_object(conn, row["object_id"])
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "subject_name": subject["name"] if subject else None,
        "subject_type": subject["type"] if subject else None,
        "predicate": row["predicate"],
        "object_id": row["object_id"],
        "object_name": name,
        "object_type": rtype,
        "value": row["value"],
    }


def article_for_entity(conn, entity_id):
    """Assemble everything Omnipedia needs for one article page."""
    relations = get_relations(conn, entity_id)
    if relations is None:
        return None

    entity = relations["entity"]
    facts = [o for o in relations["outgoing"] if o["kind"] == "fact"]
    relationships_out = [o for o in relations["outgoing"] if o["kind"] == "relationship"]
    backlinks = relations["incoming"]

    return {
        "entity": entity,
        "facts": facts,
        "relationships": relationships_out,
        "backlinks": backlinks,
    }


def search_all(conn, query):
    """Combined search for the website search page.

    Besides direct predicate/value matches, facts belonging to matching
    entities are included so that searching an entity surfaces what the
    canon says about it.
    """
    query = (query or "").strip()
    if not query:
        return {"query": "", "entities": [], "facts": [], "events": []}

    entities = search_entities(conn, query)
    facts = search_facts(conn, query)
    seen = {f["id"] for f in facts}

    for entity in entities[:10]:
        for fact in (get_facts(conn, entity["id"]) or []):
            if fact["id"] in seen:
                continue
            item = dict(fact)
            item["subject_name"] = entity["name"]
            item["subject_type"] = entity["type"]
            facts.append(item)
            seen.add(fact["id"])

    return {
        "query": query,
        "entities": entities,
        "facts": facts,
        "events": search_events(conn, query),
    }
