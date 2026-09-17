PROVIDER ?= openai

.PHONY: help test eval eval-oracle eval-real doctor measure serve crawl index clean

help:
	@echo "make doctor      check which keys and providers actually work"
	@echo "make test        run the unit tests, offline, nothing to install"
	@echo "make eval        golden suite on the synthetic fixture corpus"
	@echo "make eval-oracle the same, with hand written expansions, an upper bound"
	@echo "make eval-real   golden suite on the crawled corpus, PROVIDER=$(PROVIDER)"
	@echo "make measure     Day 0: is crawling permitted, and how many pages are there"
	@echo "make crawl       fetch the corpus (needs network)"
	@echo "make index       rebuild chunks and vectors from the fetched pages"
	@echo "make serve       the API and the page on http://127.0.0.1:8000"

doctor:
	python3 -m saal.doctor

test:
	python3 -m unittest discover -s tests

eval:
	python3 -m evals.run

eval-oracle:
	python3 -m evals.run --expander oracle

eval-real:
	python3 -m evals.run --corpus real --provider $(PROVIDER) --expander $(PROVIDER) \
		--judge $(PROVIDER) --strict

measure:
	python3 -m saal.ingest.crawl --measure

crawl:
	python3 -m saal.ingest.crawl --limit $${LIMIT:-0} --branches "$${BRANCHES:-}"

index:
	python3 -m saal.ingest.chunk && python3 -m saal.ingest.embed

serve:
	python3 -m saal.api.main

clean:
	rm -f data/corpus.db data/raw/*.html
