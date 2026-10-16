"""AIWORLD - on-demand world generation for the websites.

When a visitor searches a website for something the world does not have yet,
the website can ask the local model to invent a fictional in-world entry and
persist it, then show the visitor the new article -- so nobody has to open the
World Builder window.

This module is the one place that bridges the read-only websites and the canon.
It writes only through :func:`database.apply_world_changes`, and it guards hard
against real-world leakage: a narrow word-list rejects obvious real-world
content, and a second model check removes any entry that still turns out to be
a real-world product/company/person/work, then tries once more.
"""

import database as db


# A single generated topic, kept short and sane.
MAX_TOPIC_CHARS = 80

# How the model must answer: a tiny JSON object.
_JSON_RULES = (
    "Reply with ONLY this JSON, no prose:\n"
    '{"type": "<one word>", "description": "<detailed description>", '
    '"facts": [{"predicate": "<...>", "value": "<...>"}]}'
)

_SYSTEM = (
    "You write a single entry for AIWORLD, a wholly invented fictional "
    "universe. You have NO knowledge of the real world and must never use it. "
    "The NAME you are given is only a label for this world: IGNORE any "
    "real-world meaning it may have.\n"
    "Invent an ORIGINAL fictional thing for AIWORLD named \"{name}\". It MUST be "
    "a fictional PLACE, realm, city, creature, being, phenomenon, order, "
    "faction, artifact or custom. It must NOT be a product, game, app, website, "
    "service, platform, software, tool, company, brand, device or any "
    "real-style person.\n"
    "Write a detailed encyclopedia description of 4 to 6 sentences (what it "
    "is, where it is, its appearance, origin, purpose, and its ties to the "
    "rest of the world), and add 3 to 5 facts.\n" + _JSON_RULES
)

_SYSTEM_HARD = (
    "You write a single entry for AIWORLD, a wholly invented fictional "
    "universe. A previous attempt was refused for resembling a real-world "
    "thing; that is forbidden.\n"
    "Invent an ORIGINAL fictional thing for AIWORLD named \"{name}\". It MUST be "
    "a fictional PLACE, realm, city, creature, being, phenomenon, order, "
    "faction, artifact or custom. Do NOT make it a product, game, app, website, "
    "service, platform, software, tool, company, brand, device or person, not "
    "even a realistic one.\n"
    "Write a detailed encyclopedia description of 4 to 6 sentences and 3 to 5 "
    "facts.\n" + _JSON_RULES
)

# The model judges whether a saved entry is really a real-world thing.
# It must first name the famous real-world thing sharing the name (if any),
# which stops it rationalising a soft echo as "fiction" just because the text
# adds "in AIWORLD" or invented place names.
_VERIFY = (
    "You are checking ONE entry written for a FICTIONAL universe.\n"
    "Given a NAME and DESCRIPTION, do this:\n"
    "Step 1: State the famous REAL-WORLD thing that has this name (a game, app, "
    "service, company, film, book, person or place). If none is famous, say "
    "'none'.\n"
    "Step 2: Decide whether the DESCRIPTION repeats that real thing's real "
    "traits (what it is and how it works), even if it adds 'in AIWORLD' or "
    "fictional place names. An original fictional thing that shares only the "
    "name does NOT count.\n"
    "Then output a final line exactly: 'VERDICT: REAL' if it repeats the real "
    "thing, otherwise 'VERDICT: FICTION'."
)


def _is_real_world(name, description, builder):
    """True only when the model says the description is a real-world thing."""
    if not description:
        return False
    try:
        out = builder.ask_ollama([
            {"role": "system", "content": _VERIFY},
            {"role": "user", "content": f"NAME: {name}\nDESCRIPTION: {description}"},
        ])
    except Exception:
        return False
    if not out:
        return False
    upper = out.upper()
    if "VERDICT: REAL" in upper:
        return True
    if "VERDICT: FICTION" in upper:
        return False
    # Fall back to the old single-word reply style.
    stripped = out.strip()
    return bool(stripped) and stripped.split()[0].upper().startswith("REAL")


def _build_proposal(topic, data):
    """Turn the model's JSON into a change proposal for the given topic."""
    eid = db.generate_id("ent")
    entity = {
        "id": eid,
        "name": topic,                       # always the searched name
        "type": (data.get("type") or "concept"),
        "description": data.get("description"),
    }
    facts = []
    for fact in (data.get("facts") or []):
        if not isinstance(fact, dict):
            continue
        predicate = fact.get("predicate")
        if not predicate:
            continue
        facts.append({
            "subject_id": eid,
            "predicate": predicate,
            "value": fact.get("value"),
            "object_id": fact.get("object_id"),
        })
    return eid, {"entities": [entity], "facts": facts}


def generate(conn, topic, builder=None):
    """Invent and persist a fictional entry for ``topic``.

    Returns a dict::

        {"ok": bool, "entity": <entity dict or None>,
         "answer": <text or None>, "error": <text or None>}
    """
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "entity": None, "answer": None,
                "error": "No topic given."}
    if len(topic) > MAX_TOPIC_CHARS:
        topic = topic[:MAX_TOPIC_CHARS].strip()

    # If it already exists, don't invent it again.
    existing = db.find_entity(conn, topic)
    exact = [e for e in existing if e["name"].lower() == topic.lower()]
    if exact:
        return {"ok": True, "entity": exact[0], "answer": None, "error": None}

    if builder is None:
        import world_builder as builder

    last_note = None
    for attempt in range(2):
        base = _SYSTEM if attempt == 0 else _SYSTEM_HARD
        system = base.replace("{name}", topic)

        try:
            raw = builder.ask_ollama([
                {"role": "system", "content": system},
                {"role": "user",
                 "content": f'Create the AIWORLD entry named "{topic}".'},
            ])
        except Exception as e:
            return {"ok": False, "entity": None, "answer": None,
                    "error": f"{type(e).__name__}: {e}"}

        data = builder.extract_json(raw)
        if not isinstance(data, dict) or not data.get("description"):
            last_note = "The model did not return a usable entry."
            continue

        eid, proposal = _build_proposal(topic, data)
        result = db.apply_world_changes(conn, proposal)

        if not result.get("success"):
            # Word-list guard caught obvious real-world content.
            last_note = "Real-world content was refused: " + str(result.get("error"))
            if attempt == 0:
                continue
            return {"ok": False, "entity": None, "answer": data.get("description"),
                    "error": last_note}

        entity = db.get_entity(conn, eid)

        if _is_real_world(entity.get("name"), entity.get("description"), builder):
            db.delete_entity(conn, eid)
            last_note = "The description was actually a real-world thing."
            if attempt == 0:
                continue
            return {"ok": False, "entity": None,
                    "answer": entity.get("description"), "error": last_note}

        return {"ok": True, "entity": entity,
                "answer": entity.get("description"), "error": None}

    return {"ok": False, "entity": None, "answer": None,
            "error": last_note or "The model did not invent an entry."}
