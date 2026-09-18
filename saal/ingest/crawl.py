"""Polite crawler for the public payment content, plus the Day 0 measurement.

`--measure` answers the only question Day 0 asks: is crawling permitted, at what
rate, how many pages are in scope, and how do they split by payment family. Run
that before writing anything else, and let the real number decide the scope.
What counts as in scope lives in `scope.py`.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .. import config, store
from .extract import extract
from .scope import families_of, in_scope

LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body


def robots() -> tuple[urllib.robotparser.RobotFileParser, float | None]:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{config.BASE}/robots.txt")
    rp.read()
    delay = rp.crawl_delay(config.USER_AGENT)
    return rp, delay


def sitemap_urls(sitemap: str | None = None, seen: set[str] | None = None) -> list[str]:
    """Follow a sitemap index one level down and return every page url it lists."""
    sitemap = sitemap or config.SITEMAP
    seen = seen if seen is not None else set()
    if sitemap in seen:
        return []
    seen.add(sitemap)
    try:
        body = _get(sitemap).decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"  sitemap unreachable: {sitemap} ({exc})", file=sys.stderr)
        return []
    locs = LOC.findall(body)
    is_index = "<sitemapindex" in body.lower()
    if not is_index:
        return locs
    out: list[str] = []
    for child in locs:
        out.extend(sitemap_urls(child, seen))
    return out


def measure() -> dict:
    """Day 0. Prints the numbers that decide the corpus scope."""
    rp, delay = robots()
    urls = sitemap_urls()
    scoped = [u for u in urls if in_scope(u)]
    blocked = [u for u in scoped if not rp.can_fetch(config.USER_AGENT, u)]
    allowed = bool(scoped) and not blocked
    families = Counter(f for u in scoped for f in families_of(u))
    effective = max(config.CRAWL_DELAY, delay or 0)
    print(f"crawl permitted for scoped urls  : {allowed} ({len(blocked)} disallowed)")
    print(f"declared crawl delay             : {delay if delay is not None else 'none declared'}")
    print(f"urls in sitemap                  : {len(urls)}")
    print(f"urls in scope                    : {len(scoped)}")
    print(f"estimated crawl time             : {len(scoped) * effective / 60:.0f} minutes")
    print("\npages per family (a page can serve more than one):")
    for name, n in families.most_common():
        print(f"  {n:6d}  {name}")
    out = config.DATA / "day0_urls.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(scoped), encoding="utf-8")
    print(f"\nscoped urls written to {out}")
    return {"allowed": allowed, "delay": delay, "total": len(urls),
            "scoped": len(scoped), "families": dict(families)}


def crawl(limit: int = 0, families: tuple[str, ...] = (), force: bool = False) -> int:
    rp, declared = robots()
    delay = max(config.CRAWL_DELAY, declared or 0)
    urls = [u for u in sitemap_urls() if in_scope(u)]
    if families:
        urls = [u for u in urls if set(families_of(u)) & set(families)]
    if limit:
        urls = urls[:limit]
    print(f"{len(urls)} urls, crawl delay {delay}s")

    config.RAW.mkdir(parents=True, exist_ok=True)
    fetched = 0
    with store.connect() as conn:
        known = {r["url"]: r["html_sha"] for r in conn.execute("SELECT url, html_sha FROM pages")}
        for i, url in enumerate(urls, 1):
            if not rp.can_fetch(config.USER_AGENT, url):
                print(f"  [{i}] disallowed by robots, skipped: {url}")
                continue
            try:
                body = _get(url)
            except Exception as exc:  # noqa: BLE001 one bad page must not end the crawl
                print(f"  [{i}] failed: {url} ({exc})", file=sys.stderr)
                store.upsert_page(conn, url=url, title=None, html_sha=None,
                                  fetched_at=_now(), page_last_updated=None, status=0)
                time.sleep(delay)
                continue
            sha = hashlib.sha1(body).hexdigest()
            if not force and known.get(url) == sha:
                print(f"  [{i}] unchanged: {url}")
                time.sleep(delay)
                continue
            html = body.decode("utf-8", "replace")
            (config.RAW / f"{hashlib.sha1(url.encode()).hexdigest()}.html").write_text(html, encoding="utf-8")
            page = extract(html, url)
            store.upsert_page(conn, url=url, title=page.title, html_sha=sha,
                              fetched_at=_now(), page_last_updated=page.page_last_updated,
                              status=200)
            fetched += 1
            print(f"  [{i}] {page.page_last_updated or 'no date':>10}  {page.title[:60]}")
            conn.commit()
            time.sleep(delay)
    print(f"\nfetched {fetched} pages. Next: make index")
    return fetched


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measure", action="store_true", help="Day 0: count and report only")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--families", default="", help="comma separated, e.g. caring,work")
    ap.add_argument("--force", action="store_true", help="refetch unchanged pages")
    args = ap.parse_args(argv)
    if args.measure:
        measure()
        return 0
    families = tuple(f for f in args.families.split(",") if f)
    crawl(limit=args.limit, families=families, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
