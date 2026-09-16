"""SQLite corpus store: pages, chunks, an FTS5 lexical index and vector blobs.

One file holds the whole corpus, which is what lets the eval suite, the API and
a laptop with no network all run against identical bytes.
"""
from __future__ import annotations

import array
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url                TEXT PRIMARY KEY,
    title              TEXT,
    html_sha           TEXT,
    fetched_at         TEXT,
    page_last_updated  TEXT,
    status             INTEGER
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id           TEXT PRIMARY KEY,
    url                TEXT NOT NULL,
    title              TEXT,
    heading_path       TEXT,
    ordinal            INTEGER,
    text               TEXT NOT NULL,
    page_last_updated  TEXT,
    vector             BLOB
);

CREATE INDEX IF NOT EXISTS idx_chunks_url ON chunks(url);

CREATE TABLE IF NOT EXISTS meta (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    title,
    heading_path,
    text,
    tokenize = 'porter unicode61'
);
"""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    url: str
    title: str
    heading_path: str
    ordinal: int
    text: str
    page_last_updated: str | None = None
    vector: list[float] | None = field(default=None, repr=False)

    @property
    def stale(self) -> bool:
        return is_stale(self.page_last_updated)

    def cite(self) -> dict:
        return {
            "id": self.chunk_id,
            "title": self.title,
            "heading_path": self.heading_path,
            "url": self.url,
            "page_last_updated": self.page_last_updated,
            "stale": self.stale,
        }


def is_stale(page_last_updated: str | None, today: date | None = None) -> bool:
    """A source with no date is treated as stale: absence of evidence is not freshness."""
    if not page_last_updated:
        return True
    try:
        d = datetime.fromisoformat(page_last_updated).date()
    except ValueError:
        return True
    today = today or date.today()
    return (today - d).days > config.STALE_AFTER_DAYS


def chunk_id_for(url: str, heading_path: str, ordinal: int) -> str:
    """Stable across recrawls, so the eval answer key survives a content refresh.

    Keyed on location rather than content: an edited paragraph keeps its id, a
    moved heading gets a new one.
    """
    raw = f"{url}||{heading_path}||{ordinal}".encode()
    return "c_" + hashlib.sha1(raw).hexdigest()[:8]


def pack(vector: list[float]) -> bytes:
    return array.array("f", vector).tobytes()


def unpack(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    a = array.array("f")
    a.frombytes(blob)
    return list(a)


def open_conn(path: Path | str | None = None) -> sqlite3.Connection:
    """Long lived connection with the schema applied. Callers close it."""
    if path == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        p = Path(path or config.DB_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def connect(path: Path | str | None = None):
    conn = open_conn(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_page(conn, *, url, title, html_sha, fetched_at, page_last_updated, status):
    conn.execute(
        "INSERT INTO pages(url, title, html_sha, fetched_at, page_last_updated, status) "
        "VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET "
        "title=excluded.title, html_sha=excluded.html_sha, fetched_at=excluded.fetched_at, "
        "page_last_updated=excluded.page_last_updated, status=excluded.status",
        (url, title, html_sha, fetched_at, page_last_updated, status),
    )


def replace_chunks(conn, url: str, chunks: list[Chunk]) -> None:
    """Whole page at a time, so a recrawl cannot leave orphan chunks behind."""
    old = [r["chunk_id"] for r in conn.execute("SELECT chunk_id FROM chunks WHERE url=?", (url,))]
    if old:
        conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(c,) for c in old])
        conn.execute("DELETE FROM chunks WHERE url=?", (url,))
    for c in chunks:
        conn.execute(
            "INSERT INTO chunks(chunk_id, url, title, heading_path, ordinal, text, "
            "page_last_updated, vector) VALUES(?,?,?,?,?,?,?,?)",
            (c.chunk_id, c.url, c.title, c.heading_path, c.ordinal, c.text,
             c.page_last_updated, pack(c.vector) if c.vector else None),
        )
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id, title, heading_path, text) VALUES(?,?,?,?)",
            (c.chunk_id, c.title, c.heading_path, c.text),
        )


def set_vector(conn, chunk_id: str, vector: list[float]) -> None:
    conn.execute("UPDATE chunks SET vector=? WHERE chunk_id=?", (pack(vector), chunk_id))


def row_to_chunk(row: sqlite3.Row) -> Chunk:
    keys = row.keys()
    return Chunk(
        chunk_id=row["chunk_id"],
        url=row["url"],
        title=row["title"],
        heading_path=row["heading_path"],
        ordinal=row["ordinal"],
        text=row["text"],
        page_last_updated=row["page_last_updated"],
        vector=unpack(row["vector"]) if "vector" in keys else None,
    )


def get_chunks(conn, chunk_ids: list[str]) -> dict[str, Chunk]:
    if not chunk_ids:
        return {}
    marks = ",".join("?" * len(chunk_ids))
    rows = conn.execute(f"SELECT * FROM chunks WHERE chunk_id IN ({marks})", chunk_ids)
    return {r["chunk_id"]: row_to_chunk(r) for r in rows}


def iter_chunks(conn):
    for row in conn.execute("SELECT * FROM chunks ORDER BY url, ordinal"):
        yield row_to_chunk(row)


def get_meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def counts(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "pages": q("SELECT COUNT(*) FROM pages"),
        "chunks": q("SELECT COUNT(*) FROM chunks"),
        "vectors": q("SELECT COUNT(*) FROM chunks WHERE vector IS NOT NULL"),
        "embedder": get_meta(conn, "embedder"),
    }


def load_fixture(conn, path: Path | str) -> int:
    """Load a JSON corpus fixture. Used by tests and by the offline demo."""
    docs = json.loads(Path(path).read_text())
    n = 0
    for doc in docs:
        chunks = [
            Chunk(
                chunk_id=chunk_id_for(doc["url"], c["heading_path"], i),
                url=doc["url"],
                title=doc["title"],
                heading_path=c["heading_path"],
                ordinal=i,
                text=c["text"],
                page_last_updated=doc.get("page_last_updated"),
            )
            for i, c in enumerate(doc["chunks"])
        ]
        upsert_page(
            conn, url=doc["url"], title=doc["title"], html_sha="fixture",
            fetched_at="fixture", page_last_updated=doc.get("page_last_updated"), status=200,
        )
        replace_chunks(conn, doc["url"], chunks)
        n += len(chunks)
    return n
