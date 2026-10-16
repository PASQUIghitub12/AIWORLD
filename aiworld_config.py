"""AIWORLD - the one place the local LLM is configured.

Every AIWORLD component that talks to Ollama (the World Builder, the on-demand
website generation and the World Resident) reads the model name from here, so
the LLM Manager can change it in exactly one place.

The choice is stored in ``aiworld_config.json`` next to the project.  The
effective model name is resolved, in order, from:

1. the ``model`` value in ``aiworld_config.json`` (what the LLM Manager writes),
2. the ``AIWORLD_MODEL`` environment variable (legacy / advanced override),
3. the ``RESIDENT_MODEL`` environment variable (legacy),
4. :data:`DEFAULT_MODEL` (the model AIWORLD shipped with).

Nothing here contacts Ollama; it only reads and writes the setting.  The file is
read fresh on every call, so a running program picks up a new choice on its next
request without being restarted.
"""

import json
import os
import sys

DEFAULT_MODEL = "qwen3:14b"
CONFIG_NAME = "aiworld_config.json"


def project_dir():
    """The AIWORLD project folder (where the ``.py`` files and ``world.db`` live)."""
    env = os.environ.get("AIWORLD_HOME")
    if env and os.path.isfile(os.path.join(env, "aiworld_web.py")):
        return env

    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    if os.path.isfile(os.path.join(base, "aiworld_web.py")):
        return base

    cwd = os.getcwd()
    if os.path.isfile(os.path.join(cwd, "aiworld_web.py")):
        return cwd
    return base


def config_path():
    """Full path of the configuration file (overridable with AIWORLD_CONFIG)."""
    override = os.environ.get("AIWORLD_CONFIG")
    if override:
        return override
    return os.path.join(project_dir(), CONFIG_NAME)


def load():
    """Return the configuration as a dict (empty when there is none yet)."""
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save(data):
    """Write the configuration dict atomically.  Returns ``True`` on success."""
    path = config_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def get_model():
    """The model name AIWORLD should use right now (resolved fresh)."""
    model = (load().get("model") or "").strip()
    if model:
        return model
    for var in ("AIWORLD_MODEL", "RESIDENT_MODEL"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return DEFAULT_MODEL


def set_model(name):
    """Persist ``name`` as the chosen model.  Returns ``True`` on success."""
    name = (name or "").strip()
    if not name:
        return False
    data = load()
    data["model"] = name
    return save(data)


def source():
    """Where the current model name comes from: config, environment or default."""
    if (load().get("model") or "").strip():
        return "config"
    for var in ("AIWORLD_MODEL", "RESIDENT_MODEL"):
        if (os.environ.get(var) or "").strip():
            return "environment"
    return "default"
