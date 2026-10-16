# Security Policy

## Scope and design

AIWORLD is a **local, offline** application. It is meant to run on your own
machine and to be reachable only from that machine:

- The websites (`aiworld_web.py`, `omnipedia.py`) bind to `127.0.0.1`.
- Ollama is contacted only at `http://localhost:11434`.
- The World Resident browses only the registered local sites; `web_client.py`
  refuses any other host, so it cannot reach the real Internet.
- No accounts, API keys, telemetry or cloud services are used.

## Please do not

- Do **not** expose the AIWORLD web server or the Ollama API to the public
  Internet (for example with port-forwarding, a public reverse proxy or binding
  to `0.0.0.0` without your own protection). They have no authentication and are
  not designed to be public.
- Do **not** commit secrets, tokens, `.env` files or personal data. The
  `.gitignore` already excludes the usual suspects.

## Reporting a vulnerability

If you find a security issue, please **do not** open a public issue with exploit
details. Instead, report it privately to the repository owner (open a minimal
issue asking for a private contact, or use the contact method on their profile).

Please include: a description, steps to reproduce, the affected file/route, your
OS and Python version, and any suggested fix.

## Supported versions

The latest `main` branch is the only supported version.

## Local data

`world.db`, `resident_memory.db` and `aiworld_config.json` stay on your machine
and are excluded from version control. Removing them is safe: the schema is
recreated on next start and the world regrows as you use it.
