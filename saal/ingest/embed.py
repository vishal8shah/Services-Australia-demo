"""Embeddings behind a two method interface, with an offline default.

`hashing` is a deterministic bag of words projection with no dependencies and no
network. Word features plus character n grams, so it bridges spelling ("childcare"
to "child care") but never meaning: it will not match "Mum is moving in with us"
to "constant care", because the two share no characters worth sharing.

Closing that gap costs either a hosted embedder or a local model:

    SAAL_EMBED_PROVIDER=openai  OPENAI_API_KEY=...   # text-embedding-3-small
    SAAL_EMBED_PROVIDER=gemini  GEMINI_API_KEY=...   # free tier, no card
    SAAL_EMBED_PROVIDER=voyage  VOYAGE_API_KEY=...   # paid
    SAAL_EMBED_PROVIDER=local                        # pip install sentence-transformers

Or skip the embedder question entirely and expand the query instead, which uses the
same key the synthesis step already needs. See `saal/retrieve/expand.py`.
Whichever you pick, rerun `make index`, and watch compound recall on the scorecard.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Protocol

from .. import config, store

TOKEN = re.compile(r"[a-z0-9']+")


class Embedder(Protocol):
    name: str
    dims: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _char_ngrams(words: list[str], n: int = 4) -> list[str]:
    """Character n grams across word boundaries.

    This is what lets "childcare" find "child care" and "job" find "JobSeeker"
    without a semantic model. It is a spelling bridge, not a meaning bridge: it
    will never connect "Mum is moving in with us" to "constant care".
    """
    padded = " " + " ".join(words) + " "
    return [f"#{padded[i:i + n]}" for i in range(len(padded) - n + 1)]


def _tokens(text: str) -> list[tuple[str, float]]:
    words = TOKEN.findall(text.lower())
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    features = [(w, 1.0) for w in words] + [(b, 1.0) for b in bigrams]
    # Weighted down: character overlap is weaker evidence than a shared word,
    # and there are far more of them, so at equal weight they drown the words.
    features += [(g, config.CHAR_NGRAM_WEIGHT) for g in _char_ngrams(words)]
    return features


class HashingEmbedder:
    """Signed feature hashing, sublinear term frequency, L2 normalised."""

    name = "hashing"

    def __init__(self, dims: int | None = None) -> None:
        self.dims = dims or config.EMBED_DIMS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        counts: dict[str, float] = {}
        weights: dict[str, float] = {}
        for tok, weight in _tokens(text):
            counts[tok] = counts.get(tok, 0.0) + 1.0
            weights[tok] = weight
        vec = [0.0] * self.dims
        for tok, tf in counts.items():
            digest = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dims
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign * weights[tok] * (1.0 + math.log(tf))
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


class OpenAIEmbedder:
    """text-embedding-3-small, shortened to keep cosine fast.

    Cosine runs in pure Python here, so every dimension is latency: 1536 wide over
    a few thousand chunks is a second of arithmetic per query. The 3 series
    supports native shortening, which keeps most of the quality at a third of the
    width. Raise SAAL_OPENAI_EMBED_DIMS if recall matters more than milliseconds.
    """

    name = "openai"

    def __init__(self, model: str | None = None, dims: int | None = None) -> None:
        self.model = model or config.OPENAI_EMBED_MODEL
        self.dims = dims or config.OPENAI_EMBED_DIMS
        self.key = os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise RuntimeError("OPENAI_API_KEY is not set")

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            batch = [t[:8000] for t in texts[i:i + 128]]
            body = {"input": batch, "model": self.model, "dimensions": self.dims}
            req = urllib.request.Request(
                f"{config.OPENAI_BASE.rstrip('/')}/v1/embeddings",
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {self.key}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    payload = json.load(resp)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(
                    f"openai embeddings {exc.code}: "
                    f"{exc.read().decode('utf-8', 'replace')[:300]}") from exc
            out.extend(item["embedding"] for item in
                       sorted(payload["data"], key=lambda d: d["index"]))
        return out


class GeminiEmbedder:
    """Free tier embeddings. A Google AI Studio key needs no card.

    Listed because it is the option with no cost attached, not because it is
    better than the others. Whichever you use, rerun `make index`: changing the
    embedder changes every vector in the corpus.
    """

    name = "gemini"

    def __init__(self, model: str = "models/text-embedding-004", dims: int = 768) -> None:
        self.model, self.dims = model, dims
        self.key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY is not set")

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        base = "https://generativelanguage.googleapis.com/v1beta"
        for i in range(0, len(texts), 100):
            batch = texts[i:i + 100]
            payload = {"requests": [
                {"model": self.model, "content": {"parts": [{"text": t}]}} for t in batch]}
            req = urllib.request.Request(
                f"{base}/{self.model}:batchEmbedContents?key={self.key}",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.load(resp)
            out.extend(e["values"] for e in data["embeddings"])
        return out


class SentenceTransformerEmbedder:
    """No key and no network, once the model is downloaded.

    Costs one dependency and a few hundred megabytes: `pip install
    sentence-transformers`. Choose this when the corpus must stay on your machine.
    """

    name = "local"

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self.model = SentenceTransformer(model)
        self.dims = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in
                self.model.encode(texts, normalize_embeddings=True, batch_size=32)]


def get_embedder(name: str | None = None) -> Embedder:
    name = name or config.EMBED_PROVIDER
    if name == "hashing":
        return HashingEmbedder()
    if name == "voyage":
        return VoyageEmbedder()
    if name == "openai":
        return OpenAIEmbedder()
    if name == "gemini":
        return GeminiEmbedder()
    if name == "local":
        return SentenceTransformerEmbedder()
    raise ValueError(f"unknown embedding provider: {name}")


def embed_corpus(conn=None, embedder: Embedder | None = None) -> int:
    embedder = embedder or get_embedder()

    def run(conn) -> int:
        # Recorded so a later search can tell that the corpus was embedded with a
        # different model. A silent dimension mismatch degrades every cosine to
        # zero and looks exactly like bad retrieval.
        conn.execute("INSERT INTO meta(key, value) VALUES('embedder', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (f"{embedder.name}:{embedder.dims}",))
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
