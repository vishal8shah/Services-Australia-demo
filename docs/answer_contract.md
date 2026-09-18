# The answer contract

The reference the Day 2 build works from. There is one output shape and one refusal shape. No free prose path exists in the code, so there is no path where an unsourced sentence can reach a user.

---

## 1. Response schema

```jsonc
{
  "language": "vi",              // BCP 47, detected from the question
  "query_facets": ["caring for an ageing parent", "reduced work hours"],
  "refusal": null,               // object when refusing, see section 3
  "payments": [
    {
      "name": "Carer Payment",           // verbatim from a cited chunk, never paraphrased
      "one_liner": "...",                 // who it is for, one sentence
      "distinguisher": "...",             // how it differs from the payment beside it
      "eligibility_signals": [
        { "text": "...", "source_ids": ["c_412"] }
      ],
      "source_ids": ["c_412", "c_418"]
    }
  ],
  "next_actions": [
    { "order": 1, "text": "...", "url": "https://...", "source_ids": ["c_412"] }
  ],
  "sources": [
    {
      "id": "c_412",
      "title": "Who can get Carer Payment",
      "url": "https://...",
      "page_last_updated": "2026-07-14",
      "stale": false
    }
  ],
  "not_answered": ["How much you will receive: use the official estimator."]
}
```

**Field notes**

- `query_facets` is rendered in the interface. Showing the user how their sentence was decomposed is the cheapest trust signal available, and it is how they notice when a facet was missed.
- `distinguisher` exists because the single most common failure on the live site is not knowing that two similarly named payments are different things.
- `not_answered` is populated deliberately. An answer that quietly omits the money question feels evasive: an answer that names what it will not tell you and why does not.
- `stale` is set when `page_last_updated` is older than 18 months at query time, and a
  source with no date at all counts as stale: absence of evidence is not freshness.
- Chunk ids look like `c_9f3a21b7`, a hash of the page url, the heading path and the
  ordinal. They are keyed on location rather than content, so an edited paragraph keeps
  its id across a recrawl and the eval answer key survives a content refresh.

---

## 2. Validator

Runs after generation, in code. Prompt instructions are not a control.

| # | Rule | On failure |
|---|---|---|
| 1 | Every id in any `source_ids` exists in the retrieved set for this query | Refuse |
| 2 | Every eligibility signal and every next action carries at least one source id | Refuse |
| 3 | Every `payments[].name` appears verbatim in at least one chunk cited by that payment, matched against the chunk's title, heading path and text | Refuse |
| 4 | Every url in `next_actions` matches the url of a cited source | Strip the url, keep the action |
| 5 | Response parses against the schema | Retry once, then refuse |
| 6 | No dollar figure, wait time, or processing time appears anywhere in the output | Strip the sentence, add to `not_answered` |

Rule 3 is the one that does most of the work: the model cannot introduce a payment the corpus never mentioned. Rule 6 is a regex on the output, deliberately blunt, because the cost of a wrong rate quoted to someone in financial stress is not symmetric with the cost of a stripped sentence.

**Partial answers are never returned.** A validator failure returns the refusal path with the low confidence class. Half an answer with a broken citation is worse than no answer, because it looks exactly like a good one.

---

## 3. Refusal shape

```jsonc
{
  "refusal": {
    "class": "claim_status",
    "message": "...",            // in the user's language
    "offer": {                    // omitted when there is genuinely nothing to offer
      "text": "Check your claim in myGov",
      "url": "https://..."
    },
    "phone": "132 850"            // the relevant line, confirmed on Day 1
  }
}
```

**Classes**

| class | Trigger |
|---|---|
| `personal_record` | Anything about this person's claim, balance, or history |
| `claim_status` | Timing or progress of a claim |
| `amount` | A dollar figure. Always offer the official estimator |
| `wait_time` | Operational data we do not hold |
| `determination` | "Do I qualify". Reframe to signals, or refuse if the user insists on a yes |
| `out_of_corpus` | Business, health provider, or child support agency content |
| `out_of_scope` | Not Services Australia at all |
| `low_confidence` | Retrieval below the score floor, or a validator failure |
| `pii_detected` | The input contained an identifier. Refuse, and state that nothing was stored |

The `pii_detected` path runs **before** retrieval and before any model call, so an identifier never leaves the process.

---

## 4. Synthesis prompt structure

Four blocks, in this order:

1. **Role and hard boundaries.** The refusal classes, stated as absolutes.
2. **The retrieved chunks**, each with its id, heading path, url and last updated date.
3. **The schema**, with the instruction that any claim not supported by a chunk must be omitted rather than softened. Hedged language is a failure mode, not a safety valve: "may be eligible" reads as an answer to someone who is frightened.
4. **The question**, plus its decomposed facets.

Temperature 0. No examples of good answers in the prompt: few shot examples in this setting teach the model to imitate the shape of a confident answer, which is the opposite of what the validator is defending.

---

## 5. Language handling

- Detect, translate the query to English for retrieval, answer in the detected language.
- Payment names are **never translated**. Render the English name with a translated gloss beside it. A translated payment name is not searchable on the official site and not recognisable to staff on the phone, so translating it actively harms the user at the exact moment they need to act.
- Source titles and urls stay in English, so the answer can be handed to anyone.
- The refusal messages are translated too. A refusal that falls back to English is a refusal the user cannot read.
