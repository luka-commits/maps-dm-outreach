#!/usr/bin/env python3
"""enrich.py - Instagram, Facebook and the owner's first name from each business's website.

  python pipeline/enrich/enrich.py data/runs/GB-roofer-west-yorkshire --country GB --niche roofer

Fetches the homepage plus up to four contact pages per website with plain HTTP (no browser, no
paid API), pulls Instagram and Facebook links out of the HTML, and writes
`enriched_raw.json` (all rows, enriched) and `enrichment_measurement.json` (the numbers) next to
`raw.json`. Websites are cached per domain in `website_enrichment.json` in the run folder, so
running it again costs nothing and an interrupted run picks up where it stopped.

## Who gets fetched

The same rule the import uses: `filter_niche.classify` with the niche terms; everything that is not
`drop` is fetched. Chains are skipped by domain (10+ rows on one own domain): a chain with 1,800
branches would otherwise cost 1,800 downloads of the same homepage, and it would be thrown away on
import anyway. Rows that are skipped stay in the file.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html as html_lib
import json
import pathlib
import re
import sys
import time
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Iterable

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline import _paths  # noqa: E402
from pipeline.enrich import owner as owner_names  # noqa: E402
from pipeline.enrich.domains import CHAIN_THRESHOLD, chain_domains, domain_of  # noqa: E402
from pipeline.enrich.filter_niche import classify  # noqa: E402
from pipeline.scrape import niches  # noqa: E402
from pipeline.scrape.gosom_contract import field_coverage  # noqa: E402
from pipeline.scrape.grid import load_grid  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; MapsDmOutreach/1.0; +local-business-research)"
CACHE_VERSION = 5
MAX_WEBSITE_PAGES = 5
COMMON_CONTACT_PATHS = ("/contact", "/kontakt", "/impressum", "/about")
CONTACT_PAGE_TERMS = (
    ("contact", "kontakt", "get-in-touch"),
    ("impressum", "imprint"),
    ("about", "about-us", "ueber-uns", "uber-uns"),
    ("team", "staff", "people"),
    ("legal", "privacy", "datenschutz"),
    ("booking", "book", "appointment", "reservation"),
)


class RunStats(dict):
    """Counters as a plain dict so they go straight into the measurement file."""

    def __missing__(self, key):
        return 0


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def decode_cloudflare_email(token: str) -> str | None:
    """Decode Cloudflare's public email-protection payload."""
    if len(token) < 4 or len(token) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", token):
        return None
    try:
        key = int(token[:2], 16)
        return "".join(chr(int(token[i:i + 2], 16) ^ key) for i in range(2, len(token), 2))
    except (ValueError, UnicodeError):
        return None


def contact_page_priority(url: str) -> tuple[int, str]:
    path = urllib.parse.urlparse(url).path.lower()
    for priority, terms in enumerate(CONTACT_PAGE_TERMS):
        if any(term in path for term in terms):
            return priority, url
    return len(CONTACT_PAGE_TERMS), url


def candidate_contact_pages(homepage_url: str, discovered: Iterable[str],
                            *, limit: int = MAX_WEBSITE_PAGES - 1) -> list[str]:
    """At most four useful pages after the homepage: discovered contact-like links first, then the
    usual paths."""
    base = urllib.parse.urlparse(homepage_url)
    base_host = base.netloc.lower().removeprefix("www.")
    candidates: set[str] = set()
    for value in discovered:
        absolute = urllib.parse.urljoin(homepage_url, value)
        parsed = urllib.parse.urlparse(absolute)
        host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme in {"http", "https"} and host == base_host:
            candidates.add(urllib.parse.urlunparse(parsed._replace(fragment="")))
    ordered = sorted(candidates, key=contact_page_priority)
    for path in COMMON_CONTACT_PATHS:
        fallback = urllib.parse.urlunparse(base._replace(path=path, params="", query="", fragment=""))
        if fallback not in ordered:
            ordered.append(fallback)
    return ordered[:limit]


def clean_contact_email(value: str) -> str | None:
    email = value.lower().strip().strip(".,;:()[]<>")
    if "@" not in email or email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return None
    local, domain = email.rsplit("@", 1)
    if not local or "." not in domain or "example." in domain:
        return None
    if domain in {"email.com", "mysite.com", "domain.com"}:
        return None
    if domain == "sentry.io" or domain.endswith((".sentry.io", ".wixpress.com")):
        return None
    if re.fullmatch(r"[a-f0-9]{24,}", local):
        return None
    if local.replace("-", "").replace("_", "") in {"noreply", "donotreply", "noresponse"}:
        return None
    return email


def order_contact_emails(values: Iterable[str], website_host: str) -> list[str]:
    """Own-domain and useful role inboxes first, without discarding the others."""
    role_order = {"info": 0, "hello": 1, "contact": 2, "office": 3, "bookings": 4, "booking": 5,
                  "sales": 6, "enquiries": 7, "owner": 8}
    cleaned = {e for v in values if isinstance(v, str) for e in [clean_contact_email(v)] if e}

    def rank(email: str) -> tuple[int, int, str]:
        local, domain = email.rsplit("@", 1)
        own = bool(website_host) and (domain == website_host or domain.endswith("." + website_host))
        return (0 if own else 1, role_order.get(local, 50), email)

    return sorted(cleaned, key=rank)


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def extract_contacts(html: str, page_url: str) -> dict[str, list[str]]:
    """emails, instagrams, facebooks (in page order) and contact-like `pages` from one page."""
    decoded = html_lib.unescape(html)
    parser = LinkParser()
    try:
        parser.feed(decoded)
    except Exception:  # noqa: BLE001 - broken markup must not stop a run
        pass
    emails = set(re.findall(r"(?i)(?<![\w.+-])([\w.+-]+@[\w.-]+\.[a-z]{2,})", decoded))
    for local, domain, suffix in re.findall(
        r"(?i)\b([a-z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\s+at\s+)\s*"
        r"([a-z0-9.-]+?)\s*(?:\[dot\]|\(dot\)|\s+dot\s+)\s*([a-z]{2,})\b", decoded):
        emails.add(f"{local}@{domain}.{suffix}")
    tokens = re.findall(r"(?i)(?:data-cfemail=[\"']|/cdn-cgi/l/email-protection#)([0-9a-f]{4,})", decoded)
    emails.update(filter(None, (decode_cloudflare_email(t) for t in tokens)))

    instagrams: list[str] = []
    facebooks: list[str] = []
    pages: set[str] = set()
    base_host = urllib.parse.urlparse(page_url).netloc.lower().removeprefix("www.")
    for href in parser.links:
        # One broken link must not kill a run: urljoin raises ValueError on e.g. brackets in the
        # host. That business loses this link, every other keeps theirs.
        try:
            absolute = urllib.parse.urljoin(page_url, href)
            parsed = urllib.parse.urlparse(absolute)
        except ValueError:
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        if absolute.lower().startswith("mailto:"):
            emails.add(absolute[7:].split("?", 1)[0])
        elif host.endswith("instagram.com"):
            instagrams.append(absolute.split("?", 1)[0])
        elif host.endswith(("facebook.com", "fb.com")):
            facebooks.append(absolute.split("?", 1)[0])
        elif host == base_host and any(w in parsed.path.lower() for g in CONTACT_PAGE_TERMS for w in g):
            pages.add(absolute.split("#", 1)[0])
    return {
        "emails": order_contact_emails(emails, base_host),
        "instagrams": _unique(instagrams),
        "facebooks": _unique(facebooks),
        "pages": sorted(pages),
    }


_NON_TEXT = re.compile(r"<(script|style|template|noscript)\b[^>]*>.*?</\1>", re.S | re.I)


def page_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _NON_TEXT.sub(" ", html)))


def website_domain(url: str | None) -> str | None:
    return domain_of({"website": url}) or None


def target_rows(rows: list[dict], terms, exclusions=()) -> list[dict]:
    """Rows worth a website download: in the niche (not `drop`), not a chain, with a website."""
    chains = chain_domains(rows)
    out = []
    for row in rows:
        if classify(row, list(terms), exclusions) == "drop":
            continue
        host = domain_of(row)
        if not host or host in chains:
            continue
        out.append(row)
    return out


async def enrich_websites(rows: list[dict[str, Any]], *, concurrency: int = 30,
                          cache_path: pathlib.Path | None = None, stats: RunStats | None = None,
                          client: httpx.AsyncClient | None = None,
                          towns: set[str] | None = None,
                          trade_terms: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
    """Fetch each unique website once and attach the evidence to every matching row."""
    cache: dict[str, dict[str, Any]] = {}
    if cache_path and cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            cache = {k: v for k, v in loaded.items() if v.get("version") == CACHE_VERSION}
        except json.JSONDecodeError:
            cache = {}
    site_by_domain: dict[str, str] = {}
    for row in rows:
        domain = website_domain(row.get("website"))
        if domain:
            site = row["website"] if "://" in row["website"] else "https://" + row["website"]
            site_by_domain.setdefault(domain, site)
    if stats is not None:
        stats["unique_websites"] = len(site_by_domain)
    pending = [(d, s) for d, s in site_by_domain.items() if d not in cache]
    sem = asyncio.Semaphore(concurrency)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=12, follow_redirects=True,
                                   headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    towns = towns or set()

    async def fetch(url: str) -> tuple[str | None, str | None, str | None]:
        try:
            if stats is not None:
                stats["website_requests"] += 1
            response = await client.get(url)
            if not response.is_success or "html" not in response.headers.get("content-type", ""):
                return None, None, f"HTTP {response.status_code}"
            return str(response.url), response.text[:2_000_000], None
        except Exception as exc:  # noqa: BLE001 - any network error means "no data from this site"
            return None, None, type(exc).__name__

    async def one(domain: str, site: str) -> tuple[str, dict[str, Any]]:
        async with sem:
            page_url, html, error = await fetch(site)
            if not html or not page_url:
                return domain, {"version": CACHE_VERSION, "status": "failed", "error": error,
                                "pages_fetched": 0}
            found = extract_contacts(html, page_url)
            fetched = [page_url]
            texts = [page_text(html)]
            homepage_emails = set(found["emails"])
            for candidate in candidate_contact_pages(page_url, found.pop("pages")):
                child_url, child_html, _ = await fetch(candidate)
                if not child_html or not child_url:
                    continue
                child = extract_contacts(child_html, child_url)
                fetched.append(child_url)
                texts.append(page_text(child_html))
                for key in ("emails", "instagrams", "facebooks"):
                    found[key] = _unique([*found[key], *child[key]])
            found["emails"] = order_contact_emails(found["emails"], domain)
            return domain, {
                "version": CACHE_VERSION, "status": "measured", "pages_fetched": len(fetched),
                "page_urls": fetched, "homepage_email_hit": bool(homepage_emails),
                "website_owner": owner_names.from_website_text(" ".join(texts), towns),
                **found,
            }

    try:
        batch = max(concurrency * 3, 30)
        for offset in range(0, len(pending), batch):
            done = await asyncio.gather(*(one(d, s) for d, s in pending[offset:offset + batch]))
            for domain, result in done:
                cache[domain] = result
            if cache_path:
                _paths.atomic_json(cache_path, cache)
    finally:
        if own_client:
            await client.aclose()

    if stats is not None:
        stats["website_errors"] = sum(v.get("status") == "failed" for v in cache.values()
                                      if v is not None)
        stats["website_pages_fetched"] = sum(v.get("pages_fetched", 0) for v in cache.values())

    for row in rows:
        domain = website_domain(row.get("website")) or ""
        result = cache.get(domain, {})
        row["emails"] = order_contact_emails([*(row.get("emails") or []), *(result.get("emails") or [])], domain)
        row["instagrams"] = _unique([*(row.get("instagrams") or []), *(result.get("instagrams") or [])])
        row["facebooks"] = _unique([*(row.get("facebooks") or []), *(result.get("facebooks") or [])])
        found = owner_names.find(business_name=row.get("title") or "", emails=row["emails"],
                                 website_name=result.get("website_owner"), towns=towns,
                                 town=row.get("_ort") or "", trade_terms=trade_terms or ())
        if found:
            row["ownerName"], row["ownerSource"] = found["first_name"], found["source"]
        row.setdefault("_source", {})["websiteEnrichment"] = {
            "status": result.get("status", "not_applicable"),
            "pagesFetched": result.get("pages_fetched", 0), "method": "http_only"}
    return cache


def enrich_run(folder: pathlib.Path, country: str, spec: dict, *, concurrency: int = 30,
               fresh: bool = False) -> dict:
    """The whole step for one run folder: raw.json -> enriched_raw.json + measurement."""
    raw = folder / "raw.json"
    if not raw.is_file():
        raise SystemExit(f"{raw} is missing. Run the collect step first: run.py --from collect")
    rows = json.loads(raw.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise SystemExit("raw.json must contain a JSON array of objects")
    if not 1 <= concurrency <= 100:
        raise SystemExit("concurrency must be between 1 and 100")
    cache_path = folder / "website_enrichment.json"
    if fresh and cache_path.exists():
        cache_path.unlink()
    towns = {str(z.get("ort") or "").lower() for z in load_grid(country)} - {""}
    stats = RunStats()
    started = time.monotonic()
    targets = target_rows(rows, spec["terms"], spec.get("exclusions", ()))
    chains = chain_domains(rows)
    print(f"{len(rows)} rows: {len(targets)} in the niche with a website and not a chain "
          f"-> fetching. {len(chains)} chain domains skipped.", flush=True)
    asyncio.run(enrich_websites(targets, concurrency=concurrency, cache_path=cache_path,
                                stats=stats, towns=towns, trade_terms=spec["terms"]))
    report = {
        "duration_seconds": round(time.monotonic() - started, 1),
        "niche": spec["slug"], "terms": list(spec["terms"]), "stats": dict(stats),
        "http_only": True, "target_rows": len(targets),
        "chain_domains_skipped": sorted(chains), "chain_threshold": CHAIN_THRESHOLD,
        "field_coverage": field_coverage(rows),
    }
    _paths.atomic_json(folder / "enriched_raw.json", rows)
    _paths.atomic_json(folder / "enrichment_measurement.json", report)
    s = report["stats"]
    print(f"  {s.get('unique_websites', 0)} websites, {s.get('website_errors', 0)} unreachable, "
          f"{report['duration_seconds']:.0f} s")
    print(f"  -> {folder / 'enriched_raw.json'}")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=pathlib.Path, help="run folder containing raw.json")
    ap.add_argument("--country", required=True)
    ap.add_argument("--niche", help="keyword or preset; default: read from niche.json in the run folder")
    ap.add_argument("--terms", help="comma-separated niche terms, overrides the derived ones")
    ap.add_argument("--concurrency", type=int, default=30)
    ap.add_argument("--fresh", action="store_true", help="ignore the website cache and fetch again")
    a = ap.parse_args(argv)
    spec_file = a.folder / "niche.json"
    if a.niche:
        spec = niches.resolve(a.niche, terms=a.terms)
    elif spec_file.is_file():
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    else:
        raise SystemExit("--niche is required (no niche.json in the run folder)")
    enrich_run(a.folder, a.country, spec, concurrency=a.concurrency, fresh=a.fresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
