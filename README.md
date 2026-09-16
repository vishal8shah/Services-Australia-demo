# Services Australia answer layer, unofficial prototype

**What it does.** Takes one plain language sentence, in any language, and returns the
payment families that apply, who each is for, what the eligibility rules say, the
ordered next steps, and a link to the official page with that page's own last updated
date against every claim.

**What it refuses to do.** Anything about your record, your claim status, your balance,
wait times, or dollar amounts. It holds no personal data, it rejects any input that
contains an identifier, and it never logs the question.

Not affiliated with Services Australia or the Commonwealth. Content is sourced from
public pages, Commonwealth of Australia, reused under CC BY 4.0. For anything about
your own circumstances, use myGov or call Services Australia.

---

## Run it

Nothing to install. Python 3.11 and the standard library.

```bash
make test     # 47 unit tests, offline
make eval     # the golden suite against the synthetic fixture corpus
make serve    # http://127.0.0.1:8000
```

With no crawled corpus present, the server and the suite both fall back to
`evals/fixtures/corpus.json`, which is ten hand written synthetic pages. Those runs
measure the harness, not the product.

## Build the real corpus

```bash
make measure                    # Day 0: robots, sitemap, page count by branch
make crawl                      # polite crawl, honours the declared crawl delay
make index                      # chunk and embed
make eval-real                  # the suite against the crawled corpus
```

Optional upgrades, all read from the environment:

```bash
export SAAL_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...  # real synthesis
export SAAL_EXPANDER=claude                               # recommended: rewrites the
                                                          # question into page vocabulary,
                                                          # same key, one small call
export SAAL_RECORD=1                                      # record responses for replay
export SAAL_DEMO_MODE=static                              # no live model calls at all
```

Semantic embeddings are optional and there are three ways to get them, none of them
required:

```bash
export SAAL_EMBED_PROVIDER=gemini GEMINI_API_KEY=...   # free tier, no card
export SAAL_EMBED_PROVIDER=local                       # pip install sentence-transformers
export SAAL_EMBED_PROVIDER=voyage VOYAGE_API_KEY=...   # paid
make index                                             # changing the embedder rebuilds every vector
```

To see what expansion buys before paying for anything:

```bash
python3 -m evals.run                     # retrieval recall 0.82, payment recall 0.54
python3 -m evals.run --expander oracle   # retrieval recall 1.00, payment recall 0.82
```

The oracle is hand written from the fixture vocabulary, so it is the ceiling rather
than a measurement. `docs/decisions.md` D7 has the full table.

## What is here

| Path | What it is |
|---|---|
| [`PROTOTYPE_PLAN.md`](PROTOTYPE_PLAN.md) | Scope, architecture, the five day build with exit criteria, risks, publishing posture |
| [`docs/answer_contract.md`](docs/answer_contract.md) | The response schema, the six validator rules, the refusal classes |
| [`docs/decisions.md`](docs/decisions.md) | What was chosen and why, including two defects the eval suite caught |
| [`evals/golden_questions.md`](evals/golden_questions.md) | 31 golden questions, 8 refusal probes, 4 over refusal controls, and the release gates |
| [`evals/golden.json`](evals/golden.json) | The machine readable answer key, kept in step with the markdown by a test |
| [`evals/runs/`](evals/runs) | Every scorecard, passing or failing |
| `saal/ingest/` | Crawl, extract, chunk, embed |
| `saal/retrieve/` | Hybrid search, weighted reciprocal rank fusion, the confidence floor |
| `saal/answer/` | Contract, identifier guard, refusal classes, prompt, providers, validator |
| `saal/api/`, `web/` | The service and the single page |

## Status

Plan committed, pipeline built and tested end to end, Day 0 measurement not yet run.
The crawl target is not reachable from the environment this was built in, so every
number in the current scorecard comes from the synthetic corpus. Start at the Day 0
appendix of the plan.
