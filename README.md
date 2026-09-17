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

## Work on it locally

```bash
git clone https://github.com/vishal8shah/Services-Australia-demo.git
cd Services-Australia-demo
make hooks          # blocks committing a key, takes a second, do it first
cp .env.example .env
make doctor
```

`data/` is not in git: the corpus is rebuilt with `make crawl && make index`, which
keeps crawled government content out of the repository and the clone small.

`make hooks` installs a pre commit hook that refuses to commit an env file or
anything shaped like an API key. `.env` is gitignored, and `.env` is read
automatically by every entry point, so nothing needs `set -a` or a shell profile
edit. Anything exported in your shell wins over the file.

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

## Add your key

One key covers all three roles. Put it in `.env` and check it:

```bash
cp .env.example .env
# edit .env, then
make doctor
```

`.env` is loaded automatically and is gitignored. `SAAL_ENV_FILE=/path/to/secrets`
points somewhere outside the working tree if you would rather keep it there.

`make doctor` makes one cheap call per configured role and tells you which are
live. Run it before the crawl, not after.

```bash
export OPENAI_API_KEY=sk-...
export SAAL_LLM_PROVIDER=openai    # writes the answer
export SAAL_EXPANDER=openai        # rewrites the question into page vocabulary
export SAAL_EMBED_PROVIDER=openai  # makes retrieval semantic, rerun `make index` after
```

A Claude key works the same way: `ANTHROPIC_API_KEY`, and `anthropic` in place of
`openai` for synthesis and expansion. Anthropic has no embeddings endpoint, which
does not matter here: expansion is what bridges a person's wording to the vocabulary
of the pages, and it closed more of the gap than embeddings were asked to. Leave
`SAAL_EMBED_PROVIDER` on the offline default. Model names are all overridable, because they get retired:
`SAAL_MODEL`, `SAAL_FAST_MODEL`, `SAAL_OPENAI_EMBED_MODEL`. Check what your key can
see with `curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"`.

Embeddings are optional. The alternatives, if you would rather not spend on them:
`gemini` on the free tier needs no card, `local` needs `pip install
sentence-transformers` and no key, `voyage` is paid, and `hashing` is the default
that needs nothing and bridges spelling but never meaning.

Two switches worth knowing:

```bash
export SAAL_RECORD=1          # record live answers into evals/fixtures/llm.json
export SAAL_DEMO_MODE=static  # replay them, no live model calls at all
```

To see what expansion buys before spending anything:

```bash
make eval           # retrieval recall 0.82, payment recall 0.54
make eval-oracle    # retrieval recall 1.00, payment recall 0.82
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
