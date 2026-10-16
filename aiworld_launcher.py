"""AIWORLD - one-click launcher.

Double-click ``AIWORLD.exe`` (built from this file with PyInstaller) to bring
the whole world up at once:

* **Ollama** - the local model runtime (started hidden if it is not already up).
* **The simulated Internet** - all four websites (Omnipedia, the Herald, the
  Almanac and Farsight Search).
* **The World Builder** - the administrator AI, in its own window.
* **The World Resident** - the in-world AI, in its own window.

Then it opens the browser on Omnipedia.

The sites answer by name on port 80 (``http://omnipedia.localhost/`` ...); the
``.localhost`` names need no hosts-file or DNS setup at all, since every browser
resolves them to this PC by design.  They also answer on 127.0.0.1:5000-5003.

The launcher is only a convenience wrapper: it starts the project's own scripts
(``aiworld_web.py``, ``world_builder.py``, ``world_resident.py``) with the same
Python interpreter the project uses.  It never writes to the database itself.

Command line (all optional)::

    AIWORLD.exe                 show the menu
    AIWORLD.exe --all           start Ollama + net + Builder + Resident
    AIWORLD.exe --net           start only the simulated Internet
    AIWORLD.exe --builder       start only the World Builder
    AIWORLD.exe --resident      start only the World Resident
    AIWORLD.exe --ollama        start only Ollama (and check the model)
    AIWORLD.exe --llm           open the "Add or change LLM" window
    AIWORLD.exe --check         check the environment and exit
    AIWORLD.exe --stop          stop everything this launcher started
    AIWORLD.exe --no-browser    do not open the browser
    AIWORLD.exe --preload       warm the model into memory at start
"""

import glob
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

import aiworld_config
import aiworld_ollama


# ============================================================
# CONFIGURATION
# ============================================================

# The model name is not fixed here: it is read from aiworld_config (the LLM
# Manager writes it) so the launcher, the builder and the resident agree.
OLLAMA_TAGS_URL = aiworld_ollama.TAGS_URL
OLLAMA_CHAT_URL = aiworld_ollama.CHAT_URL

SITE_NAMES = (
    "omnipedia.localhost",
    "zyphoranherald.localhost",
    "navigatorsalmanac.localhost",
    "farsight.localhost",
)

OMNIPEDIA_URL = "http://omnipedia.localhost/"
WEB_PORTS = (5000, 5001, 5002, 5003)

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

RUN_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AIWORLD"
)
RUN_FILE = os.path.join(RUN_DIR, "run.json")


# ============================================================
# LOCATE THINGS
# ============================================================

def home_dir():
    """The AIWORLD folder: where the project's .py files live."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    candidates = [base, os.environ.get("AIWORLD_HOME", ""), os.getcwd()]
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "aiworld_web.py")):
            return candidate
    return base


def _python_ok(cmd):
    try:
        out = subprocess.run(
            list(cmd) + ["--version"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return False
    text = ((out.stdout or "") + (out.stderr or "")).lower()
    return "python" in text


def find_python():
    """Return a command list that runs Python, or None."""
    candidates = []
    for name in ("python", "python3"):
        path = shutil_which(name)
        if path:
            candidates.append([path])
    py = shutil_which("py")
    if py:
        candidates.append([py, "-3"])

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        pattern = os.path.join(local, "Programs", "Python", "Python*", "python.exe")
        candidates.extend([[p] for p in sorted(glob.glob(pattern))])

    for cmd in candidates:
        if _python_ok(cmd):
            return cmd
    return None


def shutil_which(name):
    import shutil
    return shutil.which(name)


def find_ollama():
    return aiworld_ollama.find_executable()


# ============================================================
# PROBES
# ============================================================

def port_in_use(port, host="127.0.0.1", timeout=0.6):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def net_reachable():
    return port_in_use(80) or port_in_use(5000)


def ollama_running(timeout=2):
    return aiworld_ollama.is_running(timeout)


def ollama_models():
    return aiworld_ollama.names()


def has_model(name):
    return aiworld_ollama.has_model(name)


def preload_model(name):
    return aiworld_ollama.preload(name)


# ============================================================
# RUN STATE (so we can stop what we started)
# ============================================================

def load_run():
    try:
        with open(RUN_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"pids": {}, "ollama_pid": None}


def save_run(state):
    os.makedirs(RUN_DIR, exist_ok=True)
    with open(RUN_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def pid_alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
        )
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def kill_pid(pid):
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


# ============================================================
# STARTING COMPONENTS
# ============================================================

def start_ollama():
    """Start ``ollama serve`` hidden if it is not already up. Returns pid."""
    if ollama_running():
        print("[OLLAMA] already running.")
        return None
    exe = find_ollama()
    if not exe:
        print("[OLLAMA] not found. Install it from https://ollama.com/download")
        return None
    print("[OLLAMA] starting...")
    proc = subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    start = time.time()
    while time.time() - start < 60:
        if ollama_running():
            print("[OLLAMA] ready.")
            return proc.pid
        time.sleep(0.5)
    print("[OLLAMA] did not answer in time; continuing anyway.")
    return proc.pid


def start_script(label, python, home, script):
    """Start one project script in its own console window. Returns pid."""
    print(f"[START] {label} ({script})")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        list(python) + [script],
        cwd=home, env=env,
        creationflags=CREATE_NEW_CONSOLE,
    )
    return proc.pid


def wait_for_net(seconds=45):
    start = time.time()
    while time.time() - start < seconds:
        if net_reachable():
            return True
        time.sleep(0.5)
    return False


# ============================================================
# STARTING COMPONENTS
# ============================================================

def action_check(home):
    print("=" * 60)
    print("AIWORLD environment check")
    print("=" * 60)
    print(f"Project folder : {home}")
    ok = os.path.isfile(os.path.join(home, "aiworld_web.py"))
    print(f"  aiworld_web.py : {'found' if ok else 'MISSING'}")
    print(f"Python         : {find_python() or 'NOT FOUND'}")
    print(f"Ollama         : {find_ollama() or 'NOT FOUND'}")
    print(f"  server       : {'running' if ollama_running() else 'not running'}")
    current = aiworld_config.get_model()
    print(f"  model {current:<8}: "
          f"{'installed' if has_model(current) else 'MISSING'}"
          f"   (from {aiworld_config.source()})")
    if ollama_models():
        print(f"  models       : {', '.join(ollama_models())}")

    print()
    print("Site names (.localhost, resolved by the browser):")
    for name in SITE_NAMES:
        print(f"  {name}")
    print(f"  port 80        : {'in use' if port_in_use(80) else 'free'}")
    print("Ports (fallback):")
    for port in WEB_PORTS:
        print(f"  {port:<6}: {'in use' if port_in_use(port) else 'free'}")
    return 0


def action_start(home, python, want, open_browser=True, preload=False):
    if python is None:
        print("[ERROR] Python was not found. Install Python 3, or set it on PATH.")
        return 1
    if not os.path.isfile(os.path.join(home, "aiworld_web.py")):
        print(f"[ERROR] aiworld_web.py not found in {home}.")
        print("        Put AIWORLD.exe inside the AIWORLD folder, or set")
        print("        the AIWORLD_HOME environment variable to that folder.")
        return 1

    state = load_run()
    state.setdefault("pids", {})

    # --- Ollama ---
    model = aiworld_config.get_model()
    if want & WANT_OLLAMA:
        pid = start_ollama()
        if pid:
            state["ollama_pid"] = pid
        if ollama_running() and not has_model(model):
            print(f"[OLLAMA] model '{model}' is not installed.")
            print(f"         Run:  ollama pull {model}")
            print("         or choose another model from the menu "
                  "(Add or change LLM).")

    # --- The simulated Internet ---
    if want & WANT_NET:
        if net_reachable() or pid_alive(state["pids"].get("web")):
            print("[NET] already running.")
        else:
            state["pids"]["web"] = start_script(
                "simulated Internet", python, home, "aiworld_web.py")
            if wait_for_net():
                print("[NET] online.")
            else:
                print("[NET] did not answer yet; it may still be starting.")

    # --- World Builder ---
    if want & WANT_BUILDER:
        if pid_alive(state["pids"].get("builder")):
            print("[BUILDER] already running.")
        else:
            state["pids"]["builder"] = start_script(
                "World Builder", python, home, "world_builder.py")

    # --- World Resident ---
    if want & WANT_RESIDENT:
        if pid_alive(state["pids"].get("resident")):
            print("[RESIDENT] already running.")
        else:
            state["pids"]["resident"] = start_script(
                "World Resident", python, home, "world_resident.py")

    save_run(state)

    if preload and ollama_running():
        warm = aiworld_config.get_model()
        print(f"[OLLAMA] warming model '{warm}' (this can take a while)...")
        print("[OLLAMA] warm." if preload_model(warm)
              else "[OLLAMA] could not warm the model.")

    if open_browser and (want & WANT_NET or want & WANT_BUILDER
                         or want & WANT_RESIDENT):
        try:
            webbrowser.open(OMNIPEDIA_URL)
        except Exception:
            pass

    print()
    print("=" * 60)
    print("AIWORLD is starting. Omnipedia: " + OMNIPEDIA_URL)
    print("(or http://127.0.0.1:5000/ if the name does not open)")
    print("=" * 60)
    return 0


def action_stop():
    state = load_run()
    killed = []
    for name, pid in (state.get("pids") or {}).items():
        if pid:
            print(f"[STOP] {name} (pid {pid})")
            kill_pid(pid)
            killed.append(name)
    if state.get("ollama_pid"):
        print(f"[STOP] ollama (pid {state['ollama_pid']})")
        kill_pid(state["ollama_pid"])
        killed.append("ollama")
    if not killed:
        print("[STOP] nothing was running.")
    try:
        os.remove(RUN_FILE)
    except OSError:
        pass
    save_run({"pids": {}, "ollama_pid": None})
    return 0


# ============================================================
# WANT FLAGS
# ============================================================

WANT_OLLAMA = 1
WANT_NET = 2
WANT_BUILDER = 4
WANT_RESIDENT = 8
WANT_ALL = WANT_OLLAMA | WANT_NET | WANT_BUILDER | WANT_RESIDENT


# ============================================================
# LLM MANAGER (Add or change LLM)
# ============================================================

def action_llm():
    """Open the graphical LLM Manager window ("Add or change LLM")."""
    try:
        import aiworld_llm_manager
    except Exception as e:  # noqa: BLE001
        print("[ERROR] The LLM Manager could not be started:", e)
        print("        It needs Tkinter (included with the standard Python")
        print("        on Windows).  You can still choose a model by editing")
        print("        " + aiworld_config.config_path())
        return 1
    try:
        aiworld_llm_manager.open_manager()
    except Exception as e:  # noqa: BLE001
        print("[ERROR] The LLM Manager closed with an error:", e)
        return 1
    return 0


# ============================================================
# MENU
# ============================================================

def menu():
    print()
    print("  1) Everything  (Ollama + net + Builder + Resident)")
    print("  2) The simulated Internet only (4 websites)")
    print("  3) World Builder only")
    print("  4) World Resident only")
    print("  5) Ollama only")
    print("  6) Stop everything AIWORLD started")
    print("  7) Environment check")
    print("  8) Add or change LLM")
    print("  0) Quit")
    print("=" * 60)
    try:
        choice = input("Choose [1]: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        return "0"
    return choice


def run_menu(home):
    python = find_python()
    while True:
        choice = menu()
        if choice == "1":
            action_start(home, python, WANT_ALL)
        elif choice == "2":
            action_start(home, python, WANT_NET)
        elif choice == "3":
            action_start(home, python, WANT_BUILDER)
        elif choice == "4":
            action_start(home, python, WANT_RESIDENT)
        elif choice == "5":
            action_start(home, python, WANT_OLLAMA, open_browser=False)
        elif choice == "6":
            action_stop()
        elif choice == "7":
            action_check(home)
        elif choice == "8":
            action_llm()
        elif choice == "0":
            return 0
        else:
            print("Unknown choice.")
        print()


# ============================================================
# MAIN
# ============================================================

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    home = home_dir()
    python = find_python()

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--check" in argv:
        return action_check(home)
    if "--stop" in argv:
        return action_stop()
    if "--llm" in argv or "--model" in argv:
        return action_llm()

    open_browser = "--no-browser" not in argv
    preload = "--preload" in argv

    want = 0
    if "--all" in argv:
        want |= WANT_ALL
    if "--net" in argv or "--web" in argv:
        want |= WANT_NET
    if "--builder" in argv:
        want |= WANT_BUILDER
    if "--resident" in argv:
        want |= WANT_RESIDENT
    if "--ollama" in argv:
        want |= WANT_OLLAMA

    if want == 0:
        return run_menu(home)

    return action_start(home, python, want,
                        open_browser=open_browser, preload=preload)


if __name__ == "__main__":
    sys.exit(main())
