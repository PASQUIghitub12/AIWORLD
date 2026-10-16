"""AIWORLD - World Resident.

The World Resident is a *separate* AI role from the World Builder.  It lives
inside the fictional universe and knows only what it has read on the
simulated Internet (Omnipedia, the Herald, the Almanac, and the Farsight
search engine).

Guarantees that make it an honest resident rather than a second admin:

* It never imports :mod:`database` and has no canonical-database tools.
* Its only tools are ``list_sites``, ``search`` and ``browse`` against the
  local websites through :mod:`web_client`.
* It keeps its own conversation, independent from the World Builder.
* It remembers what it learned by browsing in :mod:`resident_memory` (its own
  file, never the canon).
* Its system prompt forbids real-world knowledge and requires it to say when
  something is unknown.

Run it with::

    python world_resident.py
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import aiworld_config
import web_client as web
import resident_memory as memory


# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

# The model name comes from aiworld_config (shared with the World Builder and
# the website generation); it is read fresh on every request.

OLLAMA_START_TIMEOUT = 30
SERVER_START_TIMEOUT = 30
MAX_TOOL_STEPS = 8
MAX_PAGE_CHARS = 6000


# ============================================================
# OLLAMA (kept local to this role)
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
    print("[SYSTEM] Avvio Ollama...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print("[ERRORE] Impossibile avviare Ollama:", e)
        return
    start = time.time()
    while time.time() - start < OLLAMA_START_TIMEOUT:
        if ollama_is_running():
            return
        time.sleep(0.5)


def ask_ollama(messages):
    payload = {
        "model": aiworld_config.get_model(),
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.4},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))["message"]["content"]
    except urllib.error.HTTPError as e:
        print("[OLLAMA ERROR]", e.read().decode("utf-8", errors="replace"))
        return None
    except Exception as e:
        print("[OLLAMA ERROR]", e)
        return None


def extract_json(text):
    if not text:
        return None
    text = re.sub(r" thinking.*?</think>", "", text.strip(),
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
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


# ============================================================
# LOCAL WEBSITE
# ============================================================

def ensure_net():
    """Make sure the simulated Internet is running, starting it if needed."""
    if web.is_reachable():
        return True

    print("[SYSTEM] La rete locale non è in esecuzione. Avvio i siti...")
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.Popen(
            [sys.executable, "aiworld_web.py"],
            cwd=here,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print("[ERRORE] Impossibile avviare la rete locale:", e)
        return False

    start = time.time()
    while time.time() - start < SERVER_START_TIMEOUT:
        if web.is_reachable():
            print("[SYSTEM] La rete locale è online.")
            return True
        time.sleep(0.5)

    print("[ERRORE] La rete locale non ha risposto entro il timeout.")
    return False


# ============================================================
# RESIDENT AGENT
# ============================================================

RESIDENT_PROMPT = """
You are a resident of AIWORLD, a completely fictional universe.

You are NOT the World Builder and NOT an administrator.
You have no access to any database of canonical facts.

Your ONLY knowledge of the world comes from the simulated Internet, which
you read through the tools below. The net has several sites; the central one
is Omnipedia, the encyclopedia of your world, but there are others
(a newspaper, a gazetteer, a search engine).

------------------------------------------------------------
TOOLS
------------------------------------------------------------

list_sites
List the websites on the net with their addresses.
Arguments: {}

search
Search the net (the search engine spans every site).
Arguments: {"query": "text"}

browse
Open a page by its address. You may give a full URL from list_sites or a
link printed on a page, or a path such as "/article/ent_zyphora".
Arguments: {"url": "http://omnipedia.localhost/article/ent_zyphora"}

------------------------------------------------------------
RULES
------------------------------------------------------------

- Answer ONLY using information you have actually read on the websites.
- Never use real-world knowledge; AIWORLD is not the real world.
- Before answering anything about an entity, person, place or fact you have
  not already read about, call search (and then browse the best page).
- Follow the LINKS printed on pages rather than guessing addresses.
- If the pages you read do not answer the question, reply honestly that the
  net does not say so and that you do not know. Never invent an answer, and
  never answer a different question instead.
- Quote or paraphrase what the pages say; do not add outside facts.
- Prefer searching first, then opening the most relevant article.

------------------------------------------------------------
OUTPUT PROTOCOL
------------------------------------------------------------

Return exactly one JSON object.

Tool call:
{
    "type": "tool_call",
    "tool": "search",
    "arguments": {"query": "Zyphora"}
}

Final answer:
{
    "type": "final",
    "answer": "Your answer, based only on what you read."
}

Do not output anything except the JSON object.
"""


def run_resident(question, session_messages):
    """Ask the resident one question.

    ``session_messages`` is the resident's working memory for this session:
    the full record of the earlier turns *including the pages it read*.
    Persisting the browsed pages is what lets the resident remember the world
    it has learned without ever being handed the database.

    The resident also has long-term memory (``resident_memory``) of things it
    learned in previous sessions, injected as a clearly-labelled memory block.
    Returns ``(answer, updated_session_messages)``.
    """
    remembered = memory.memory_block()
    system_text = RESIDENT_PROMPT
    if remembered:
        system_text += "\n\n" + remembered

    system = {"role": "system", "content": system_text}
    conv = [system] + list(session_messages) + [{"role": "user", "content": question}]

    visited = []

    for step in range(MAX_TOOL_STEPS):
        print(f"[RESIDENT] Elaborazione ({step + 1}/{MAX_TOOL_STEPS})...")
        response = ask_ollama(conv)

        if not response:
            return "Non ho ricevuto una risposta valida dal modello.", session_messages

        parsed = extract_json(response)
        if parsed is None:
            conv.append({"role": "assistant", "content": response})
            conv.append({"role": "user",
                         "content": "Rispondi usando ESATTAMENTE il protocollo JSON."})
            continue

        rtype = parsed.get("type")
        arguments = parsed.get("arguments", {}) or {}

        if rtype == "tool_call":
            tool = parsed.get("tool")

            if tool == "list_sites":
                sites = web.list_sites()
                result = {
                    "path": "(site directory)",
                    "status": 200,
                    "content": "\n".join(
                        f"- {s['name']} [{s['kind']}] {s['url']} — {s['description']}"
                        for s in sites
                    ),
                }
                label = "LIST_SITES"
            elif tool == "search":
                result = web.search(arguments.get("query", ""))
                label = f"SEARCH({arguments.get('query', '')})"
            elif tool == "browse":
                target = arguments.get("url") or arguments.get("path") or "/"
                result = web.browse(target)
                label = f"BROWSE({target})"
            else:
                result = {"status": 0, "content": "", "error": "unknown tool"}
                label = f"UNKNOWN({tool})"

            content = (result.get("content") or "")[:MAX_PAGE_CHARS]

            if result.get("status") == 200 and label != "LIST_SITES":
                visited.append(result.get("path"))

            print(f"[WEB] {label} -> status {result.get('status')}")

            conv.append({"role": "assistant",
                         "content": json.dumps(parsed, ensure_ascii=False)})
            conv.append({
                "role": "user",
                "content": (f"WEB PAGE ({result.get('path')}, "
                            f"status {result.get('status')}):\n{content}"),
            })
            continue

        if rtype == "final":
            answer = parsed.get("answer")
            if answer is None:
                return "Non ho prodotto una risposta.", session_messages

            # Keep the whole turn (question, pages read, answer) as memory.
            new_turn = conv[1 + len(session_messages):]
            session_messages = list(session_messages) + new_turn

            # Persist what it learned, with the pages it actually read.
            try:
                memory.remember(question, str(answer), visited)
            except Exception as e:
                print("[MEMORY WARNING]", e)

            return str(answer), session_messages

        conv.append({"role": "assistant",
                     "content": json.dumps(parsed, ensure_ascii=False)})
        conv.append({"role": "user",
                     "content": "Tipo non valido: usa tool_call oppure final."})

    return ("Non sono riuscito a trovare una risposta sulla rete "
            "entro il numero massimo di passaggi."), session_messages


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("AIWORLD - WORLD RESIDENT")
    print("=" * 60)

    start_ollama()
    if not ollama_is_running():
        print("[ERRORE] Ollama non è disponibile.")
        return

    if not web.is_reachable() and not ensure_net():
        return

    memory.init_memory()

    print(f"[SYSTEM] Modello: {aiworld_config.get_model()}")
    print("[SYSTEM] Il residente conosce il mondo solo leggendo la rete locale:")
    for s in web.list_sites():
        print(f"[SYSTEM]   {s['name']:<24} {s['url']}")
    print(f"[SYSTEM] Ricordi in memoria: {memory.count()}")
    print()
    print("Fai una domanda al residente.")
    print("Scrivi 'exit' per uscire.")
    print()

    history = []

    while True:
        try:
            question = input("resident> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit", "esci"}:
            break

        answer, history = run_resident(question, history)

        print()
        print("RESIDENTE:")
        print(answer)
        print()

    print("[SYSTEM] World Resident chiuso.")


if __name__ == "__main__":
    main()
