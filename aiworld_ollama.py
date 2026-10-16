"""AIWORLD - a small, shared Ollama helper.

This is the one place AIWORLD talks to the local Ollama API
(``http://localhost:11434``).  The launcher and the LLM Manager use it to
discover, check and start Ollama the same way, and to list the installed
models.

Rules:

* It only ever contacts the local Ollama, never the real Internet.
* It never kills or restarts a running Ollama.
* It never changes the selected model (that is :mod:`aiworld_config`).
* The executable is discovered safely (``PATH`` first, then the usual install
  folders) instead of assuming one fixed path.
"""

import json
import os
import shutil
import subprocess
import time
import urllib.request

TAGS_URL = "http://localhost:11434/api/tags"
CHAT_URL = "http://localhost:11434/api/chat"


def is_running(timeout=2):
    """True when the Ollama API answers."""
    try:
        req = urllib.request.Request(TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models(timeout=5):
    """Installed models as a list of dicts, or ``[]`` if Ollama is unreachable.

    Each item has ``name`` (``name:tag``), ``size`` (bytes, if given),
    ``modified`` and ``family`` -- straight from Ollama, never invented.
    """
    try:
        req = urllib.request.Request(TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    models = []
    for m in data.get("models", []):
        name = (m.get("name") or "").strip()
        if not name:
            continue
        details = m.get("details") or {}
        models.append({
            "name": name,
            "size": m.get("size"),
            "modified": m.get("modified_at"),
            "family": details.get("family"),
        })
    return models


def names():
    """Just the model names, in Ollama's order."""
    return [m["name"] for m in list_models()]


def find_executable():
    """Locate the ollama executable without assuming one fixed directory."""
    path = shutil.which("ollama")
    if path:
        return path

    candidates = []
    for env in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        candidates.append(os.path.join(base, "Programs", "Ollama", "ollama.exe"))
        candidates.append(os.path.join(base, "Ollama", "ollama.exe"))
    for cand in candidates:
        if os.path.isfile(cand):
            return cand
    return None


def start(wait=60.0, poll=0.5):
    """Start ``ollama serve`` if it is not running.

    Returns ``(ok, message)``.  A running Ollama is left untouched.
    """
    if is_running():
        return True, "Ollama is already running."

    exe = find_executable()
    if not exe:
        return False, ("Ollama was not found on this PC. Install it from "
                       "https://ollama.com/download and try again.")

    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:  # noqa: BLE001 - report any launch failure clearly
        return False, f"Could not start Ollama: {e}"

    deadline = time.time() + wait
    while time.time() < deadline:
        if is_running():
            return True, "Ollama started."
        time.sleep(poll)
    return False, "Ollama did not answer in time."


def has_model(name):
    """True when ``name`` (or ``name:<tag>``) is installed."""
    name = (name or "").strip()
    if not name:
        return False
    for full in names():
        if full == name or full.startswith(name + ":"):
            return True
    return False


def preload(name, timeout=600):
    """Warm a model into memory with a one-token request.  True on success."""
    payload = json.dumps({
        "model": name,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "options": {"num_predict": 1},
    }).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False
