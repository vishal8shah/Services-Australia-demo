"""Hybrid retrieval: FTS5 BM25 for the payment name, vectors for the situation.

Fused with reciprocal rank fusion rather than a weighted score blend, because a
weight tuned on thirty questions is a weight overfitted to thirty questions.
Confidence is reported separately from rank, since the refusal decision needs an
absolute signal and RRF only gives a relative one.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .. import config, store
from ..ingest.embed import get_embedder

FTS_SAFE = re.compile(r"[^\w\s']+")


@dataclass
class Hit:
    chunk: store.Chunk
    score: float           # fused rank score, comparable within one query only
    lexical: float | None  # bm25, normalised against the best hit for this query
    vector: float | None   # raw cosine
    coverage: float        # share of the question's content words present in the chunk
    margin: float          # how far this chunk sits above the median candidate
    facets: list[str]

    @property
    def confidence(self) -> float:
        """An absolute signal, unlike rank.

        Rank only says which chunk won. The refusal decision needs to know whether
        the winner is any good, so confidence is the better of two absolute
        measures: how much of what the person actually said appears in the chunk,
        and how far the chunk stands above the middle of the candidate pool. The
        second keeps the floor meaningful when a semantic embedder is configured,
        where every cosine sits high and only the spread carries information.
        """
        return max(self.coverage, self.margin)


def fts_query(text: str) -> str:
    """FTS5 has its own syntax: a stray quote or hyphen from a user is a crash.

    Terms of four characters or more also get a prefix form, so "jobseek" finds
    "jobseeker" and "claim" finds "claiming". Short terms stay exact, because
    "car*" would match half the corpus.
    """
    cleaned = FTS_SAFE.sub(" ", text).strip()
    terms = [t for t in cleaned.split() if len(t) > 1]
    forms = []
    for t in terms:
        forms.append(f'"{t}"')
        if len(t) >= 4:
            forms.append(f'"{t}"*')
    return " OR ".join(forms)


def lexical_search(conn, query: str, limit: int) -> list[tuple[str, float]]:
    q = fts_query(query)
    if not q:
        return []
    rows = conn.execute(
        "SELECT chunk_id, bm25(chunks_fts, 2.0, 3.0, 1.0) AS rank FROM chunks_fts "
        "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (q, limit),
    ).fetchall()
    # bm25() returns a negative number, more negative is better.
    if not rows:
        return []
    best = min(r["rank"] for r in rows)
    return [(r["chunk_id"], _norm_bm25(r["rank"], best)) for r in rows]


def _norm_bm25(rank: float, best: float) -> float:
    """Map bm25 onto 0 to 1 against the best hit for this query, saturating."""
    if best == 0:
        return 0.0
    return max(0.0, min(1.0, rank / best))


STOPWORDS = {
    "i", "we", "my", "our", "me", "us", "it", "is", "am", "are", "was", "were",
    "the", "a", "an", "to", "of", "in", "on", "at", "so", "and", "but", "now",
    "just", "have", "has", "had", "do", "does", "did", "this", "that", "for",
    "with", "he", "she", "they", "them", "his", "her", "their", "be", "been",
    "get", "got", "can", "will", "would", "should", "what", "how", "when",
    "who", "if", "about", "from", "you", "your", "there", "any", "all", "as",
}
WORD = re.compile(r"[a-z']{2,}")


def content_terms(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS}


def soft_match(term: str, token: str) -> bool:
    """Exact, or one contains the other with room to spare.

    The margin matters. Without it "car" matches "care" and every question about a
    vehicle retrieves Carer Payment. With it, "job" still finds "jobseeker" and
    "child" still finds "childcare", which are the two misses the fixture corpus
    actually produced.
    """
    if term == token:
        return True
    if len(term) >= 3 and len(token) >= len(term) + 3 and term in token:
        return True
    return len(token) >= 3 and len(term) >= len(token) + 3 and token in term


def coverage(query_terms: set[str], chunk: store.Chunk) -> float:
    """Share of the question's content words that appear in the chunk.

    Stemming is deliberately absent: "changed" not matching "changes" costs a few
    points of coverage, and inventing a stemmer here would hide the cost rather
    than remove it. The FTS index does the stemming for ranking.
    """
    if not query_terms:
        return 0.0
    haystack = content_terms(f"{chunk.title} {chunk.heading_path} {chunk.text}")
    hit = sum(1 for term in query_terms
              if term in haystack or any(soft_match(term, tok) for tok in haystack))
    return hit / len(query_terms)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, dot / (na * nb))


def vector_search(conn, query: str, limit: int,
                  embedder=None) -> tuple[list[tuple[str, float]], float]:
    """Returns the top hits and the median cosine across all candidates.

    The median is what makes the cosine interpretable: embedding models put every
    pair of English sentences somewhere around 0.6, so the absolute number says
    almost nothing and the distance above the middle says almost everything.
    """
    embedder = embedder or get_embedder()
    qv = embedder.embed([query])[0]
    scored = []
    for row in conn.execute("SELECT chunk_id, vector FROM chunks WHERE vector IS NOT NULL"):
        vec = store.unpack(row["vector"])
        if vec and len(vec) == len(qv):
            scored.append((row["chunk_id"], cosine(qv, vec)))
    scored.sort(key=lambda x: x[1], reverse=True)
    values = sorted(s for _, s in scored)
    median = values[len(values) // 2] if values else 0.0
    # Anything at or below the median cosine carries no information: including it
    # in the fusion adds a near uniform prior across the whole corpus, which is
    # how a good lexical hit gets voted out by forty irrelevant chunks.
    informative = [(cid, sc) for cid, sc in scored if sc > median]
    return informative[:limit], median


def rrf(rankings: list[list[tuple[str, float]]], k: int,
        weights: list[float] | None = None) -> dict[str, float]:
    """Reciprocal rank fusion, with a weight per ranking.

    The weights exist for one reason: a facet is a fragment of what the person
    said, so it should not outvote the whole sentence. Three facets contributing
    six unweighted rankings will otherwise bury the sentence's own best hit.
    """
    weights = weights or [1.0] * len(rankings)
    fused: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, (chunk_id, _score) in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + weight / (k + rank)
    return fused


def search(conn, query: str, facets: list[str] | None = None,
           expansions: list[str] | None = None,
           top_k: int | None = None, embedder=None) -> list[Hit]:
    """Retrieve for the whole sentence, for each facet, and for each expansion.

    Running the facets as separate queries is what surfaces two payment families
    from one sentence: the carer facet and the income facet each win their own
    ranking, and fusion keeps both instead of letting the longer one dominate.

    Three tiers of evidence, weighted apart on purpose. The sentence is what the
    person said. A facet is part of what they said. An expansion is a model's
    guess at what they meant, so it can pull a chunk into the results but it
    cannot, on its own, talk the system out of refusing.
    """
    top_k = top_k or config.TOP_K
    user_queries = [query] + [f for f in (facets or []) if f.strip() and f != query]
    expansion_queries = [e for e in (expansions or []) if e.strip() and e not in user_queries]
    queries = user_queries + expansion_queries
    weights_by_query = ([1.0] + [config.FACET_WEIGHT] * (len(user_queries) - 1)
                        + [config.EXPANSION_WEIGHT] * len(expansion_queries))

    rankings: list[list[tuple[str, float]]] = []
    weights: list[float] = []
    lex_best: dict[str, float] = {}
    vec_best: dict[str, float] = {}
    margin_best: dict[str, float] = {}
    origin: dict[str, set[str]] = {}

    for q, weight in zip(queries, weights_by_query):
        lex = lexical_search(conn, q, config.CANDIDATES)
        vec, median = vector_search(conn, q, config.VECTOR_CANDIDATES, embedder=embedder)
        rankings.extend([lex, vec])
        weights.extend([weight, weight])
        for cid, s in lex:
            lex_best[cid] = max(lex_best.get(cid, 0.0), s)
            origin.setdefault(cid, set()).add(q)
        span = max(1e-6, 1.0 - median)
        for cid, s in vec:
            vec_best[cid] = max(vec_best.get(cid, 0.0), s)
            # Discounted by the weight of the query that found it, so second hand
            # evidence stays second hand in the refusal decision too.
            margin_best[cid] = max(margin_best.get(cid, 0.0), weight * (s - median) / span)
            origin.setdefault(cid, set()).add(q)

    fused = rrf(rankings, config.RRF_K, weights)
    ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
    chunks = store.get_chunks(conn, [cid for cid, _ in ordered])
    # Coverage weighting is not the fusion weighting. A facet is the person's own
    # words, so evidence found through it counts in full; only an expansion is
    # second hand and gets discounted. The fusion weight exists to stop facets
    # outvoting the sentence in the ranking, which is a different problem, and
    # reusing it here quietly cost eight points of recall.
    term_sets = ([(content_terms(q), 1.0) for q in user_queries]
                 + [(content_terms(q), config.EXPANSION_WEIGHT) for q in expansion_queries])

    hits = []
    for cid, score in ordered:
        chunk = chunks.get(cid)
        if not chunk:
            continue
        hits.append(Hit(
            chunk=chunk,
            score=score,
            lexical=lex_best.get(cid),
            vector=vec_best.get(cid),
            coverage=max((w * coverage(t, chunk) for t, w in term_sets), default=0.0),
            margin=max(0.0, margin_best.get(cid, 0.0)),
            facets=sorted(origin.get(cid, set())),
        ))
    return hits


def confidence_of(hits: list[Hit]) -> float:
    return max((h.confidence for h in hits), default=0.0)
