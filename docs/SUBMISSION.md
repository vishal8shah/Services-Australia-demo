# Build submission: Payment Finder

Draft answers for the Claude "Show off what you built" form
(https://form.typeform.com/to/SygLMeAD). Read the terms before submitting:
https://support.claude.com/en/articles/15485501. The three checkboxes grant Anthropic
a perpetual licence to feature what you submit, so only tick them if every line in
"Anything we should know?" is accurate for you.

Your name, email, location and social handles are yours to fill in.

---

**Project name**

Payment Finder

**One-line description**

Say what's happening in your life, in your own language, and see which Australian
government payments apply, with the official page and its date behind every line.

**Link to the build**

- Recorded demo, public, runs in any browser: https://vishal8shah.github.io/payment-finder/
- Deck: https://vishal8shah.github.io/payment-finder/deck.html
- Repository: https://github.com/vishal8shah/Services-Australia-demo (it must be public
  for reviewers to open it). A repo lets people run the live version.

**Screenshots or video (optional, recommended)**

A 60 to 90 second screen recording of the live local version does the most work:
1. Tap the mic and say Scenario A in Vietnamese or another language.
2. Pause on the progress panel while the facets, English search phrases and dated
   official pages appear.
3. Scroll the answer: payment cards, numbered source chips, next steps, "What this
   can't tell you". Press Read aloud.
4. Type "How much will I get for Carer Payment?" to show it refusing rather than guessing.

**How Claude contributed**

Claude is in the product and built it.

- In the product: Claude Sonnet 5 writes every answer into a fixed JSON contract, in
  the person's own language, using only retrieved passages from the official pages.
  Claude Haiku 4.5 rewrites the person's situation into the pages' English
  vocabulary before search, and judges every cited claim in the eval suite.
- Building it: Claude Code (Claude Opus 5) worked as the engineer across two days.
  It measured the live site and found it had dropped its /individuals/ section,
  rescoped the crawl to 379 pages by payment family, built the retrieval, validator,
  multilingual voice interface and the deck, and tuned retrieval by scorecard (golden
  items anchored to a real passage went from 11 of 31 to 29 of 31).
- Keeping it honest: six answer-contract rules are enforced in code after the model
  writes, so an unsourced line or an invented payment becomes a refusal. The eval
  suite caught nine real defects, each recorded with its fix in docs/decisions.md,
  and failing scorecards were kept. On the real corpus: 0 fabricated payments, 100%
  refusal precision, 0% over-refusal, faithfulness 0.93, median answer 11 seconds.

**Anything we should know?**

- Content: answers are generated from public pages published by Services Australia,
  © Commonwealth of Australia, reused under CC BY 4.0 with attribution on every page
  of the build. The project is unofficial and not affiliated with or endorsed by
  Services Australia; the interface says so above the fold and uses none of its
  branding.
- The recorded demo replays answers the pipeline generated live on 18 September 2026
  for eight example situations; it is labelled as recorded on the page.
- Third-party services: OpenAI text-embedding-3-small for search embeddings. Voice
  input uses the browser's Web Speech API, which in Chrome and Edge sends audio to the
  browser vendor for transcription; the build never receives or stores it, and the
  page says this.
- Fonts: Schibsted Grotesk, Source Serif 4 and IBM Plex Mono via Google Fonts, under
  the SIL Open Font License.
- No people, faces or voices appear in the materials. No personal data is collected.

**Preferred attribution**

Your choice, for example your name or team name.
