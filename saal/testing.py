"""Fixture corpus helpers shared by the unit tests and the offline eval run."""
from __future__ import annotations

from pathlib import Path

from . import config, store
from .ingest.embed import HashingEmbedder, embed_corpus

FIXTURE_CORPUS = config.ROOT / "evals" / "fixtures" / "corpus.json"


def fixture_conn(path: str | Path = ":memory:", corpus: str | Path | None = None):
    """An in memory corpus, indexed and embedded, in about a tenth of a second."""
    conn = store.open_conn(path)
    store.load_fixture(conn, corpus or FIXTURE_CORPUS)
    embed_corpus(conn, HashingEmbedder())
    conn.commit()
    return conn
