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
make doctor    # which keys and providers actually work, run this first
make test      # 74 unit tests, offline, nothing to install
make eval      # golden suite on the synthetic fixture corpus
make measure   # Day 0: is crawling permitted, how many pages, which branches
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
   clone must pass `make test` with nothing installed.
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

Pipeline complete and tested end to end. Day 0 has not been run: the environment
this was built in cannot reach servicesaustralia.gov.au, so every number in
`evals/runs/` comes from the synthetic corpus and measures the harness, not the
product.

**Next step, in order:**

1. `make doctor` with a key in `.env`.
2. `make measure`, then write the four TBD values into the Day 0 appendix of
   `PROTOTYPE_PLAN.md`. The real page count decides full corpus or three branches.
3. `make crawl && make index`.
4. Day 1 proper: trace each expected answer in `evals/golden_questions.md` to a real
   chunk id and correct the ones the corpus does not support. The answer key comes
   from the corpus, never from the model and never from memory.
5. `make eval-real`, and commit the first scorecard that means something.
