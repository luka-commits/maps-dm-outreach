#!/usr/bin/env python3
"""collect.py - the cell files of one run become ONE raw.json in the pipeline's row shape.

  python pipeline/scrape/collect.py data/runs/GB-roofer-west-yorkshire --country GB

1. Every cell file is read, every row mapped with `gosom_contract.to_apify_shape`.
2. Every row carries its cell: `_cell` (postcode), `_region` (county / state), `_country_part`
   (England, Texas), `_town` (town). The region comes from the CURRENT postcode grid, not from the
   cell file.
3. Deduplicated across cells by `gosom_contract.identity_key` (place id, else domain, else phone).
   Neighbouring cells see the same business; the first row is kept.
4. `raw.json` (the rows) and `collect.json` (the numbers) are written next to the cells.

A run folder without cell files is an error, not an empty result.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline._paths import atomic_json  # noqa: E402
from pipeline.scrape.gosom_contract import identity_key, to_apify_shape  # noqa: E402
from pipeline.scrape.grid import load_grid  # noqa: E402

NOT_CELLS = {"raw.json", "collect.json", "enriched_raw.json", "website_enrichment.json",
             "enrichment_measurement.json", "niche.json"}


def read_cells(folder: pathlib.Path) -> list[dict]:
    cells = []
    for path in sorted(folder.glob("*.json")):
        if path.name in NOT_CELLS:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  [warn] {path.name} is not JSON, skipped")
            continue
        if isinstance(data, dict) and "rows" in data and "code" in data:
            cells.append(data)
    return cells


def collect(folder: pathlib.Path, country: str, grid: list[dict] | None = None) -> tuple[list[dict], dict]:
    cells = read_cells(folder)
    if not cells:
        raise SystemExit(f"{folder}: no cell files. Fetch them first: run.py --from fetch")
    by_code = {z["code"]: z for z in (grid if grid is not None else load_grid(country))}
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()

    seen: set[str] = set()
    rows: list[dict] = []
    per_region_hits: collections.Counter = collections.Counter()
    per_region_unique: collections.Counter = collections.Counter()
    hits = blocked = empty = no_id = 0
    for cell in cells:
        code = cell["code"]
        known = by_code.get(code) or {}
        region = known.get("region") or cell.get("region")
        country_part = known.get("country_part") or cell.get("region")
        town = known.get("town") or cell.get("town")
        raw_rows = cell.get("rows") or []
        hits += len(raw_rows)
        blocked += bool(cell.get("blocked"))
        empty += not raw_rows
        per_region_hits[region] += len(raw_rows)
        for raw in raw_rows:
            row = to_apify_shape(raw, fetched_at, query=cell.get("query"))
            key = identity_key(row)
            if key is None:
                no_id += 1
                continue
            if key in seen:
                continue
            seen.add(key)
            row.update({"_cell": code, "_region": region, "_country_part": country_part, "_town": town})
            rows.append(row)
            per_region_unique[region] += 1

    report = {
        "run": folder.name, "country": country, "collected_at": fetched_at,
        "cells": len(cells), "cells_empty": empty, "cells_blocked": blocked,
        "hits": hits, "unique": len(rows), "without_identity": no_id,
        "with_website": sum(1 for r in rows if r.get("website")),
        "per_region": {str(r): {"hits": per_region_hits[r], "unique": per_region_unique[r]}
                       for r in sorted(per_region_hits, key=str)},
    }
    return rows, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=pathlib.Path)
    ap.add_argument("--country", required=True, help="US, GB, CA, AU, IE or DE")
    a = ap.parse_args(argv)
    rows, report = collect(a.folder, a.country.upper())
    atomic_json(a.folder / "raw.json", rows)
    atomic_json(a.folder / "collect.json", report)
    print(f"{report['run']}: {report['cells']} cells, {report['hits']} hits, {report['unique']} unique "
          f"businesses ({report['with_website']} with a website)")
    if report["cells_blocked"]:
        print(f"  {report['cells_blocked']} cells with a suspected block")
    if report["cells_empty"]:
        print(f"  {report['cells_empty']} cells without results")
    print(f"  -> {a.folder / 'raw.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
