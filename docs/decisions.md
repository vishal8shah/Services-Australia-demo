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

## D13. Two defects the first real key found

**No temperature on Anthropic calls.** `claude-sonnet-5` rejects `temperature` with
a 400, so synthesis failed in `make doctor` while expansion on Haiku passed. The
transport now sends no temperature to either provider, matching the OpenAI branch.
Contract rule 5 is unchanged in substance: one retry, then refuse.

**The test suite never reads `.env`.** The loader ran on import, so the moment a
`.env` set `SAAL_EXPANDER=anthropic` the offline suite started calling the API,
took 109 seconds instead of one, and failed the test that proves the default stack
refuses without expansion. `config` now skips env files when `unittest` is loaded.
Shell exports still apply, per D11. Found by running `make test` after `make doctor`
on a clone with a real key, which is exactly the order CLAUDE.md prescribes.

## D14. Scope by payment family and page type, because the branches are gone

**Context.** Day 0 found the site restructured. There is no `/individuals/` path any
more: all 4,304 sitemap urls sit at the root, mixing payment pages with forms
(`sa391`), audio translations, provider and lawyer guidance, statistics, and dated
disaster events. The prefix filter scoped 0 pages.

**Chosen.** `saal/ingest/scope.py` admits a url when its slug names a payment the
golden suite asks about *and* starts with a standard page type (`who-can-get-`,
`how-much-`, `how-to-claim-`, income and residence rules, ...), or is exactly that
payment's landing page. Cross cutting topics with no payment name (nominees, proof of
identity, compensation, relationship status, aged care cost, evergreen disaster
support) are listed by exact slug. Audience and format words (`translation`,
`providers`, `professionals`, ...) exclude first. Result: 296 pages, about 49 minutes
at the declared 10 second delay. `--branches` became `--families`.

**Rejected.** Payment name alone admitted 1,081 pages, most of them long tail an
answer should never cite. The full sitemap is 12 hours of crawling for mostly out of
corpus content. Dated disaster event pages (`vic-bushfires-jan-2026-dra`) are left out
on purpose: they expire, and a corpus that cites a closed event is worse than one that
refuses.

**Known gap for Day 1.** No evergreen page is named for Disaster Recovery Payment or
Disaster Recovery Allowance; those live only on per event pages now. `make trace` will
flag them, and the answer is a scope or golden suite decision, not a retrieval fix.

## D15. Every file read and write names its encoding

`read_text()` and `write_text()` without an encoding use the platform default, which
is cp1252 on Windows. The crawler writes raw HTML and the eval runner writes
scorecards containing the golden suite's non English questions, so the first page
or question outside cp1252 would have crashed a crawl or a run partway through. It
never showed on macOS or Linux, where the default is already UTF-8. Every
`read_text`, `write_text` and file read in `saal/`, `evals/` and `tests/` now passes
`encoding="utf-8"`.

## D16. A page's title comes from og:title, not its h1

**Found by `make trace` on the first real corpus.** 20 of 31 golden items could not
be anchored, and the chunks retrieved in their place were titled "Who can get it",
"How to claim", "How much you can get". About 190 of the 296 pages have an h1 that
does not name the payment it belongs to; the payment is only in `og:title` and the
document title ("Who can get JobSeeker Payment - JobSeeker Payment - Services
Australia"). The extractor preferred the h1, so most chunks were anonymous to
retrieval: FTS indexes the title, and the title said nothing.

**Chosen.** Title order is `og:title`, then the first segment of `<title>` split on
` | ` or ` - `, then the h1. Separately, the audio player's "Listen" label had become a
chunk of its own on every page (294 of them); it is now boilerplate. Corpus went from
1,684 chunks to 1,390, and traced items from 11 to 19 with no change to the floor,
the validator or the golden suite.

## D17. Day 1 judgement calls on the 12 untraced items

Decided with the owner after D16 left 12 of 31 golden items without an anchor.

**Expected name was wrong: A2, B2.** The site no longer uses the words the suite
expected. "aged care means assessment" appears in no chunk; the page is "Aged care
calculation of your cost of care". "member of a couple" survives only in body text; the
page is "Updating your relationship status". Both expectations now use the site's own
title wording, in `golden.json` and `golden_questions.md` together. The answer key
comes from the corpus, per CLAUDE.md.

**Scope was too narrow: X2.** Disaster Recovery Payment and Allowance exist only as
per event pages. D14 left those out because they expire; the owner chose to include
them. `scope.py` admits slugs ending in a payment code (`agdrp`, `dra`, `drp`) and
event landing pages named for a disaster and a month and year: 83 pages across five
events. They must be recrawled as events open and close, or the corpus will cite
closed claims.

**Retrieval was failing: C1, F1, F2, F3, F4, D1, S1, A4, X4.** Every expected payment
here is in the corpus. The offline embedder matches spelling, and near identical
"Change of circumstances for X" pages crowded out the right one on situation and
compound questions. `SAAL_EMBED_PROVIDER=openai` (text-embedding-3-small, 512
dimensions) replaces it. Not changed: the score floor, the validator, the fusion
weights. If semantic retrieval does not close these, the next suspect is the
generic page type pages, not the floor.

## D18. Two defects the first live demo found

**The server hung on the first browser visit.** `http.server.HTTPServer` handles one
connection at a time, and Chromium opens speculative preconnect sockets that send
nothing. The server waited on one of those forever and every real request queued
behind it. It is now `ThreadingHTTPServer`; the single sqlite connection is shared
across worker threads behind a lock (`check_same_thread=False`), so requests take
turns on the corpus and an idle socket blocks nobody.

**Every live answer refused with "no JSON in model output: ''".** `claude-sonnet-5`
runs adaptive thinking by default, and thinking spends output tokens before the first
text block. Synthesis allowed 2,000; a probe used 1,677 of them, 501 on thinking,
and a real query with more context ran out mid thought and returned no text. The
validator then refused, correctly. Synthesis now allows 16,000, the transport reads
only `text` blocks, and it raises a named error on `stop_reason` `max_tokens` with no
text or on `refusal`, instead of passing an empty string along. Scenario A now
answers with Carer Payment and Carer Allowance and three dated sources, in about 22
seconds, most of it thinking.

## D19. The first real scorecard: 2026-09-18-070947, fails 4 of 7 gates

Real corpus (379 pages, 1,805 chunks, openai:512), Claude for synthesis, expansion
and the judge. Recorded as it came out, per CLAUDE.md rule 6.

| gate | value | gate | |
|---|---|---|---|
| payment_recall | 0.74 | 0.90 | fail |
| compound_recall | 0.58 | 0.80 | fail |
| citation_faithfulness | 0.84 | 1.00 | fail |
| fabricated_payment_rate | 0.00 | 0.00 | pass |
| refusal_precision | 1.00 | 1.00 | pass |
| over_refusal_rate | 0.00 | 0.05 | pass |
| latency_p50_s | 25.7 | 6.0 | fail |

**What held.** Every safety gate: no invented payment, all eight refusal probes
refused with the right class, no answerable question refused.

**Recall.** 10 of 31 answer items fail. Six are the second payment of a compound
question that trace had already flagged (Family Tax Benefit in F1, F3, F4; Child Care
Subsidy in F2; Commonwealth Seniors Health Card in A4 behind "Assets test for X"
pages; Carer Allowance in C1). C1 also returned no payments at all after 90 seconds
without refusing, where the same question answered correctly in the demo the day
before: a non determinism to chase. D1, D2, A3, B2 are synthesis choosing a
neighbouring payment over the expected one.

**Faithfulness.** Three causes, not one. Real synthesis faults: a one liner reading
"A payment mentioned in these chunks that has...", and Mobility Allowance offered
for reduced work hours. Judge shape: each claim is judged against each cited chunk
separately, so a claim that three chunks support together fails three times.
Procedural next actions ("Check the full eligibility rules") are judged as factual
claims. The judge rubric is a scoring decision for the owner; it has not been changed.

**Latency.** Median 25.7s against a 6s gate, most of it Sonnet 5's default adaptive
thinking on synthesis. `output_config.effort` is the lever to measure next.

## D20. Owner delegated the D19 calls: judge together, low effort, rank by page type

The owner asked for best judgement, aimed at a live hackathon demo. Chosen:

**Judge claims against their cited chunks together.** Contract rule 1 says every claim
maps to the retrieved set; it never required each chunk alone to carry the whole
claim. One verdict per claim over all its cited chunks, and "open the page" next
actions count as supported when that page is cited. Faithfulness rose 0.84 to 0.89
on the intermediate run.

**`output_config.effort: low` on synthesis** (`SAAL_SYNTH_EFFORT`). Measured on W2 and
W3: low returned as many or more payments than the model default, in 8 to 10s
against 12 to 15s. Correctness is enforced by the validator in code, not by thinking.

**Retrieval, ranking only, confidence untouched:**
- *Expander grounded in the corpus.* It now gets the list of payment names in scope
  and may name any that commonly apply, in English whatever the question's
  language. Family Tax Benefit had never been proposed for a family question.
- *Known item lookup.* A query or expansion that is exactly a payment's name adds
  that payment's own page and its "Who can get" page as a ranking. BM25 had ranked
  "Who can get Carer Payment" 25th for the query "Carer Payment".
- *Page type prior.* Rule pages ("Income test for X", "Assets test for X", "Change of
  circumstances...", "When you'll get...") rank at 0.5; "Who can get" and landing
  pages at 1.5; dated disaster event pages get no boost. At most two chunks per page
  in the top eight, which leaves room for a compound question's second payment.
Trace went 25 to 29 of 31, and the fixture suite still passes its recall gates.

**Multilingual end to end.** The interface sends the speech recogniser's language
(`vi-VN`, `pa-Guru-IN`, `yue-Hant-HK`); `language.normalise` maps it, synthesis is
told the language by name, and an undetected Latin script language falls back to
"the same language the QUESTION is written in". Verified live in Vietnamese,
Italian and Arabic: payment names stay English with a translated gloss.

**Interface.** `/api/plan` returns facets, English search phrases and the pages found
in a few seconds, alongside `/api/answer`, so the wait shows the system working.
The server now opens a sqlite connection per request for the crawled corpus, so
the two run in parallel, and sends `Cache-Control: no-cache` on static files.
Voice input uses the browser's Web Speech API; the page says plainly that the
browser's speech provider transcribes the audio and this tool never receives it.

## D21. Scorecard 2026-09-18-091008, after D20: better on every gate, still 4 failing

| gate | D19 (070947) | D21 (091008) | gate |
|---|---|---|---|
| retrieval_recall (diagnostic) | 0.82 | 0.89 | |
| payment_recall | 0.74 | 0.76 | 0.90 |
| compound_recall | 0.58 | 0.67 | 0.80 |
| citation_faithfulness | 0.84 | 0.93 | 1.00 |
| fabricated_payment_rate | 0.00 | 0.00 | 0.00 |
| refusal_precision | 1.00 | 1.00 | 1.00 |
| over_refusal_rate | 0.00 | 0.00 | 0.05 |
| latency_p50_s | 25.7 | 11.2 | 6.0 |

Nine answer items fail, and they split cleanly in two:
- **Retrieval had the page, synthesis returned nothing** (W4, A3, D2, B2, all
  retrieval recall 1.0, no refusal): the model reads "only when the situation
  matches" too strictly and empties the payments list. Next lever is the prompt,
  not the floor or the validator.
- **Family Tax Benefit still missed at retrieval** on three family questions (F1, F3,
  F4) and Special Benefit on X4, varying run to run with the expander's phrases.
  C1 found Carer Payment but not Carer Allowance on this run; it found both in the
  direct check an hour earlier. Expander variance is now the largest single source
  of noise in the suite.

## D22. Submission day: an over-cautious prompt, and a demo anyone can open

**Prompt.** D20's "include a payment only when the situation matches" made synthesis
return an empty payments list even with the right page retrieved (W4, A3, D2, B2 in
D21). Reworded: include every payment a chunk describes as for people in the person's
situation, even when individual eligibility cannot be confirmed, since checking
eligibility is theirs; return an empty list only when no chunk describes a payment
for their situation. Rechecked live: W4, A3 and C1 now pass. D2 and B2 expect topics
("compensation", "relationship status") that the payments list cannot hold; that is
a golden suite shape question, left for the owner.

**Recorded demo.** A public audience cannot run the server, so the interface is also
published as a page that replays real `/api/plan` and `/api/answer` outputs recorded
from the pipeline for the eight example chips, and says so in its notice bar.
Recordings live outside the repository (rule 4). Two of eight were re-recorded once
because the first run missed a payment the second found (Vietnamese Scenario A,
Chinese flood); that selection is disclosed here rather than hidden.

## D23. Published with GitHub Pages, from a separate repository

The recorded demo and the deck are served from `vishal8shah/payment-finder`
(https://vishal8shah.github.io/payment-finder/), not from this repository. The recordings are model answers derived
from live Services Australia pages, and rule 4 keeps live content out of this repo;
a separate site repository keeps that line clean while still giving a public URL.
A normal web page, unlike an artifact viewer, can ask for the microphone, so voice
input works on the published demo. The site is rebuilt from `web/index.html` and
`docs/deck.html` plus the recordings; the builder lives outside the repo with them.
