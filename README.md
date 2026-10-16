# AIWORLD

**AIWORLD is a fully local, completely fictional universe that writes itself.**

It runs entirely on your own Windows PC with Python, SQLite and
[Ollama](https://ollama.com) — no cloud AI, no accounts, no telemetry, and no
real Internet. A local language model invents a world; a SQLite database holds
it as canon; a small set of fictional websites serve it; and a second AI "lives"
inside that world and learns about it only by browsing those sites.

> The rule of the project: **`world.db` is the single source of truth.** The
> websites never invent facts and never write; the resident never peeks at the
> database.

---

## What is AIWORLD?

AIWORLD is a self-contained fictional universe that is **generated live** by a
local LLM and served as a tiny simulated Internet, all on your own PC. Nothing
is downloaded from, or sent to, the real Internet.

It has four parts:

1. **World Builder** — the administrator AI. It answers questions about the
   world and is the only thing that may create or change canonical facts.
2. **The simulated Internet** — four fictional, in-world websites, all
   server-rendered HTML + CSS with **no JavaScript**, all reading the canonical
   database:
   - **Omnipedia** — the encyclopedia of the world.
   - **The Zyphoran Herald** — the world's newspaper and world desk.
   - **Navigator's Almanac** — a gazetteer of places and the routes between them.
   - **Farsight Search** — the world's search engine, spanning every site.
2. **World Resident** — an AI that *lives inside* the world and learns about it
   only by browsing the simulated Internet. It has no access to the database.
3. **Canonical database** (`world.db`) — the single source of truth.

The rule of the project: **the SQLite database is the canon.** The websites never
invent facts and never write; the resident never peeks at the database.

### What Omnipedia does

Omnipedia is the encyclopedia of the world, served at
**<http://omnipedia.localhost/>**. It is server-rendered HTML/CSS with **no
JavaScript**, and it reads *only* through `database.py`:

- **Home** lists every article, grouped by type, with a live count and the latest
  timeline events.
- **Articles** show an entity's description, its facts and its links to other
  entities (click through the world as a web).
- **Categories** list every entity of a type.
- **Timeline** shows the world's events.
- **Search** looks across entities, facts and events — and if the thing you
  searched for does not exist yet, Omnipedia **invents it** (see below) and takes
  you straight to the new article.

Omnipedia can also run on its own (`python omnipedia.py`) on `127.0.0.1:5000`.

---

## Architecture

```
                     ┌──────────────────────────┐
   Ollama (local) ───│  world_builder.py        │  writes (validated)
   qwen3:14b (or ────│  aiworld_config.py       │──────────┐
   the model you ────│  world_generation.py     │          ▼
   choose)           └──────────────────────────┘   ┌─────────────┐
                                                    │  database.py │
   world_resident.py ── web_client.py ── HTTP ──┐   │  world.db    │
   (browse-only, no DB)                          │   └─────────────┘
                                                 ▼          ▲ reads
                                    aiworld_web.py (port 80, Host routing)
                                    Omnipedia · Herald · Almanac · Farsight
```

- **`database.py`** is the single data-access layer (schema, reads, validated
  writes). Everything uses it; the websites can only read.
- **`aiworld_config.py`** is the single place the LLM is configured (see
  "Changing the model").
- **`aiworld_web.py`** serves all four sites at once: by name on port 80 (routed
  by the HTTP `Host` header) and on each site's own port as a fallback.
- **`web_client.py`** is the resident's browser: it fetches *only* registered
  local sites and refuses any other host.

---

## Requirements

| Dependency | Notes |
|------------|-------|
| Windows 10/11 | The launcher and scripts are Windows-oriented. The Python code itself is portable. |
| Python 3 | Tested on 3.14. `tkinter` (for the LLM Manager) ships with the standard Windows Python installer. |
| Flask | The local web servers. `Jinja2`, `Werkzeug` and friends come with it. |
| Ollama | The local LLM runtime. Install from https://ollama.com/download |
| At least one model | e.g. `ollama pull qwen3:14b` (about 9 GB, one-time). Any installed model works. |

No API keys, no accounts, no cloud services, no telemetry.

---

## Install

```bat
git clone https://github.com/<you>/AIWORLD.git
cd AIWORLD
python -m pip install -r requirements.txt
ollama pull qwen3:14b
```

Then start AIWORLD (below). On first run the database is created empty and grows
as you use it.

A convenience script `setup.bat` does the pip step and checks Python/Ollama.

---

## Start AIWORLD

### One click (recommended)

Double-click **`AIWORLD.exe`** (or run `start_aiworld.bat`). A menu appears:

```
  1) Everything  (Ollama + net + Builder + Resident)
  2) The simulated Internet only (4 websites)
  3) World Builder only
  4) World Resident only
  5) Ollama only
  6) Stop everything AIWORLD started
  7) Environment check
  8) Add or change LLM
  0) Quit
```

Option **1** starts Ollama (hidden if it is not already up), the four websites,
the World Builder and the World Resident, then opens
<http://omnipedia.localhost/>. Option **8** opens the LLM Manager (next section).

`AIWORLD.exe` is a thin wrapper (built from `aiworld_launcher.py`) that runs the
project's Python scripts; it never writes to the database itself. Flags:

```
AIWORLD.exe --all | --net | --builder | --resident | --ollama
AIWORLD.exe --llm          open "Add or change LLM"
AIWORLD.exe --check        check the environment and exit
AIWORLD.exe --stop         stop everything this launcher started
AIWORLD.exe --no-browser   --preload
```

To rebuild the exe after editing the launcher (needs `pip install pyinstaller`):

```bat
python -m PyInstaller --onefile --console --name AIWORLD --distpath . aiworld_launcher.py
```

### From a terminal

```bat
python aiworld_web.py       :: all four websites
python world_builder.py     :: the administrator AI
python world_resident.py    :: the in-world AI (starts the net if needed)
```

You can run the websites and either AI at the same time.

---

## Changing the model (Add or change LLM)

AIWORLD uses **one** model, chosen in **one** place. To change it:

1. Open AIWORLD and choose **8) Add or change LLM** (or run
   `python aiworld_llm_manager.py`, or `AIWORLD.exe --llm`).
2. The **AIWORLD — LLM Manager** window opens. It shows whether Ollama is
   running (and starts it in the background if it is not — without killing an
   Ollama that is already up), and lists the models Ollama actually has.
3. Select a model and press **Select and apply**. The choice is saved and used
   from the next request on; **Refresh** re-reads the list; **Back to main menu**
   returns.

Only **installed** models are listed; the manager never downloads models. The
choice is stored in `aiworld_config.json` next to the project:

```json
{ "model": "qwen3:14b" }
```

Every component that talks to Ollama — the World Builder, on-demand website
generation, and the World Resident — reads this file fresh on each request, so a
change applies to the next request without restarting anything.

**Advanced / no config file:** the environment variables `AIWORLD_MODEL` (and the
legacy `RESIDENT_MODEL`) are honoured when `aiworld_config.json` has no `model`.
Resolution order: config file → `AIWORLD_MODEL` → `RESIDENT_MODEL` →
`qwen3:14b`.

**How to confirm the selected model is really used:** change it in the LLM
Manager, then ask the World Builder something (its console prints
`[SYSTEM] Modello: <name>` at startup, and every `/api/chat` request carries
`"model": "<name>"`). `AIWORLD.exe --check` prints the model and where the choice
came from. A wrong model name produces a clear `[OLLAMA ERROR] ... model ... not
found` instead of a crash.

---

## Accessing Omnipedia locally

Open **<http://omnipedia.localhost/>**.

The four sites are addressed by `.localhost` names:

| Site | Address |
|------|---------|
| Omnipedia | <http://omnipedia.localhost/> |
| The Zyphoran Herald | <http://zyphoranherald.localhost/> |
| Navigator's Almanac | <http://navigatorsalmanac.localhost/> |
| Farsight Search | <http://farsight.localhost/> |

`aiworld_web.py` serves all of them **on port 80**, routing each request by the
HTTP `Host` header. The `.localhost` names resolve to your PC in every browser by
design (RFC 6761) — **no hosts-file edit, no DNS change, no admin rights**. Each
site also answers on its own port as a fallback
(`http://127.0.0.1:5000/` … `:5003/`).

### Local vs public hosting — important

`omnipedia.localhost` is a **local development domain**. Browsers resolve it to
your own PC; it is *not* a public Internet domain and will **not** become reachable
from the Internet when you push this code to GitHub. Pushing the repository only
shares the source code.

This project is designed to run entirely on one machine: do **not** expose the
local Ollama API or the local web server to the public Internet.

---

## How the world grows

1. In the World Builder, ask it to create or change something.
2. The model returns a **change proposal** (JSON) — it never writes directly.
3. `database.apply_world_changes` validates it: referenced entities must exist,
   duplicate names/aliases are rejected, and every change is logged.
4. On the next page load every site reflects the new data, because every page is
   generated live from `world.db`.

### Creating something straight from a website

Search Omnipedia or Farsight for something that does not exist yet (e.g.
`Zephyrion`): it is created **automatically**. The site asks the model to invent a
fictional in-world entry, saves it through the same validated path, and redirects
to the new article. There is no confirmation step, so a mistyped search becomes a
real (fictional) entry; it happens once per search and then redirects.

The world is kept fictional by **two layers**:

1. A **word-list guard** (`database.py`) refuses descriptions/facts that carry an
   unmistakable real-world tell (a real company/service name, or phrasing like
   "in the real world"). An entity's own name is ignored, so a topic that *is* a
   real brand is not refused for containing its own name.
2. A **semantic verifier** (`world_generation.py`) makes a second model call to
   check whether the description repeats a real thing's traits; if so, the draft
   is deleted and invented again.

The inventing prompt only ever asks for a fictional **place, realm, creature,
being, phenomenon, order, faction, artifact or custom**, and forbids products,
apps, services, companies and real-style people.

### How the resident learns

The World Resident has no database access. Each question runs a small loop: it
may `list_sites`, `search` (Farsight, spanning all sites) or `browse` a page; it
reads readable text and links through `web_client.py`; and it answers **only** from
what it read, or says honestly that the net does not say. It remembers what it
learned across sessions in `resident_memory.db` (never the canon).

---

## Configuration and data files

| File | What it is | In Git? |
|------|-----------|---------|
| `world.db` | **Canonical world data** (your generated universe). Created empty on first run. | No — per-machine data |
| `resident_memory.db` | The resident's own memory. | No — per-machine data |
| `aiworld_config.json` | Your chosen Ollama model. | No — machine-specific |
| `aiworld_config.py` | The **code** that defines how the model is chosen (default + env). | Yes |
| `requirements.txt` | Python dependencies. | Yes |
| `backups/` | Your local world/code snapshots. | No |

`app.db` and `*.backup` are unused leftovers and are left untouched.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Browser cannot open `omnipedia.localhost` | Make sure the net is running (option 2). If port 80 is taken, use the fallback `http://127.0.0.1:5000/`. Try a recent Chrome/Edge/Firefox. |
| `[OLLAMA ERROR] ... model ... not found` | The chosen model is not installed. Open **Add or change LLM** and pick an installed one, or `ollama pull <model>`. |
| Ollama not running | Option 5, or the LLM Manager starts it for you. Install from https://ollama.com/download if missing. |
| Console shows `?` for accents | Run `set PYTHONIOENCODING=utf-8` first (the `.bat` files already do). |
| "database is locked" | Should not happen (a 30 s busy timeout is set). Close extra copies of the AI if it does. |
| Python not found by the exe | Install Python 3 and put it on `PATH`, or set `AIWORLD_HOME` to the project folder. |
| Model manager window does not open | `tkinter` is missing (rare on Windows). Reinstall Python with the standard installer, or set the model by editing `aiworld_config.json`. |

---

## Contributing

Contributions are welcome. Please read `CONTRIBUTING.md`. In short: keep the
database as the single source of truth, keep the websites read-only and free of
JavaScript, keep one implementation per concern, and never commit user data
(`world.db`, `resident_memory.db`, `aiworld_config.json`, `backups/`).

Report bugs and request features with the issue tracker on the GitHub repository:
https://github.com/<you>/AIWORLD/issues

---

## Security

This is a local, offline application. See `SECURITY.md`. Do not expose the local
Ollama API or the local web server to the public Internet.

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE). You may use, modify
and redistribute it, including commercially, provided the copyright notice is
kept. There is no warranty.

---

## Roadmap (not implemented yet)

These are ideas, clearly **not** part of the current build:

- More fictional websites (forums, corporations) — add a module under `sites/`
  and list it in `sites/registry.py`.
- Richer resident browsing (following more link shapes, pagination).
- An optional, explicit "download a model" action inside the LLM Manager with
  size/disk information.
