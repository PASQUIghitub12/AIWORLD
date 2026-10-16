# Contributing to AIWORLD

Thanks for your interest. AIWORLD is a small, self-contained project; please keep
it that way.

## Ground rules

- **`world.db` is the single source of truth.** All database access goes through
  `database.py`. The websites are read-only; only the World Builder (and
  `world_generation.py`) may propose changes, and only through
  `database.apply_world_changes`, which validates them first.
- **The websites use no JavaScript.** Server-rendered HTML + CSS only. Any new
  page must work with JS disabled.
- **One implementation per concern.** There is exactly one database layer, one
  browsing client, one model configuration (`aiworld_config.py`). Do not
  duplicate these.
- **The World Resident has no database access.** It learns only by browsing the
  simulated Internet through `web_client.py`, which refuses any non-local host.
- **Never commit user data or secrets.** Keep `world.db`, `resident_memory.db`,
  `aiworld_config.json`, `backups/`, `AIWORLD.exe` and any `.env` out of git
  (they are already in `.gitignore`).

## Setting up

```bat
git clone https://github.com/OWNER/AIWORLD.git
cd AIWORLD
python -m pip install -r requirements.txt
ollama pull qwen3:14b
```

Run it with `start_aiworld.bat` (or `python aiworld_launcher.py`). See the README
for details.

## Making a change

1. Keep the change focused; avoid broad refactors.
2. Do not change an existing database's schema destructively; use
   `CREATE TABLE IF NOT EXISTS` and additive migrations only.
3. If you add a dependency, add it to `requirements.txt` and explain why. Do not
   list standard-library modules.
4. Update the README if you change behaviour or config.

## Testing

There is no formal test suite. Before opening a pull request, verify manually:

- `python aiworld_launcher.py --check` reports Python, Ollama and the model as found.
- `python aiworld_web.py`, then open `http://omnipedia.localhost/` and browse a few
  articles and the other sites.
- Searching a brand-new word on Omnipedia creates a fictional article and shows it.
- The World Builder answers and can create a fact; the site then shows it.
- `PRAGMA integrity_check` on `world.db` is `ok`.

## Reporting issues

Open an issue on the GitHub repository with your OS, Python version, the model
you selected, the exact command you ran, and the full error text. Do **not**
attach your `world.db` unless you are happy to share its (fictional) contents.

## Code style

Plain, readable Python. Keep the existing header/comment style. No emojis in code
or docs unless there is a clear reason.
