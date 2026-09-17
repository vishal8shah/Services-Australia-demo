"""Day 1 helper: trace every expected answer to a real chunk id.

The rule in the plan is that the answer key comes from the corpus, never from the
model and never from memory. Doing that by hand across 31 questions is the slowest
hour of Day 1, so this does the lookup and leaves the judgement.

    python3 -m evals.trace                 # report only
    python3 -m evals.trace --write         # fill the unambiguous ones in golden.json
    python3 -m evals.trace --only C1,F2    # one or two items

An item is filled automatically only when a retrieved chunk's page title matches an
expected family. Everything else is printed for you to decide, including the items
where the corpus appears not to support the expected answer at all, which means the
expected answer is wrong, not the corpus.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from saal import config, store
from saal.answer.facets import decompose
from saal.retrieve.expand import get_expander
from saal.retrieve.search import search
from saal.testing import fixture_conn

ELIGIBILITY = re.compile(r"who can get|eligib|you must|qualif", re.I)

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden.json"


def trace_item(conn, item: dict, expander, top_k: int) -> dict:
    question = item["question"]
    facets = decompose(question)
    expansions = expander.expand(question) if expander else []
    hits = search(conn, question, facets=facets, expansions=expansions, top_k=top_k)

    def usefulness(hit) -> tuple[int, float]:
        """An eligibility section beats a lead paragraph as an answer key anchor.

        The claims in the golden suite are eligibility claims, so the chunk that
        should be cited is the one holding the rules, not the page introduction
        that happened to rank first.
        """
        eligibility = bool(ELIGIBILITY.search(hit.chunk.heading_path))
        return (1 if eligibility else 0, hit.confidence)

    matches: dict[str, list[dict]] = {}
    for family in item["expect"]:
        found = [h for h in hits if family.lower() in h.chunk.title.lower()
                 or h.chunk.title.lower() in family.lower()]
        found.sort(key=usefulness, reverse=True)
        matches[family] = [
            {"chunk_id": h.chunk.chunk_id, "title": h.chunk.title,
             "heading_path": h.chunk.heading_path, "url": h.chunk.url,
             "page_last_updated": h.chunk.page_last_updated,
             "confidence": round(h.confidence, 3)}
            for h in found
        ]
    return {"item": item, "facets": facets, "expansions": expansions,
            "hits": hits, "matches": matches}


def report(trace: dict) -> tuple[str, list[str]]:
    """Returns a status and the chunk ids that can be filled in without a judgement."""
    item = trace["item"]
    missing = [f for f, ms in trace["matches"].items() if not ms]
    if not trace["matches"]:
        return "no expectation", []
    if missing:
        return ("nothing found" if len(missing) == len(trace["matches"])
                else "partly found"), []
    # One chunk per expected family, the most useful one.
    return "traced", [ms[0]["chunk_id"] for ms in trace["matches"].values()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", choices=["fixture", "real"], default="real")
    ap.add_argument("--only", default="")
    ap.add_argument("--top-k", type=int, default=12)
    ap.add_argument("--write", action="store_true",
                    help="write the traced chunk ids back into golden.json")
    args = ap.parse_args(argv)

    doc = json.loads(GOLDEN.read_text())
    items = [i for i in doc["items"] if i["type"] == "answer"]
    if args.only:
        wanted = {i.strip().upper() for i in args.only.split(",")}
        items = [i for i in items if i["id"].upper() in wanted]

    if args.corpus == "fixture":
        conn = fixture_conn()
        items = [i for i in items if i.get("fixture")]
    else:
        conn = store.open_conn()
    counts = store.counts(conn)
    if not counts["chunks"]:
        print("corpus is empty: run `make crawl` then `make index`", file=sys.stderr)
        return 2

    expander = get_expander() if config.EXPANDER not in ("none", "") else None
    print(f"corpus: {counts['chunks']} chunks from {counts['pages']} pages, "
          f"expander {getattr(expander, 'name', 'none')}\n")

    filled, needs_eyes = 0, []
    for item in items:
        trace = trace_item(conn, item, expander, args.top_k)
        status, chunk_ids = report(trace)
        print(f"{item['id']:>3}  {status:<14} {item['question'][:58]}")
        for family, ms in trace["matches"].items():
            if ms:
                best = ms[0]
                print(f"       + {family}")
                print(f"         {best['chunk_id']}  {best['heading_path'][:62]}")
                print(f"         updated {best['page_last_updated']}  "
                      f"confidence {best['confidence']}")
            else:
                print(f"       ! {family}: not in the retrieved chunks")
        if status != "traced":
            needs_eyes.append(item["id"])
            print("         top retrieved instead: "
                  + ", ".join(sorted({h.chunk.title for h in trace["hits"]}))[:90])
        if args.write and chunk_ids:
            item["chunk_ids"] = chunk_ids
            filled += 1
        print()

    if args.write:
        GOLDEN.write_text(json.dumps(doc, indent=2))
        print(f"wrote chunk ids for {filled} items into {GOLDEN.relative_to(ROOT)}")

    if needs_eyes:
        noun = "item needs" if len(needs_eyes) == 1 else "items need"
        print(f"\n{len(needs_eyes)} {noun} your judgement: {', '.join(needs_eyes)}")
        print("For each one, either the expected family is wrong, the corpus scope is "
              "too narrow, or retrieval is failing. Decide which, and record it in "
              "docs/decisions.md.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
