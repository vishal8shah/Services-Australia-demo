"""The release gate.

Runs the golden suite, scores it with deterministic checks wherever a
deterministic check exists, and writes a dated scorecard that gets committed.
Failing runs get committed too: a suite that only records its wins proves nothing.

    python3 -m evals.run                 # offline, synthetic corpus, stub provider
    python3 -m evals.run --corpus real   # the crawled corpus in data/corpus.db
    python3 -m evals.run --judge anthropic --strict   # what CI should run
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from saal import config, pipeline, store
from saal.answer import contract
from saal.answer.providers import AnthropicProvider, ProviderError, get_provider
from saal.testing import fixture_conn

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden.json"
RUNS = ROOT / "evals" / "runs"


# ---------------------------------------------------------------- scoring ---

def name_matches(expected: str, produced: str) -> bool:
    """Substring either way, so "Youth Allowance" matches "Youth Allowance for students"."""
    e, p = expected.lower().strip(), produced.lower().strip()
    return e in p or p in e


def found_names(expected: list[str], payments: list[dict]) -> list[str]:
    produced = [p.get("name", "") for p in payments]
    return [e for e in expected if any(name_matches(e, p) for p in produced)]


def unsourced_claims(response: dict) -> int:
    n = 0
    for p in response.get("payments") or []:
        for sig in p.get("eligibility_signals") or []:
            if not [s for s in (sig.get("source_ids") or []) if s]:
                n += 1
    for a in response.get("next_actions") or []:
        if not [s for s in (a.get("source_ids") or []) if s]:
            n += 1
    return n


def score_item(item: dict, response: dict) -> dict:
    kind = item["type"]
    refusal = response.get("refusal")
    row = {
        "id": item["id"],
        "type": kind,
        "question": item["question"],
        "shape": item.get("shape"),
        "refused": bool(refusal),
        "refusal_class": (refusal or {}).get("class"),
        "confidence": response.get("confidence"),
        "elapsed_ms": (response.get("meta") or {}).get("elapsed_ms"),
        "payments": [p.get("name") for p in response.get("payments") or []],
        "unsourced": unsourced_claims(response),
        "validator_errors": (response.get("meta") or {}).get("validator_errors") or [],
    }

    if kind == "refusal":
        row["pass"] = bool(refusal) and refusal.get("class") in item["expect_class"]
        row["detail"] = f"expected {item['expect_class']}, got {row['refusal_class']}"
    elif kind == "control":
        row["pass"] = not refusal
        row["detail"] = "" if not refusal else f"over refused as {row['refusal_class']}"
    else:
        expected = item["expect"]
        hit = found_names(expected, response.get("payments") or [])
        row["expected"] = expected
        row["found"] = hit
        row["recall"] = len(hit) / len(expected) if expected else 0.0
        row["pass"] = row["recall"] == 1.0
        row["optional_found"] = found_names(item.get("optional") or [],
                                            response.get("payments") or [])
        row["detail"] = "" if row["pass"] else f"missing {[e for e in expected if e not in hit]}"
    return row


def aggregate(rows: list[dict], faithfulness: dict | None) -> dict:
    answers = [r for r in rows if r["type"] == "answer"]
    compounds = [r for r in answers if r["shape"] == "compound"]
    refusals = [r for r in rows if r["type"] == "refusal"]
    controls = [r for r in rows if r["type"] == "control"]
    latencies = [r["elapsed_ms"] / 1000 for r in rows if r.get("elapsed_ms")]

    fabricated = sum(
        1 for r in rows if any("rule 3" in e for e in r.get("validator_errors", []))
    )
    return {
        "payment_recall": _mean([r["recall"] for r in answers]),
        "compound_recall": _mean([1.0 if r["pass"] else 0.0 for r in compounds]),
        "citation_faithfulness": (faithfulness or {}).get("rate"),
        "fabricated_payment_rate": fabricated / len(rows) if rows else 0.0,
        "refusal_precision": _mean([1.0 if r["pass"] else 0.0 for r in refusals]),
        "over_refusal_rate": _mean([0.0 if r["pass"] else 1.0 for r in controls]),
        "unsourced_claims": sum(r["unsourced"] for r in rows),
        "latency_p50_s": round(statistics.median(latencies), 3) if latencies else None,
        "answered": sum(1 for r in answers if not r["refused"]),
        "counts": {"answer": len(answers), "compound": len(compounds),
                   "refusal": len(refusals), "control": len(controls)},
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


GATE_DIRECTION = {  # metric: True when higher is better
    "payment_recall": True, "compound_recall": True, "citation_faithfulness": True,
    "fabricated_payment_rate": False, "refusal_precision": True,
    "over_refusal_rate": False, "latency_p50_s": False,
}


def check_gates(metrics: dict, gates: dict) -> list[dict]:
    out = []
    for metric, threshold in gates.items():
        value = metrics.get(metric)
        if value is None:
            out.append({"metric": metric, "value": None, "gate": threshold,
                        "status": "not scored"})
            continue
        higher_better = GATE_DIRECTION.get(metric, True)
        ok = value >= threshold if higher_better else value <= threshold
        out.append({"metric": metric, "value": value, "gate": threshold,
                    "status": "pass" if ok else "FAIL"})
    return out


# ----------------------------------------------------------------- judging ---

JUDGE_SYSTEM = (
    "You check one claim against one source chunk. Answer with a single word, yes or no. "
    "yes means the chunk states or directly supports the claim. no means it does not, "
    "including when the claim is merely plausible or is about a different payment."
)


def judge_faithfulness(conn, rows_responses: list[tuple[dict, dict]], model: str) -> dict:
    """One rubric question per claim: does this chunk support this claim.

    A model is used here and nowhere else in the scorer, because this is the one
    question no regular expression can answer. Everything else is deterministic
    on purpose: a suite that leans on a model to decide whether it passed is a
    suite with a model sized hole in it.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY is not set, cannot judge")
    import urllib.request

    checked = supported = 0
    failures: list[str] = []
    for item, response in rows_responses:
        if response.get("refusal"):
            continue
        claims = list(iter_claims(response))
        wanted = sorted({cid for _, ids in claims for cid in ids})
        chunks = store.get_chunks(conn, wanted)
        for claim, ids in claims:
            for cid in ids:
                chunk = chunks.get(cid)
                if not chunk or not claim.strip():
                    continue
                checked += 1
                body = {
                    "model": model, "max_tokens": 5, "temperature": 0,
                    "system": JUDGE_SYSTEM,
                    "messages": [{"role": "user", "content":
                                  f"CHUNK\n{chunk.heading_path}\n{chunk.text}"
                                  f"\n\nCLAIM\n{claim}"}],
                }
                req = urllib.request.Request(
                    f"{config.ANTHROPIC_BASE.rstrip('/')}/v1/messages",
                    data=json.dumps(body).encode(),
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.load(resp)
                verdict = "".join(b.get("text", "") for b in payload.get("content", []))
                if verdict.strip().lower().startswith("yes"):
                    supported += 1
                else:
                    failures.append(f"{item['id']}: {claim[:80]} [{cid}]")
    return {"rate": round(supported / checked, 4) if checked else None,
            "checked": checked, "failures": failures}


def iter_claims(response: dict):
    for p in response.get("payments") or []:
        if p.get("one_liner"):
            yield f"{p.get('name')}: {p['one_liner']}", p.get("source_ids") or []
        for sig in p.get("eligibility_signals") or []:
            yield f"{p.get('name')}: {sig.get('text')}", sig.get("source_ids") or []
    for a in response.get("next_actions") or []:
        yield a.get("text", ""), a.get("source_ids") or []


# -------------------------------------------------------------- scorecard ---

def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001 a scorecard without a commit is still a scorecard
        return "unknown"


def write_scorecard(meta: dict, metrics: dict, gate_rows: list[dict],
                    rows: list[dict], faithfulness: dict | None) -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    path = RUNS / f"{stamp}.md"

    failed = [g for g in gate_rows if g["status"] == "FAIL"]
    headline = "PASS" if not failed else f"FAIL on {len(failed)} gate(s)"

    lines = [
        f"# Eval scorecard {stamp}",
        "",
        f"**Result: {headline}**",
        "",
        "| | |",
        "|---|---|",
        f"| corpus | {meta['corpus']} ({meta['chunks']} chunks, {meta['pages']} pages) |",
        f"| answer provider | `{meta['provider']}` |",
        f"| embedding provider | `{meta['embedder']}` |",
        f"| score floor | {meta['score_floor']} |",
        f"| judge | {meta['judge']} |",
        f"| items run | {meta['items']} of {meta['items_total']} |",
        f"| commit | `{meta['commit']}` |",
        "",
        "## Gates",
        "",
        "| metric | value | gate | status |",
        "|---|---|---|---|",
    ]
    for g in gate_rows:
        value = "not scored" if g["value"] is None else f"{g['value']}"
        lines.append(f"| {g['metric']} | {value} | {g['gate']} | {g['status']} |")

    lines += ["", "## Items", "",
              "| id | type | result | confidence | found | note |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        mark = "pass" if r["pass"] else "FAIL"
        found = ", ".join(r.get("payments") or []) or ("refused: " + str(r["refusal_class"])
                                                       if r["refused"] else "")
        note = r.get("detail") or ""
        lines.append(f"| {r['id']} | {r['type']} | {mark} | {r['confidence']} | "
                     f"{found[:60]} | {note[:70]} |")

    if faithfulness and faithfulness.get("failures"):
        lines += ["", "## Unsupported claims", ""]
        lines += [f"- {f}" for f in faithfulness["failures"][:25]]

    lines += ["", "## Notes", "", meta.get("note", "")]
    path.write_text("\n".join(lines) + "\n")
    path.with_suffix(".json").write_text(json.dumps(
        {"meta": meta, "metrics": metrics, "gates": gate_rows, "items": rows}, indent=2))
    return path


# ------------------------------------------------------------------- main ---

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", choices=["fixture", "real"], default="fixture")
    ap.add_argument("--provider", default=None, help="stub, fixture or anthropic")
    ap.add_argument("--judge", choices=["none", "anthropic"], default="none")
    ap.add_argument("--only", default="", help="comma separated item ids")
    ap.add_argument("--strict", action="store_true", help="exit non zero when a gate fails")
    args = ap.parse_args(argv)

    doc = json.loads(GOLDEN.read_text())
    items = doc["items"]
    if args.only:
        wanted = {i.strip().upper() for i in args.only.split(",")}
        items = [i for i in items if i["id"].upper() in wanted]

    if args.corpus == "fixture":
        conn = fixture_conn()
        items = [i for i in items if i.get("fixture")]
        note = ("Synthetic fixture corpus and the stub provider: these numbers measure the "
                "harness, not the product. The `hashing` embedder cannot match a situation "
                "sentence to a page that shares no words with it, which is why the compound "
                "items refuse. Rerun with `--corpus real` and a real embedder for a number "
                "worth quoting.")
    else:
        conn = store.open_conn()
        note = "Crawled corpus."

    provider = get_provider(args.provider) if args.provider else get_provider()
    counts = store.counts(conn)
    if not counts["chunks"]:
        print("corpus is empty: run `make crawl` then `make index`", file=sys.stderr)
        return 2

    rows, responses = [], []
    started = time.perf_counter()
    for item in items:
        response = pipeline.answer(item["question"], conn=conn, provider=provider)
        rows.append(score_item(item, response))
        responses.append((item, response))
        mark = "pass" if rows[-1]["pass"] else "FAIL"
        print(f"  {mark:4} {item['id']:>3}  {item['question'][:62]}")

    faithfulness = None
    if args.judge == "anthropic":
        try:
            faithfulness = judge_faithfulness(conn, responses, config.JUDGE_MODEL)
        except Exception as exc:  # noqa: BLE001 a missing judge must not lose the run
            print(f"judge unavailable, faithfulness not scored: {exc}", file=sys.stderr)

    metrics = aggregate(rows, faithfulness)
    gate_rows = check_gates(metrics, doc["gates"])
    meta = {
        "corpus": args.corpus, "pages": counts["pages"], "chunks": counts["chunks"],
        "provider": getattr(provider, "name", "?"), "embedder": config.EMBED_PROVIDER,
        "score_floor": config.SCORE_FLOOR, "judge": args.judge,
        "items": len(items), "items_total": len(doc["items"]), "commit": git_commit(),
        "wall_seconds": round(time.perf_counter() - started, 2), "note": note,
    }
    path = write_scorecard(meta, metrics, gate_rows, rows, faithfulness)

    print()
    for g in gate_rows:
        value = "not scored" if g["value"] is None else g["value"]
        print(f"  {g['status']:>9}  {g['metric']:<24} {value}  (gate {g['gate']})")
    print(f"\nscorecard: {path.relative_to(ROOT)}")

    conn.close()
    failed = [g for g in gate_rows if g["status"] == "FAIL"]
    return 1 if (failed and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
