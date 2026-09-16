.PHONY: help test eval eval-real measure serve crawl index clean

help:
	@echo "make test      run the unit tests, offline, nothing to install"
	@echo "make eval      run the golden suite on the synthetic fixture corpus"
	@echo "make eval-real run the golden suite on the crawled corpus"
	@echo "make measure   Day 0: is crawling permitted, and how many pages are there"
	@echo "make crawl     fetch the corpus (needs network)"
	@echo "make index     rebuild chunks and vectors from the fetched pages"
	@echo "make serve     run the API and the page on http://127.0.0.1:8000"

test:
	python3 -m unittest discover -s tests

eval:
	python3 -m evals.run

eval-real:
	python3 -m evals.run --corpus real --provider anthropic --judge anthropic --strict

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
