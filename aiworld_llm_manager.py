"""AIWORLD - the LLM Manager window ("Add or change LLM").

A small Tk window that lets you choose which **installed** Ollama model AIWORLD
should use.  It shows whether Ollama is running, lists the models Ollama
actually has, shows the currently selected model, and writes your choice to
``aiworld_config.json`` -- which the World Builder, the on-demand website
generation and the World Resident all read.

It starts Ollama in the background when needed (without freezing the window and
without killing an Ollama that is already running), and it never downloads
models: pick from what you already have.

Run it with ``python aiworld_llm_manager.py``, or from the launcher menu
("Add or change LLM").
"""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import aiworld_config as config
import aiworld_ollama as ollama


class LLMManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AIWORLD — LLM Manager")
        self.geometry("580x430")
        self.minsize(500, 380)

        self.model_names = []
        self.busy = False
        self._q = queue.Queue()

        self._build()
        self.after(120, self._poll)
        self.after(150, self.refresh)

    # ----------------------------------------------------------
    # layout
    # ----------------------------------------------------------

    def _build(self):
        ttk.Label(self, text="AIWORLD — LLM Manager",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=12, pady=(12, 4))

        self.ollama_var = tk.StringVar(value="Ollama: checking…")
        ttk.Label(self, textvariable=self.ollama_var,
                  font=("Segoe UI", 10)).pack(anchor="w", padx=12)

        self.current_var = tk.StringVar()
        ttk.Label(self, textvariable=self.current_var,
                  foreground="#0a7a34").pack(anchor="w", padx=12, pady=(2, 10))

        ttk.Label(self, text="Models installed in Ollama:"
                  ).pack(anchor="w", padx=12)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=4)
        self.listbox = tk.Listbox(frame, height=10, activestyle="dotbox",
                                  font=("Consolas", 10))
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>",
                          lambda _event: self.apply_selection())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=8)
        self.refresh_btn = ttk.Button(buttons, text="Refresh",
                                      command=self.refresh)
        self.refresh_btn.pack(side="left")
        self.apply_btn = ttk.Button(buttons, text="Select and apply",
                                    command=self.apply_selection)
        self.apply_btn.pack(side="left", padx=6)
        ttk.Button(buttons, text="Back to main menu",
                   command=self.destroy).pack(side="right")

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, foreground="#555",
                  wraplength=540, justify="left").pack(anchor="w", padx=12,
                                                       pady=(0, 10))

    # ----------------------------------------------------------
    # thread plumbing (keep the window responsive)
    # ----------------------------------------------------------

    def _poll(self):
        try:
            while True:
                self._q.get_nowait()()
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_btn.configure(state=state)
        self.apply_btn.configure(state=state)

    # ----------------------------------------------------------
    # actions
    # ----------------------------------------------------------

    def refresh(self):
        if self.busy:
            return
        self._set_busy(True)
        self.ollama_var.set("Ollama: checking…")
        self.status_var.set("Looking for Ollama and the installed models…")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        running = ollama.is_running()
        message = ""
        if not running:
            running, message = ollama.start(wait=45)
        models = ollama.list_models() if running else []
        self._q.put(lambda: self._apply_refresh(running, message, models))

    def _apply_refresh(self, running, message, models):
        self._set_busy(False)
        self.ollama_var.set(
            "Ollama: running at http://localhost:11434" if running
            else "Ollama: NOT running")

        current = config.get_model()
        self.model_names = [m["name"] for m in models]
        self.listbox.delete(0, tk.END)
        selected = None
        for i, m in enumerate(models):
            label = m["name"]
            if m.get("family"):
                label += f"    ({m['family']})"
            self.listbox.insert(tk.END, label)
            if m["name"] == current:
                selected = i
        if selected is not None:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(selected)
            self.listbox.see(selected)

        self._refresh_current()

        if not running:
            self.status_var.set(message or "Ollama is not running.")
            messagebox.showerror(
                "Ollama not available",
                (message or "Ollama is not running.") +
                "\n\nInstall it from https://ollama.com/download, or start it "
                "and press Refresh.")
        elif not models:
            self.status_var.set("Ollama is running, but no models are installed. "
                                "Add one with:  ollama pull <model>")
        else:
            self.status_var.set(
                f"Found {len(models)} model(s). Select one and press "
                "“Select and apply”. The choice applies from the next request on.")

    def _refresh_current(self):
        self.current_var.set(
            f"Current AIWORLD model:  {config.get_model()}   "
            f"[from {config.source()}]")

    def apply_selection(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "No model selected",
                "Choose a model in the list first, then press “Select and apply”.")
            return

        name = self.model_names[selection[0]]

        if name not in ollama.names():
            messagebox.showerror(
                "Model not available",
                f"“{name}” is not installed in Ollama any more. Press Refresh.")
            return

        if config.set_model(name):
            self._refresh_current()
            self.status_var.set(
                f"Saved. AIWORLD will use “{name}”. Windows that are already "
                "open switch on their next request.")
            messagebox.showinfo(
                "Model changed",
                f"AIWORLD now uses:\n\n    {name}\n\n"
                "Saved in:\n" + config.config_path())
        else:
            messagebox.showerror(
                "Could not save the choice",
                "The selection could not be written to:\n\n"
                + config.config_path() +
                "\n\nCheck that the folder is writable.")


def open_manager():
    """Open the LLM Manager window (blocking until the user closes it)."""
    LLMManager().mainloop()


def main():
    open_manager()


if __name__ == "__main__":
    main()
