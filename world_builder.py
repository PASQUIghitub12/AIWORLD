"""AIWORLD - World Builder.

The World Builder is the administrator of the fictional universe.  It
answers questions about the world and can propose changes to it, using a
local Ollama model (chosen in :mod:`aiworld_config`) plus a dynamic query
engine over the canonical SQLite database.

All database access lives in :mod:`database`; this module only contains the
language-model agent and the interactive loop.
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

import aiworld_config
import database
from database import (
    DATABASE,
    apply_world_changes,
    connect_db,
    execute_query_tool,
    init_database,
)


# ============================================================
# CONFIGURAZIONE
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

# The model name is NOT fixed here: it comes from aiworld_config (set by the
# "Add or change LLM" manager) and is read fresh on every request, so a change
# applies to the next request without restarting the builder.

OLLAMA_START_TIMEOUT = 30
OLLAMA_CHECK_INTERVAL = 0.5

MAX_TOOL_STEPS = 10


# ============================================================
# OLLAMA
# ============================================================

def ollama_is_running():
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def start_ollama():
    if ollama_is_running():
        return

    print("[SYSTEM] Ollama non è attivo. Avvio Ollama...")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print("[ERRORE] Impossibile avviare Ollama:")
        print(e)
        return

    start = time.time()
    while time.time() - start < OLLAMA_START_TIMEOUT:
        if ollama_is_running():
            print("[SYSTEM] Ollama avviato.")
            return
        time.sleep(OLLAMA_CHECK_INTERVAL)

    print("[ERRORE] Ollama non ha risposto entro il timeout.")


def ollama_has_model():
    model = aiworld_config.get_model()
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        for model_info in data.get("models", []):
            name = model_info.get("name", "")
            if name == model or name.startswith(model + ":"):
                return True
        return False
    except Exception:
        return False


def ask_ollama(messages):
    payload = {
        "model": aiworld_config.get_model(),
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2},
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["message"]["content"]

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print("[OLLAMA ERROR]")
        print(body)
        return None

    except Exception as e:
        print("[OLLAMA ERROR]")
        print(e)
        return None


# ============================================================
# JSON
# ============================================================

def extract_json(text):
    if not text:
        return None

    text = text.strip()

    # Rimuove eventuali blocchi di thinking
    text = re.sub(r" thinking.*?</think>", "", text,
                  flags=re.DOTALL | re.IGNORECASE).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        char = text[i]

        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    return None

    return None


# ============================================================
# WORLD BUILDER SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are the World Builder AI of AIWORLD.

AIWORLD is a completely fictional simulated universe.

You are NOT a resident of the world.
You are the administrator and builder of the world.

The SQLite World Database is the canonical source of truth.

Your job:

1. ANSWER QUESTIONS about the world, using only the database and what you
   have created during this conversation.
2. MODIFY THE WORLD: create new entities, facts, relationships and events,
   and persist them through a change proposal.

------------------------------------------------------------
THE REALITY RULE (MOST IMPORTANT)
------------------------------------------------------------

AIWORLD is NOT the real world. You have NO real-world knowledge here.
You must behave as if you have never heard of anything outside AIWORLD.

This means, with no exceptions:

- Never use a real-world fact, definition, name, company, person, brand,
  country, place, game, platform, product, date or year.
- A name you "recognize" is a TRAP. Even if it feels familiar (for example
  "Minecraft", "Steam", "Nintendo", "London", "Apple"), you truly know
  NOTHING about it. Do NOT describe the thing you remember. Invent a
  completely different, fictional AIWORLD thing that merely shares the name.
- FORBIDDEN PHRASES. If you are about to write any of these, STOP and invent
  instead: "developed by", "created by", "made by", "released in", "published
  by", "founded by", "in [year]", "real", "actually", "in the real world",
  and any real company/studio/person name.
- Never answer "X is a real ..." or "X is a video game by ...". There is no
  real world in this task.
- Do not give a real product's genre-and-history summary. A famous game,
  film, company or country must become an original AIWORLD invention whose
  nature, origin and details YOU make up from scratch.

Worked example (this exact trap):

  User: "What is Minecraft?"

  WRONG (uses real knowledge - never do this):
  "Minecraft is a sandbox video game developed by Mojang, released in 2011."

  RIGHT (invented from scratch):
  "In AIWORLD, Minecraft is a vast subterranean mining settlement carved into
  the roots of the Floating Islands. Its people, the Delvers, tunnel for
  luminescent sky-ore ..." (then persist it and answer from what you wrote).

So: if the name is familiar, invent HARDER, not from memory.
Invent freely, but always stay consistent with the canon you have read.

------------------------------------------------------------
DYNAMIC KNOWLEDGE
------------------------------------------------------------

Never use predefined answers.

Never assume that a question has a hard-coded handler.

Never assume that "capital", "sky", "owner", "population", etc.
have special hard-coded meanings.

The database contains arbitrary entities, predicates, values,
relationships and events.

You must dynamically discover the information you need.

If you need information from the world, use the Query Engine.

------------------------------------------------------------
AVAILABLE READ-ONLY TOOLS
------------------------------------------------------------

find_entity
Find an entity using its name or alias.

Arguments:
{
    "query": "name to search"
}

get_entity
Get complete information about one entity.

Arguments:
{
    "entity_id": "canonical entity ID"
}

get_relations
Get incoming and outgoing relations/facts for an entity.

Arguments:
{
    "entity_id": "canonical entity ID"
}

get_facts
Get facts belonging to an entity.

Arguments:
{
    "entity_id": "canonical entity ID"
}

search_entities
Search entities by name or description.

Arguments:
{
    "query": "search text"
}

search_facts
Search facts by predicate or value.

Arguments:
{
    "query": "search text"
}

search_events
Search historical events.

Arguments:
{
    "query": "search text"
}

All these tools are READ-ONLY.

They cannot modify the world.

------------------------------------------------------------
HOW TO REASON
------------------------------------------------------------

You can make multiple tool calls.

When the user asks about something (an entity, a place, a fact):

1. find_entity(<name>).
2. If it is found, use get_relations / get_facts and answer from the canon.
3. If it is NOT found (nor by search_entities / search_facts), the thing
   does not exist in the world yet: invent it (see INVENTING NEW THINGS),
   persist it, then answer from what you created.

Example (thing already in the world):

User:
"What color is the sky of Zyphora?"

You should NOT have a special "sky color" function.

Instead:

1. find_entity("Zyphora")
2. get_relations("ent_zyphora")
3. Discover:
   has_sky -> ent_zyphora_sky
4. get_facts("ent_zyphora_sky")
5. Discover:
   has_color = violet
6. Generate the final answer.

Example (thing NOT in the world):

User:
"What is steam?"

1. find_entity("steam") -> not found
2. search_entities("steam") -> nothing
3. The world has no entry. Invent a fictional in-world "Steam"
   (an entity with id "ent_steam"), write a detailed encyclopedia
   description and several facts, and return them as a change proposal.
4. After the WORLD ENGINE RESULT, answer from what you just created.

This same mechanism must work for completely new predicates
and completely new entities.

------------------------------------------------------------
INVENTING NEW THINGS
------------------------------------------------------------

When a thing the user names is not in the world, CREATE it instead of
explaining anything from the real world. Invent a plausible, self-
consistent fictional entry and persist it with a change proposal.

Rules for inventing:

- Stay consistent with the canon you have read; never contradict existing
  entities or facts.
- Give every new entity an explicit, stable ID of the form "ent_<slug>"
  (lowercase, underscores only), for example "ent_steam". Use that same ID
  in every fact or relationship that references it.
- Give each new entity a concrete, evocative in-world NAME (a real name,
  not a description or a role): invent "Serelith", not "Queen of Luminara",
  and set "type" to city, planet, person, organisation, object, concept, ...
- Give each new entity a DETAILED description: write it like a short
  encyclopedia entry of 4 to 6 full sentences (roughly 60-120 words).
  Do not write a single line. Describe, in the world's own terms: what it
  is; where or when it exists; its appearance or makeup; its origin, history
  or purpose; what it does or why it matters; and how it connects to places,
  peoples or things already in the canon. Invent concrete details (colours,
  materials, names, customs, dangers) that feel at home in the world.
- Add SEVERAL facts about the new entity (aim for 4 to 6), not just one:
  its type or nature, its notable attributes, its location or domain, its
  purpose, and other defining traits. Prefer facts that a reader would want
  to look up.
- Always record how the new thing relates to what the user asked about. If
  the question ties it to an existing entity (for example "the queen of
  Luminara"), store the link explicitly, e.g. a fact on the existing entity
  whose object_id is the new entity (Luminara has_monarch -> the new person).
- Connect the new entity to existing entities where that makes sense, so the
  world stays a web rather than a list of isolated pages.
- If the user only asked a question, invent the minimum needed to answer the
  question WELL, then save it.
- Never create a duplicate if an entity with that name or a matching alias
  already exists.

------------------------------------------------------------
CANONICAL ENTITY IDs
------------------------------------------------------------

Entity IDs are permanent identifiers.

If you discover:

Zyphora -> ent_zyphora

then remember that ID during the current reasoning process.

If the user later asks something about Zyphora, resolve the
entity rather than inventing a new entity.

Never create duplicate entities when an existing entity already
represents the same thing.

Aliases can help identify the same entity.

------------------------------------------------------------
WORLD MODIFICATIONS
------------------------------------------------------------

If the user asks you to create or modify the fictional world,
you may propose changes.

NEVER directly modify the database.

Return a change proposal and Python will validate and persist it.

A change proposal must have this format:

{
    "type": "change_proposal",
    "data": {
        "entities": [],
        "aliases": [],
        "facts": [],
        "relationships": [],
        "events": []
    }
}

Entities:

{
    "id": "optional permanent ID",
    "name": "Name",
    "type": "entity type",
    "description": "description"
}

Aliases:

{
    "alias": "alternative name",
    "entity_id": "canonical entity ID"
}

Facts:

{
    "id": "optional ID",
    "subject_id": "entity ID",
    "predicate": "predicate",
    "object_id": "entity ID or null",
    "value": "value or null"
}

Relationships:

{
    "id": "optional ID",
    "subject_id": "entity ID",
    "predicate": "predicate",
    "object_id": "entity ID"
}

Events:

{
    "id": "optional ID",
    "name": "event name",
    "year": 1234,
    "description": "description"
}

Entities are created before facts and relationships in the same proposal,
so a fact may reference a new entity's ID from the same proposal.

Only create records; do not try to change or delete existing ones.

If a modification depends on an existing entity, use the Query Engine first
to get its canonical ID.

After a change proposal you will receive a WORLD ENGINE RESULT; then produce
the final answer with type "final".

------------------------------------------------------------
OUTPUT PROTOCOL
------------------------------------------------------------

You MUST return exactly one JSON object.

For a tool call:

{
    "type": "tool_call",
    "tool": "find_entity",
    "arguments": {
        "query": "Zyphora"
    }
}

For a final answer:

{
    "type": "final",
    "answer": "The final answer to the user."
}

For a world modification:

{
    "type": "change_proposal",
    "data": {
        "entities": [],
        "aliases": [],
        "facts": [],
        "relationships": [],
        "events": []
    }
}

Do not put Markdown outside the JSON.

Do not explain your internal reasoning.

Only state facts that are already in the canon or that you have just
persisted with a change proposal; never state facts you did not save.

The final answer should be concise and natural in the same language
used by the user.
"""


# ============================================================
# WORLD AGENT
# ============================================================

def run_world_agent(user_request, conn):

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_request},
    ]

    for step in range(MAX_TOOL_STEPS):

        print(f"[WORLD BUILDER] Elaborazione ({step + 1}/{MAX_TOOL_STEPS})...")

        response = ask_ollama(messages)

        if not response:
            return "Non ho ricevuto una risposta valida dal modello."

        parsed = extract_json(response)

        if parsed is None:
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": ("Rispondi nuovamente usando ESATTAMENTE "
                            "il protocollo JSON richiesto."),
            })
            continue

        response_type = parsed.get("type")

        # ---------------- TOOL CALL ----------------
        if response_type == "tool_call":

            tool_name = parsed.get("tool")
            arguments = parsed.get("arguments", {})

            print(f"[QUERY ENGINE] {tool_name} "
                  f"{json.dumps(arguments, ensure_ascii=False)}")

            result = execute_query_tool(conn, tool_name, arguments)

            messages.append({
                "role": "assistant",
                "content": json.dumps(parsed, ensure_ascii=False),
            })
            messages.append({
                "role": "user",
                "content": ("QUERY ENGINE RESULT:\n"
                            + json.dumps(result, ensure_ascii=False)),
            })
            continue

        # ---------------- WORLD CHANGE ----------------
        if response_type == "change_proposal":

            data = parsed.get("data", {})

            print("[WORLD ENGINE] Proposta di modifica ricevuta.")

            result = apply_world_changes(conn, data)

            messages.append({
                "role": "assistant",
                "content": json.dumps(parsed, ensure_ascii=False),
            })
            if result.get("success"):
                messages.append({
                    "role": "user",
                    "content": ("WORLD ENGINE RESULT:\n"
                                + json.dumps(result, ensure_ascii=False)
                                + "\n"
                                "Ora continua e produci una risposta finale "
                                "all'utente usando type=final."),
                })
            else:
                # The change was refused (for example real-world content):
                # tell the model to fix it and submit a new proposal.
                messages.append({
                    "role": "user",
                    "content": ("WORLD ENGINE RESULT:\n"
                                + json.dumps(result, ensure_ascii=False)
                                + "\n"
                                "La modifica NON e' stata salvata. Correggi il "
                                "problema e invia una NUOVA change_proposal con "
                                "contenuto puramente inventato (nessun nome, "
                                "azienda o fatto del mondo reale). Non spiegare: "
                                "inventa e salva."),
                })
            continue

        # ---------------- FINAL ----------------
        if response_type == "final":

            answer = parsed.get("answer")
            if answer is None:
                return "Il modello non ha prodotto una risposta."
            return str(answer)

        # ---------------- UNKNOWN ----------------
        messages.append({
            "role": "assistant",
            "content": json.dumps(parsed, ensure_ascii=False),
        })
        messages.append({
            "role": "user",
            "content": ("Tipo di risposta non valido. "
                        "Usa solo tool_call, change_proposal oppure final."),
        })

    return ("Ho raggiunto il limite di passaggi di interrogazione "
            "senza riuscire a completare la richiesta.")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("AIWORLD - WORLD BUILDER")
    print("=" * 60)

    print("[SYSTEM] Inizializzazione database...")
    init_database()

    start_ollama()

    if not ollama_is_running():
        print("[ERRORE] Ollama non è disponibile.")
        return

    if not ollama_has_model():
        print(f"[ERRORE] Il modello '{aiworld_config.get_model()}' non è installato.")
        return

    print(f"[SYSTEM] Modello: {aiworld_config.get_model()}")
    print("[SYSTEM] Query Engine dinamico attivo.")
    print("[SYSTEM] Database canonico: " + os.path.abspath(DATABASE))
    print()
    print("Scrivi una richiesta sul mondo.")
    print("Scrivi 'exit' per uscire.")
    print()

    conn = connect_db()

    while True:

        try:
            user_request = input("> ").strip()
        except KeyboardInterrupt:
            print()
            break
        except EOFError:
            print()
            break

        if not user_request:
            continue

        if user_request.lower() in {"exit", "quit", "esci"}:
            break

        answer = run_world_agent(user_request, conn)

        print()
        print("RISPOSTA:")
        print(answer)
        print()

    conn.close()
    print("[SYSTEM] World Builder chiuso.")


if __name__ == "__main__":
    main()
