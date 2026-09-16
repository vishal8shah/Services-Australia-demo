# Fixtures

**`corpus.json` is synthetic.** It is written by hand to mimic the shape of the real
pages: a lead paragraph, a "Who can get it" section, a "How to claim" section, and a
change of circumstances section. It is not copied from servicesaustralia.gov.au, the
urls are deliberately `example.invalid`, and nothing in it should be read as advice
or as an accurate statement of any payment rule.

It exists so the contract, the validator, the retriever and the scorer can be
exercised with no network and no model. The real corpus arrives on Day 1 and
replaces it for every run that produces a number anyone quotes.

`llm.json` is written by `SAAL_RECORD=1` against the real model and replayed by the
fixture provider, so the suite can be rerun without paying for it or waiting for it.
