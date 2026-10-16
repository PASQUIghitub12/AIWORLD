"""AIWORLD - persistent memory for the World Resident.

The resident remembers what it has learned **by browsing**, across sessions.
This memory lives in its own SQLite file (``resident_memory.db``) and is never
mixed into the canonical world database: the resident must still reason from
what it read, but it no longer has to forget it between runs.

What is stored: for each answered question, the question, the answer, the
pages that were read, and a timestamp.  Only answers the resident actually
produced from pages it opened are recorded.
"""

import json
import os
import sqlite3
from datetime import datetime

import web_client as web


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_DB = os.path.join(BASE_DIR, "resident_memory.db")


def connect():
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory():
    conn = connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources TEXT
        )
    """)
    conn.commit()
    conn.close()


def remember(question, answer, sources):
    """Store one learned exchange. ``sources`` is a list of page URLs."""
    conn = connect()
    conn.execute("""
        INSERT INTO memories (ts, question, answer, sources)
        VALUES (?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        question,
        answer,
        json.dumps(list(sources), ensure_ascii=False),
    ))
    conn.commit()
    conn.close()


def recent(limit=20):
    conn = connect()
    rows = conn.execute("""
        SELECT ts, question, answer, sources
        FROM memories
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    items = []
    for r in rows:
        try:
            sources = json.loads(r["sources"] or "[]")
        except Exception:
            sources = []
        items.append({
            "ts": r["ts"],
            "question": r["question"],
            "answer": r["answer"],
            "sources": sources,
        })
    return items


def count():
    conn = connect()
    n = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
    conn.close()
    return n


def search(query, limit=20):
    conn = connect()
    pattern = "%" + (query or "").lower() + "%"
    rows = conn.execute("""
        SELECT ts, question, answer, sources
        FROM memories
        WHERE LOWER(question) LIKE ? OR LOWER(answer) LIKE ?
        ORDER BY id DESC
        LIMIT ?
    """, (pattern, pattern, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def memory_block(limit=12):
    """A compact text summary of recent memories, for the resident's prompt.

    It is clearly framed as things the resident already learned by reading,
    not as a source of canonical truth.
    """
    items = recent(limit)
    if not items:
        return ""

    lines = [
        "You have previously learned the following by reading the net. "
        "Treat it as your own memory: it may be out of date, so re-check by "
        "browsing if it matters.",
        "",
    ]
    for it in reversed(items):
        src = ""
        if it["sources"]:
            src = " (from " + ", ".join(it["sources"][:3]) + ")"
        lines.append(f"- Q: {it['question']}")
        lines.append(f"  A: {it['answer']}{src}")
    return "\n".join(lines)
