# Decisions

Short entries, newest last. Each one records what was chosen, why, and what would
change it. Findings from the eval suite are recorded here too, because a finding
nobody wrote down gets rediscovered at the worst moment.

---

## D1. Core runs on the standard library alone

**Chosen.** `sqlite3`, `urllib`, `html.parser`, `http.server`. Optional extras:
`trafilatura` for better boilerplate stripping, a hosted embedding API, the Claude
API for synthesis.

**Why.** The corpus is a few thousand chunks. A vector database, a web framework
and an ORM would all be ceremony at that size, and every dependency is a thing that
has to still work on the day of the demo. A clone with nothing installed runs the
tests and the eval suite.

**What would change it.** A corpus above roughly 100k chunks, where brute force
cosine stops being milliseconds.

## D2. The refusal floor is term coverage, not rank

**Chosen.** Confidence is the better of two absolute measures: the share of the
question's content words present in the chunk, and how far the chunk's cosine sits
above the median of the candidate pool.

**Why.** The first attempt normalised BM25 against the best hit for the query, which
returns 1.0 for the top result of every query including nonsense ones. A refusal
decision needs an absolute signal. Rank only says which chunk won, never whether the
winner is any good. The median relative margin keeps the floor meaningful under a
semantic embedder, where every cosine sits high and only the spread carries
information.

**What would change it.** Calibrating the floor on the real corpus. The current 0.30
was set against the fixture corpus and is a starting point, not a result.

## D3. Facets get less of a vote than the whole question

**Chosen.** Reciprocal rank fusion with a weight of 1.0 for the full sentence and
0.7 for each facet, and vector hits at or below the median cosine dropped before
fusion.

**Why, and this was a real defect.** With unweighted fusion, decomposing "I lost my
job last month, I have two kids in childcare and I rent" made the results worse than
not decomposing: three facets contributed six rankings, the near uniform vector
rankings acted as a corpus wide prior, and JobSeeker Payment was voted out of the
results entirely. Query decomposition that loses the main answer is worse than no
decomposition. There is now a regression test for exactly this.

## D4. The offline stack cannot answer situation questions, and says so

**Finding, not a decision.** The `hashing` embedder is feature hashing over words,
so it matches vocabulary, not meaning. Compound words defeat it too: "childcare"
does not match "child care", and "lost my job" does not match "looking for work".
On the fixture corpus the compound items therefore fall below the floor and refuse.

That is the correct behaviour for a system that cannot answer them, and it is the
measurement that justifies the cost of a real embedding provider. Do not tune the
floor down to make these pass. Set `SAAL_EMBED_PROVIDER=voyage` and rerun.

## D5. The suite runs against synthetic fixtures until Day 1

**Chosen.** `evals/fixtures/corpus.json` is ten hand written pages at
`example.invalid`, shaped like the real ones.

**Why.** The harness has to be testable before the corpus exists, and copying real
content into the repository to test a crawler is both a licensing question and a
staleness trap. The fixture numbers measure the harness. Only a run against the
crawled corpus produces a number worth quoting.

## D6. The stub provider is not a model and never pretends to be

**Chosen.** `StubProvider` composes an answer from chunk structure: the lead
sentence, the "Who can get it" bullets, the "How to claim" section.

**Why.** It exercises the contract, all six validator rules and the whole scorer with
no key and no network, which means the eval harness itself is under test. Its scores
are a floor, not a result, and the scorecard header names the provider on every run
so no number is ever quoted without it.
