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

## D7. No embedding key needed: expand the query instead

**Context.** There is no Voyage key, and the offline embedder cannot bridge meaning.

**Chosen.** Query expansion as the primary path, using the Anthropic key that
synthesis already requires. One small, fast model call rewrites the situation into
the vocabulary the pages use, and those phrases join the retrieval as a third tier
of query, weighted below the person's own words. The embedding providers stay
available for anyone who wants one: `gemini` on the free tier needs no card, `local`
needs `sentence-transformers` and no key at all, `voyage` is the paid option.

**Measured before recommending it.** `python3 -m evals.run --expander oracle` runs
the suite with hand written expansions taken from the fixture corpus vocabulary,
which is the best an expander could possibly do on this corpus. On the same corpus
and the same stub generator:

| | no expansion | oracle expansion |
|---|---|---|
| retrieval recall | 0.82 | **1.00** |
| payment recall | 0.54 | **0.82** |
| compound recall | 0.00 | **0.67** |
| refusal precision | 8 of 8 | 8 of 8 |
| over refusal | 0 of 4 | 0 of 4 |

The oracle is an upper bound, not a measurement of the real expander, and every
scorecard it writes says so in the header. What it settles is whether expansion is
worth one extra call per question. It is.

**The expander is allowed to guess.** Nothing it produces can reach the user: it
only changes which chunks are retrieved, and validator rule 3 still requires every
payment named in an answer to appear verbatim in a chunk that answer cites.

## D8. Coverage weighting is not fusion weighting

**A slip worth recording.** Facet weighting was reused for the confidence
calculation as well as the ranking, which discounted evidence found through a facet
even though a facet is the person's own words. Payment recall fell from 0.54 to 0.39
until it was separated: fusion weight stops facets outvoting the sentence in the
ranking, coverage weight decides what counts as evidence, and only expansions are
second hand. The eval suite caught it in one run.

## D9. Retrieval recall is reported next to answer recall

**Chosen.** Every response carries the titles it retrieved, and the scorer reports
whether the expected family was among them, separately from whether it reached the
answer.

**Why.** Under oracle expansion the three remaining failures all had the correct page
in the retrieved set: the stub generator caps itself at two payments and dropped
them. Retrieval recall 1.00 against payment recall 0.82 says the retriever is not the
problem. Without the split, that reads as a retrieval failure and sends the next day
of work in exactly the wrong direction.

## D10. One key, three roles, one transport

**Chosen.** OpenAI and Anthropic are both supported for all three model roles:
synthesis, query expansion, and the eval judge. Which one runs is three environment
variables, and every model name is overridable because model names get retired.

```bash
export OPENAI_API_KEY=sk-...
export SAAL_LLM_PROVIDER=openai SAAL_EXPANDER=openai SAAL_EMBED_PROVIDER=openai
```

**Why one transport.** Both APIs are a single POST with a JSON body. They differ in
the endpoint, the auth header, and whether JSON mode is a request parameter or a
prompt instruction. That is a twenty line difference, so it lives in `saal/llm.py`
and the synthesiser, the expander and the judge share it. Before this there were
three near copies of the same urllib call, which is three places for a timeout or a
retry to be handled differently by accident. No SDK either: a dependency that has to
be installed before the demo runs is a dependency that can fail before the demo runs.

**Embedding width is a latency decision.** Cosine runs in pure Python, so
`text-embedding-3-small` is requested at 512 dimensions rather than its full 1536.
The 3 series supports native shortening and keeps most of its quality at a third of
the width. If recall matters more than milliseconds, raise
`SAAL_OPENAI_EMBED_DIMS` and rerun `make index`.

**Failures are surfaced, not swallowed.** A missing key fails when the provider is
constructed, not on the first question, because "no answer found" is the wrong face
for a configuration error. A wrong model name or an exhausted balance comes back
with the provider's own message attached. `make doctor` makes one cheap call per
configured role so all of this is found before a crawl, not during a demo. The
transport is unit tested against a fake urlopen, so the request shape, the JSON
parsing and both failure modes are covered without a key, a network or a balance.

## D11. Secrets have two guards, because one is not enough

**Chosen.** `.env` is gitignored, loaded automatically by every entry point, and
never overrides a value already in the shell. `make hooks` installs a pre commit
hook that refuses to commit an env file or anything shaped like an API key.

**Why both.** Before this, `.gitignore` covered `data/` and `__pycache__` but not
`.env`, so the first real key written to disk would have been committed on the next
`git add -A`. Ignoring the file fixes that one path. The hook covers the other one,
a key pasted into a source file or a notebook, which no ignore rule catches. Both
were tested by staging a fake key and watching the commit fail.

**Why the shell wins over the file.** A stale `.env` silently overriding the key you
just exported is an hour of debugging that should not be available to anyone. The
loader uses `setdefault`, and there is a test for exactly that.

**No python-dotenv.** It is twenty lines, and it would be the only thing standing
between a fresh clone and a working `make test`.

## D12. A Claude key alone is enough, and embeddings are the optional part

**Context.** Anthropic publishes no embeddings endpoint, which reads like a gap when
the retrieval design calls for vectors.

**It is not one.** The thing that fails on this corpus is not vector search, it is
vocabulary: the pages say "constant care" and "looking for work", people say "Mum is
moving in with us" and "I got let go". Query expansion attacks that directly, and
the oracle ablation in D7 measured it closing the retrieval recall gap completely,
0.82 to 1.00, with the offline embedder left in place the whole time. An embedding
provider is a second, weaker route to the same bridge.

So with a Claude key: `SAAL_LLM_PROVIDER=anthropic` and `SAAL_EXPANDER=anthropic`,
and `SAAL_EMBED_PROVIDER` stays on `hashing`. With both keys, Claude writes the
answers and OpenAI can do the embeddings, which is belt and braces rather than a
requirement.

**`make doctor` checks the combination, not just the roles.** Offline embeddings and
no expansion is a working configuration by every per role check, and answers nothing
a person actually asks. That pairing now prints a warning naming the consequence,
because a setup that looks green and refuses every real question is the worst of the
available failure modes.
