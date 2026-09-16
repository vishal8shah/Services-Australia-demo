# Services Australia answer layer, unofficial prototype

**What it does.** Takes one plain language sentence in any language, returns the payment families that apply, who each is for, the eligibility signals, the ordered next steps, and a link to the official page with that page's own last updated date against every claim.

**What it refuses to do.** Anything about your record, your claim status, your balance, wait times, or dollar amounts. It holds no personal data and rejects any input containing an identifier.

Not affiliated with Services Australia or the Commonwealth. Content is sourced from public pages, Commonwealth of Australia, CC BY 4.0. For anything about your own circumstances, use myGov or call Services Australia.

---

| Document | What it is |
|---|---|
| [`PROTOTYPE_PLAN.md`](PROTOTYPE_PLAN.md) | Scope, architecture, the five day build with exit criteria, risks, publishing posture |
| [`evals/golden_questions.md`](evals/golden_questions.md) | 30 golden questions, 8 refusal probes, 4 over refusal controls, and the release gates |
| [`docs/answer_contract.md`](docs/answer_contract.md) | The response schema, the validator rules, the refusal classes |

**Current status:** plan committed, Day 0 measurement not yet run. Start at the appendix of the plan.
