PROVIDER ?= openai
# macOS ships an older python3. Point this at a 3.11+ interpreter if `make check`
# complains: make PYTHON=python3.12 test
PYTHON ?= python3

.PHONY: help check test eval eval-oracle eval-real doctor hooks measure trace serve crawl index clean

help:
	@echo "make doctor      check which keys and providers actually work"
	@echo "make hooks       install the pre commit hook that blocks committing a key"
	@echo "make check       confirm this Python is new enough and has sqlite FTS5"
	@echo "make test        run the unit tests, offline, nothing to install"
	@echo "make eval        golden suite on the synthetic fixture corpus"
	@echo "make eval-oracle the same, with hand written expansions, an upper bound"
	@echo "make eval-real   golden suite on the crawled corpus, PROVIDER=$(PROVIDER)"
	@echo "make measure     Day 0: is crawling permitted, and how many pages are there"
	@echo "make crawl       fetch the corpus (needs network)"
	@echo "make index       rebuild chunks and vectors from the fetched pages"
	@echo "make trace       Day 1: trace each expected answer to a real chunk id"
	@echo "make serve       the API and the page on http://127.0.0.1:8000"

check:
	@$(PYTHON) scripts/preflight.py

doctor: check
	$(PYTHON) -m saal.doctor

hooks:
	@cp scripts/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit \
		&& echo "installed .git/hooks/pre-commit"

test: check
	$(PYTHON) -m unittest discover -s tests

eval: check
	$(PYTHON) -m evals.run

eval-oracle: check
	$(PYTHON) -m evals.run --expander oracle

eval-real: check
	$(PYTHON) -m evals.run --corpus real --provider $(PROVIDER) --expander $(PROVIDER) \
		--judge $(PROVIDER) --strict

measure: check
	$(PYTHON) -m saal.ingest.crawl --measure

crawl: check
	$(PYTHON) -m saal.ingest.crawl --limit $${LIMIT:-0} --branches "$${BRANCHES:-}"

index: check
	$(PYTHON) -m saal.ingest.chunk && $(PYTHON) -m saal.ingest.embed

trace: check
	$(PYTHON) -m evals.trace

serve: check
	$(PYTHON) -m saal.api.main

clean:
	rm -f data/corpus.db data/raw/*.html
