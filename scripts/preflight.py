"""Fail early, with a message that says what to do about it.

Two things stop this project on an otherwise healthy machine: a Python older than
3.11, which macOS still ships, and a Python whose bundled SQLite was built without
FTS5, which takes out the entire lexical half of retrieval. Both produce confusing
errors deep inside a run, so they are checked once at the front of every make
target, and the checks themselves are tested.
"""
from __future__ import annotations

import sqlite3
import sys

MINIMUM = (3, 11)


def python_problem(version_info=None, executable: str | None = None) -> str | None:
    version_info = version_info or sys.version_info
    executable = executable or sys.executable
    if tuple(version_info[:2]) >= MINIMUM:
        return None
    return (f"this project needs Python {MINIMUM[0]}.{MINIMUM[1]} or newer, "
            f"found {version_info[0]}.{version_info[1]} at {executable}.\n"
            f"  Try:  make PYTHON=python3.12 <target>\n"
            f"  macOS without one:  brew install python@3.12")


def fts5_problem(connect=None) -> str | None:
    connect = connect or (lambda: sqlite3.connect(":memory:"))
    try:
        conn = connect()
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        conn.close()
    except Exception as exc:  # noqa: BLE001 any failure here means no usable FTS5
        return (f"this Python's sqlite3 has no FTS5 ({exc}), and the lexical half of "
                f"retrieval needs it.\n"
                f"  macOS:  brew install python@3.12 and use make PYTHON=python3.12")
    return None


def problems() -> list[str]:
    return [p for p in (python_problem(), fts5_problem()) if p]


def main() -> int:
    found = problems()
    for problem in found:
        print(f"\n  {problem}\n", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
