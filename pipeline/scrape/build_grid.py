"""build_grid.py - add a country: builds its postcode grid from GeoNames, free, in a few seconds.

  python3 pipeline/scrape/build_grid.py FR
  python3 pipeline/scrape/build_grid.py NL --prefix 4        # group longer codes by their first 4 characters
  python3 pipeline/scrape/build_grid.py CH --language fr     # Google results in French instead of German

Writes `regions/<CC>_postcodes.json` (the search cells) and `regions/<CC>.json` (country name, Google
language, a bounding box for the country filter, the postcode shape for addresses). After that,
`run.py --country <CC>` works like for the six shipped countries.

## Cells

One cell per postcode. A postcode with a space ("SW1A 1AA") becomes its part before the space, so a
cell is a district and not a single street. `--prefix N` groups by the first N characters instead,
for countries whose codes are so fine that a search per code would mostly return the same businesses.
The script prints the number of cells and the rough cost of a whole-country run, so you see before
any paid run whether the grid is too fine.

## Regions

`region` is the second administrative level when GeoNames has one (county, département, provincia),
otherwise the first (state, region). `land_region` is always the first. `--region` in run.py matches
either, so both "Île-de-France" and "Paris" work for FR.

Source: GeoNames postal code data, https://download.geonames.org/export/zip/ (CC BY 4.0). Not every
country is in it; the script says so when one is missing.
"""
from __future__ import annotations

import argparse
import collections
import io
import itertools
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from pipeline.scrape import grid  # noqa: E402

ZIP_URL = "https://download.geonames.org/export/zip/{cc}.zip"
INFO_URL = "https://download.geonames.org/export/dump/countryInfo.txt"
USER_AGENT = "maps-dm-outreach grid builder"
BOX_MARGIN = 0.5           # degrees around the outermost postcode, the country filter is deliberately generous
SHAPE_COVERAGE = 0.97      # postcode shapes kept for the address pattern, the rare rest is noise
# Codes for big mail receivers, not places: France lists 14,000 "75021 CEDEX 01" next to its 6,000
# real postcodes, which would triple the cells of an FR run for no new businesses.
BULK_MAIL = re.compile(r"\b(?:CEDEX|CIDEX|BP)\b", re.IGNORECASE)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def country_info(cc: str) -> dict:
    """Name and main language from GeoNames' country list."""
    for line in fetch(INFO_URL).decode("utf-8").splitlines():
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) > 15 and cols[0] == cc:
            languages = [x for x in cols[15].split(",") if x]
            return {"country": cols[4], "language": languages[0].split("-")[0] if languages else "en"}
    raise SystemExit(f"{cc} is not an ISO country code GeoNames knows.")


def postcode_rows(cc: str) -> list[list[str]]:
    try:
        data = fetch(ZIP_URL.format(cc=cc))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(f"GeoNames has no postcode data for {cc}, so there is no grid to build. "
                             "List of covered countries: https://download.geonames.org/export/zip/")
        raise
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(f"{cc}.txt").decode("utf-8")
    return [line.split("\t") for line in text.splitlines() if line.strip()]


def cell_code(code: str, prefix: int) -> str:
    code = code.strip().upper()
    if prefix:
        return code.replace(" ", "")[:prefix]
    return code.split(" ")[0]


def shape(code: str) -> str:
    return re.sub(r"[A-Z]", "A", re.sub(r"\d", "9", code.strip().upper()))


def shape_pattern(shapes: collections.Counter) -> str | None:
    """A regex for the postcode shapes that cover most codes: "9999 AA" -> \\d{4}\\s?[A-Z]{2}."""
    total = sum(shapes.values())
    kept, covered = [], 0
    for s, n in shapes.most_common():
        if covered / total >= SHAPE_COVERAGE:
            break
        kept.append(s)
        covered += n
    parts = []
    for s in sorted(kept, key=len, reverse=True):          # longest first, so a short shape cannot cut one off
        regex = ""
        for char, run in ((c, len(list(g))) for c, g in itertools.groupby(s)):
            unit = {"9": r"\d", "A": "[A-Z]", " ": r"\s?"}.get(char, re.escape(char))
            regex += unit if run == 1 or unit == r"\s?" else f"{unit}{{{run}}}"
        parts.append(regex)
    return r"\b(?:" + "|".join(parts) + r")\b" if parts else None


def most_common(values: list[str]) -> str | None:
    values = [v for v in values if v]
    return collections.Counter(values).most_common(1)[0][0] if values else None


def build(cc: str, rows: list[list[str]], prefix: int = 0) -> tuple[list[dict], dict]:
    groups: dict[str, list[list[str]]] = collections.defaultdict(list)
    shapes: collections.Counter = collections.Counter()
    for r in rows:
        if len(r) < 11 or not r[1].strip():
            continue
        if BULK_MAIL.search(r[1]):
            continue
        try:
            float(r[9]), float(r[10])
        except ValueError:
            continue
        groups[cell_code(r[1], prefix)].append(r)
        shapes[shape(r[1])] += 1

    cells = []
    for code, members in sorted(groups.items()):
        lats = [float(m[9]) for m in members]
        lngs = [float(m[10]) for m in members]
        admin1 = most_common([m[3].strip() for m in members])
        admin2 = most_common([m[5].strip() for m in members])
        cells.append({
            "code": code,
            "ort": most_common([m[2].strip() for m in members]),
            "region": admin2 or admin1,
            "land_region": admin1 or admin2,
            "lat": round(sum(lats) / len(lats), 4),
            "lng": round(sum(lngs) / len(lngs), 4),
        })
    if not cells:
        raise SystemExit(f"The GeoNames file for {cc} has no usable postcodes.")
    lats = [c["lat"] for c in cells]
    lngs = [c["lng"] for c in cells]
    extra = {
        "box": [round(min(lats) - BOX_MARGIN, 2), round(max(lats) + BOX_MARGIN, 2),
                round(min(lngs) - BOX_MARGIN, 2), round(max(lngs) + BOX_MARGIN, 2)],
        "postcode_pattern": shape_pattern(shapes),
    }
    return cells, extra


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Add a country: build its postcode grid from GeoNames.")
    ap.add_argument("country", help="two-letter ISO code, e.g. FR, NL, ES, NZ")
    ap.add_argument("--prefix", type=int, default=0, help="one cell per first N characters of the postcode")
    ap.add_argument("--language", help="Google result language, default: the country's main language")
    ap.add_argument("--force", action="store_true", help="overwrite an existing grid")
    a = ap.parse_args(argv)
    cc = a.country.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", cc):
        ap.error("country must be a two-letter code such as FR")
    if grid.grid_path(cc).exists() and not a.force:
        raise SystemExit(f"{cc} already has a grid ({grid.grid_path(cc).name}). --force rebuilds it.")

    info = country_info(cc)
    rows = postcode_rows(cc)
    cells, extra = build(cc, rows, a.prefix)
    language = (a.language or info["language"]).lower()
    cell_kind = (f"first {a.prefix} characters of the postcode" if a.prefix
                 else "postcode (part before the space)" if any(" " in r[1].strip() for r in rows if len(r) > 1)
                 else "postcode")
    source = f"GeoNames postal codes, {ZIP_URL.format(cc=cc)} (CC BY 4.0)"
    grid.grid_path(cc).write_text(json.dumps(
        {"country": cc, "cell": cell_kind, "source": source, "liste": cells},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (grid.REGIONS / f"{cc}.json").write_text(json.dumps(
        {"country": info["country"], "language": language, **extra}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    regions = collections.Counter(c["land_region"] for c in cells)
    print(f"{cc} ({info['country']}): {len(cells):,} cells, Google language '{language}'")
    print(f"  whole country about ${len(cells) * grid.COST_PER_CELL:,.0f} and "
          f"{len(cells) * grid.SECONDS_PER_CELL / grid.CONCURRENCY / 3600:.1f} hours on Modal")
    print(f"  {len(regions)} regions, for --region: "
          + ", ".join(f"{name} ({n})" for name, n in regions.most_common(6))
          + (" ..." if len(regions) > 6 else ""))
    print("  example cells: " + ", ".join(f"{c['code']} {c['ort']}" for c in cells[:: max(1, len(cells) // 4)][:4]))
    if len(cells) > 20000 and not a.prefix:
        print(f"  That is a fine grid. If nearby cells look alike, rebuild with --prefix "
              f"{max(2, len(cells[0]['code']) - 1)} --force for fewer, larger cells.")
    print(f"\nNext: python3 run.py --country {cc} --niche \"<keyword in {language}>\" "
          f"--region \"{regions.most_common(1)[0][0]}\" --cells 20")


if __name__ == "__main__":
    main()
