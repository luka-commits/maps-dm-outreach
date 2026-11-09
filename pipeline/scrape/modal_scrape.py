"""modal_scrape.py - one country, one niche, one Google Maps search per postcode cell, on Modal.

  modal run pipeline/scrape/modal_scrape.py --country GB --niche roofer
  modal run pipeline/scrape/modal_scrape.py --country GB --niche roofer --region "West Yorkshire"
  modal run pipeline/scrape/modal_scrape.py --country GB --niche roofer --cells 20     # probe

Normally you do not call this directly: `python run.py` does, and then downloads the cells.

## Why postcode cells (measured)

A county-wide search finds about 11% of what the same area finds as postcode cells: one Google
search returns 55-60 results and cuts off, so a bigger area only changes which sixty you see.
Hence one search per cell ("roofer in Leeds LS1, GB").

## Why every cell is written immediately

Each cell writes its result into a Modal volume and a new run skips whatever is already there.
Aborting costs one cell, not the whole run. Modal retries a crashed container three times, and
exceptions come back as results instead of ending the run: at the end you get the list of cells
that did not come, and running the same command again fetches only those.

## Pace

Twelve cells at a time. For ~1,500 cells that is a few hours, which looks less like a bot than the
same volume in half an hour. Whether larger runs pass without blocks is untested; the cell files
carry a `blocked` flag when Google answered with a challenge page.

## One Modal app per run

Two `modal run` with the same app name stop each other (`function ... is stopped`). The volume
keeps one fixed name, it is the shared storage; only the app name is unique per run.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

import modal

HERE = pathlib.Path(__file__).resolve().parent
# Locally this file sits in <repo>/pipeline/scrape; inside the Modal container it is /root/modal_scrape.py
# and has no grandparent. Only the local entrypoint needs the repo root.
ROOT = HERE.parents[1] if len(HERE.parents) > 1 else HERE
APP_NAME = "maps-dm-outreach-" + re.sub(r"[^a-z0-9-]+", "-", (os.environ.get("OUTREACH_RUN_ID") or "adhoc").lower())
VOLUME_NAME = "maps-dm-outreach"
# Pinned by digest so a new upstream release cannot change the output format under you.
GOSOM_IMAGE = (
    "gosom/google-maps-scraper@"
    "sha256:b5cb22cfe7d91f81d66d090e72ac9b3806350ae74b74bcbf244e8a54edfa3495"
)
SCRAPER_TIMEOUT = 240
CONCURRENCY = 12
STORE = "/cells"

CHALLENGE = re.compile(
    r"\bcaptcha\b|\brecaptcha\b|unusual traffic|automated queries"
    r"|sorry/index|/sorry\?|http[ /]?429\b|status[ =:]+429\b|too many requests"
    r"|\b403 forbidden\b|access denied",
    re.IGNORECASE,
)

app = modal.App(APP_NAME)
image = modal.Image.from_registry(GOSOM_IMAGE, add_python="3.12").entrypoint([])
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    image=image,
    volumes={STORE: volume},
    timeout=600,
    retries=3,          # Modal retries a crashed container; in-cell retry code would not cover that
    cpu=2.0,
    memory=4096,
    max_containers=CONCURRENCY,
)
def scrape_cell(job: dict[str, Any]) -> dict[str, Any]:
    target = pathlib.Path(STORE) / job["run"] / f"{job['code']}.json"
    if target.exists():
        # Already there means skip: running the same command again resumes where it stopped.
        return {"code": job["code"], "status": "skipped", "hits": 0}
    if not job.get("fresh"):
        # Same country, niche, search phrase and postcode from another run (a county probe, then
        # the country run): once is enough. Cell files carry their `prefix` to tell them apart.
        for other in sorted(pathlib.Path(STORE).glob(f"*/{job['code']}.json")):
            if other.parent.name == job["run"]:
                continue
            try:
                if json.loads(other.read_text(encoding="utf-8")).get("prefix") == job["prefix"]:
                    return {"code": job["code"], "status": "elsewhere", "hits": 0,
                            "run": other.parent.name}
            except (OSError, json.JSONDecodeError):
                continue

    start = time.monotonic()
    query = job["query"]
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder)
        (path / "q.txt").write_text(query + "\n", encoding="utf-8")
        results = path / "r.json"
        proc = subprocess.run(
            ["/usr/bin/google-maps-scraper",
             "-input", str(path / "q.txt"), "-results", str(results),
             "-json", "-lang", job.get("language") or "en", "-depth", "5", "-c", "1",
             "-browser-pool-size", "1", "-pages-per-browser", "1",
             "-exit-on-inactivity", "45s"],
            capture_output=True, text=True, timeout=SCRAPER_TIMEOUT + 300)
        text = results.read_text(encoding="utf-8") if results.exists() else ""

    rows = []
    for piece in text.strip().splitlines():
        try:
            rows.append(json.loads(piece))
        except json.JSONDecodeError:
            pass

    log = (proc.stdout or "") + (proc.stderr or "")
    blocked = bool(CHALLENGE.search(log))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "code": job["code"], "query": query, "town": job.get("town"), "region": job.get("region"),
        "prefix": job["prefix"], "hits": len(rows), "seconds": round(time.monotonic() - start, 1),
        "blocked": blocked, "rows": rows,
    }, ensure_ascii=False), encoding="utf-8")
    volume.commit()
    # The ids go back so the report counts UNIQUE businesses: neighbouring cells see the same
    # business (a city run returned 1,730 hits for 878 businesses).
    return {"code": job["code"], "status": "scraped", "hits": len(rows), "blocked": blocked,
            "ids": [r.get("place_id") or r.get("cid") for r in rows]}


@app.local_entrypoint()
def main(country: str = "GB", niche: str = "", search: str = "", region: str = "",
         cells: int = 0, run: str = "", fresh: bool = False, whole_country: bool = False) -> None:
    sys.path.insert(0, str(ROOT))
    from pipeline.scrape import grid, niches

    country = country.upper()
    if not niche:
        raise SystemExit("--niche is required, any keyword works: --niche roofer")
    spec = niches.resolve(niche, search or None)
    grid.check_scope(country, region or None, cells, whole_country)
    selected = grid.select_cells(country, region or None, cells)
    name = run or grid.run_name(country, spec["slug"], region or None,
                                spec["search"] if spec["search_overridden"] else None)
    prefix = grid.run_name(country, spec["slug"], None, spec["search"] if spec["search_overridden"] else None)
    language = grid.language(country)
    jobs = [{
        "run": name, "prefix": prefix, "fresh": fresh, "language": language,
        "code": c["code"], "town": c.get("ort"), "region": c.get("region"),
        # The town name goes along: "roofer in Leeds LS1, GB" reads better to Google than "in LS1".
        "query": (f"{spec['search']} in {c['ort']} {c['code']}, {country}" if c.get("ort")
                  else f"{spec['search']} in {c['code']}, {country}"),
    } for c in selected]

    print(f"{name}: {len(jobs)} cells, {CONCURRENCY} at a time")
    print(f"  estimate ${len(jobs) * grid.COST_PER_CELL:.2f}, "
          f"{len(jobs) * grid.SECONDS_PER_CELL / CONCURRENCY / 3600:.1f} hours (rough, Modal bills by use)\n")

    # One broken cell does not end the run.
    scraped = skipped = elsewhere = failed = blocked = hits = 0
    unique: set[str] = set()
    other_runs: dict[str, int] = {}
    for result in scrape_cell.map(jobs, return_exceptions=True, wrap_returned_exceptions=False):
        if isinstance(result, Exception):
            failed += 1
        elif result["status"] == "skipped":
            skipped += 1
        elif result["status"] == "elsewhere":
            elsewhere += 1
            other_runs[result["run"]] = other_runs.get(result["run"], 0) + 1
        else:
            scraped += 1
            hits += result["hits"]
            blocked += bool(result.get("blocked"))
            unique.update(i for i in result.get("ids") or [] if i)

    print(f"\n  {scraped} cells scraped, {skipped} already in this run, {failed} failed")
    if elsewhere:
        print(f"  {elsewhere} cells already scraped in an earlier run, not fetched again: "
              + ", ".join(f"{k} ({n})" for k, n in other_runs.items()) + "  [--fresh scrapes them anyway]")
    print(f"  {hits} hits, {len(unique)} unique businesses (freshly scraped cells only), "
          f"{blocked} cells with a suspected block")
    print(f"\n  Results are in the Modal volume '{VOLUME_NAME}' under {name}/")
    if failed:
        print(f"  {failed} cells failed: run the same command again, finished cells are skipped.")
    if failed and not (scraped or skipped or elsewhere):
        # Nothing usable came back (for example a container that cannot start): stop the chain here
        # instead of letting the fetch step fail with a confusing "No such file or directory".
        raise SystemExit(f"All {failed} cells failed; see the errors above.")
