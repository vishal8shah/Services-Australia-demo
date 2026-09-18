"""Heading scoped chunking.

One chunk is one heading's worth of text, split on paragraph boundaries when it
runs long and merged forward when it is too short to stand alone. The heading
path is prepended to the indexed text so a lexical match on "who can get it"
still lands on the right payment.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .. import config, store
from .extract import Page, Section, extract


def split_section(section: Section, max_chars: int) -> list[str]:
    """Split on paragraph boundaries, falling back to sentences for a long block."""
    if len(section.text) <= max_chars:
        return [section.text]
    units = section.text.split("\n")
    out: list[str] = []
    for unit in units:
        if len(unit) <= max_chars:
            out.append(unit)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", unit)
        buf = ""
        for s in sentences:
            if buf and len(buf) + len(s) + 1 > max_chars:
                out.append(buf.strip())
                buf = s
            else:
                buf = f"{buf} {s}" if buf else s
        if buf.strip():
            out.append(buf.strip())

    parts, current = [], ""
    for unit in out:
        if current and len(current) + len(unit) + 1 > max_chars:
            parts.append(current.strip())
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p]


def _is_kin(parent_path: str, child_path: str) -> bool:
    """Same heading, or the child sits directly under the parent."""
    return child_path == parent_path or child_path.startswith(parent_path + " > ")


def chunk_page(page: Page,
               max_chars: int | None = None,
               min_chars: int | None = None) -> list[store.Chunk]:
    max_chars = max_chars or config.MAX_CHUNK_CHARS
    min_chars = min_chars or config.MIN_CHUNK_CHARS

    pending: list[tuple[str, str]] = []  # (heading_path, text)
    for section in page.sections:
        for part in split_section(section, max_chars):
            short = len(part) < min_chars
            if (pending and short
                    and _is_kin(pending[-1][0], section.heading_path)
                    and len(pending[-1][1]) + len(part) + 1 <= max_chars):
                # A short fragment belongs with its parent section: an orphaned
                # "You must tell us within 14 days" retrieves as pure noise.
                prev_path, prev_text = pending[-1]
                pending[-1] = (prev_path, f"{prev_text}\n{part}")
            else:
                pending.append((section.heading_path, part))

    return [
        store.Chunk(
            chunk_id=store.chunk_id_for(page.url, path, i),
            url=page.url,
            title=page.title,
            heading_path=path,
            ordinal=i,
            text=text,
            page_last_updated=page.page_last_updated,
        )
        for i, (path, text) in enumerate(pending)
    ]


def rebuild() -> int:
    """Re-chunk every stored raw page. Safe to run repeatedly."""
    import hashlib

    total = 0
    with store.connect() as conn:
        rows = list(conn.execute("SELECT url FROM pages WHERE status=200"))
        for row in rows:
            url = row["url"]
            raw = config.RAW / f"{hashlib.sha1(url.encode()).hexdigest()}.html"
            if not raw.exists():
                continue
            page = extract(raw.read_text(encoding="utf-8"), url)
            chunks = chunk_page(page)
            store.replace_chunks(conn, url, chunks)
            total += len(chunks)
        print(f"chunked {len(rows)} pages into {total} chunks")
        print(store.counts(conn))
    return total


if __name__ == "__main__":
    sys.exit(0 if rebuild() >= 0 else 1)
