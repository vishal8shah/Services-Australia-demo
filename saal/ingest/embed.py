"""Embeddings behind a two method interface, with an offline default.

`hashing` is a deterministic bag of words projection with no dependencies and no
network. It is a development fallback, not semantic retrieval: it will not match
"Mum is moving in with us" to "constant care" because it shares no words with it.
Set SAAL_EMBED_PROVIDER=voyage with VOYAGE_API_KEY for the real thing, and expect
the compound recall metric in the eval scorecard to move when you do. That gap is
the point of measuring it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from typing import Protocol

from .. import config, store

TOKEN = re.compile(r"[a-z0-9']+")


class Embedder(Protocol):
    name: str
    dims: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokens(text: str) -> list[str]:
    words = TOKEN.findall(text.lower())
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + bigrams


class HashingEmbedder:
    """Signed feature hashing, sublinear term frequency, L2 normalised."""

    name = "hashing"

    def __init__(self, dims: int | None = None) -> None:
        self.dims = dims or config.EMBED_DIMS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        counts: dict[str, int] = {}
        for tok in _tokens(text):
            counts[tok] = counts.get(tok, 0) + 1
        vec = [0.0] * self.dims
        for tok, tf in counts.items():
            digest = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dims
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign * (1.0 + math.log(tf))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class VoyageEmbedder:
    """Real semantic embeddings. Requires VOYAGE_API_KEY and network access."""

    name = "voyage"

    def __init__(self, model: str = "voyage-3", dims: int = 1024) -> None:
        self.model, self.dims = model, dims
        self.key = os.environ.get("VOYAGE_API_KEY")
        if not self.key:
            raise RuntimeError("VOYAGE_API_KEY is not set")

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = texts[i:i + 64]
            req = urllib.request.Request(
                "https://api.voyageai.com/v1/embeddings",
                data=json.dumps({"input": batch, "model": self.model}).encode(),
                headers={"Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.load(resp)
            out.extend(item["embedding"] for item in payload["data"])
        return out


def get_embedder(name: str | None = None) -> Embedder:
    name = name or config.EMBED_PROVIDER
    if name == "hashing":
        return HashingEmbedder()
    if name == "voyage":
        return VoyageEmbedder()
    raise ValueError(f"unknown embedding provider: {name}")


def embed_corpus(conn=None, embedder: Embedder | None = None) -> int:
    embedder = embedder or get_embedder()

    def run(conn) -> int:
        rows = list(conn.execute("SELECT chunk_id, title, heading_path, text FROM chunks"))
        if not rows:
            return 0
        texts = [f"{r['title']}. {r['heading_path']}.\n{r['text']}" for r in rows]
        vectors = embedder.embed(texts)
        for row, vec in zip(rows, vectors):
            store.set_vector(conn, row["chunk_id"], vec)
        return len(rows)

    if conn is not None:
        return run(conn)
    with store.connect() as owned:
        n = run(owned)
        print(f"embedded {n} chunks with provider '{embedder.name}'")
        print(store.counts(owned))
        return n


if __name__ == "__main__":
    sys.exit(0 if embed_corpus() >= 0 else 1)
