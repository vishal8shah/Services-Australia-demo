# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

An unofficial answer layer over the public Services Australia individuals content.
One plain language sentence in, the payment families that apply out, with a source
link and that page's own last updated date against every claim. It refuses anything
touching a person's record, a claim status, a wait time or a dollar amount.

Read `PROTOTYPE_PLAN.md` first. `docs/decisions.md` records what was chosen and why,
including defects the eval suite caught. Add to it rather than rediscovering them.

## Commands

```bash
make check     # Python 3.11+ and sqlite FTS5, runs before every other target
make doctor    # which keys and providers actually work, run this first
make test      # 99 unit tests, offline, nothing to install
make eval      # golden suite on the synthetic fixture corpus
make measure   # Day 0: is crawling permitted, how many pages, which families
make crawl     # fetch the corpus, honours the declared crawl delay
make index     # chunk and embed
make serve     # API and the single page on http://127.0.0.1:8000
```

## Layout

| Path | What it holds |
|---|---|
| `saal/ingest/` | crawl, extract, chunk, embed |
| `saal/retrieve/` | hybrid search, weighted fusion, the confidence floor, query expansion |
| `saal/answer/` | contract, identifier guard, refusal classes, prompt, providers, validator |
| `saal/pipeline.py` | the whole flow, every exit is an answer or a refusal |
| `saal/llm.py` | one chat transport for OpenAI and Anthropic |
| `evals/` | golden suite, runner, committed scorecards |

## Rules that are not up for negotiation

1. **The core runs on the standard library.** Optional extras are optional. A fresh
   clone must pass `make test` with nothing installed. Override the interpreter with
   `make PYTHON=python3.12 <target>` rather than adding a virtualenv requirement.
2. **Never weaken a validator rule to make an answer pass.** The six rules in
   `docs/answer_contract.md` are the product. If a rule blocks a good answer, the
   retrieval or the prompt is wrong, not the rule.
3. **Never lower the score floor to make the fixture suite pass.** The fixture
   corpus is synthetic and the offline embedder matches spelling, not meaning.
   Refusals there are correct. See decision D4.
4. **Never copy live site content into this repository.** The fixture corpus is
   hand written and lives at `example.invalid` on purpose.
5. **Never log or store a question.** The product promise is that nothing personal
   is kept, and a web log full of people's circumstances breaks it quietly.
6. **Commit failing scorecards too.** A suite that only records its wins proves
   nothing.
7. **Secrets:** `.env` is gitignored and loaded automatically. Run `make hooks`
   once per clone. Never put a key in a source file, a test or a commit message.

## Where things stand

Days 0 and 1 are done (2026-09-17/18). The site dropped its /individuals/ section, so
scope is by payment family and page type (`saal/ingest/scope.py`, D14, D17): 379
pages, 1,805 chunks, OpenAI embeddings. `make trace` anchors 29 of 31 golden items.
The latest real scorecard is `evals/runs/2026-09-18-091008` (D21): every safety gate
passes; payment recall 0.76, compound recall 0.67, faithfulness 0.93 and median
latency 11.2s are still below their gates. The interface (`web/index.html`) takes
voice or text in 24 languages and shows retrieval progress from `/api/plan` (D20).
A recorded, static copy of it is published with GitHub Pages (D22, D23).

**Next step, in order:**

1. Family Tax Benefit on family questions (F1, F3, F4): the largest remaining recall
   gap, and it varies run to run with the expander's phrases (D21). Measure expander
   variance first; never lower the floor.
2. Golden items D2 and B2 expect topics ("compensation", "relationship status") that
   the payments list cannot hold. Decide with the owner whether the suite or the
   contract changes.
3. Latency to the 6s gate: synthesis output length is now the cost, not thinking.
4. Recrawl on a schedule; disaster event pages open and close (D17).
