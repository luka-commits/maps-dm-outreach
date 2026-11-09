"""Postcode grids: the search cells of a country and their language."""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REGIONS = HERE / "regions"
COUNTRIES = ("US", "GB", "CA", "AU", "IE", "DE")   # shipped with the kit; build_grid.py adds more
BUILD_HINT = "python3 pipeline/scrape/build_grid.py {cc}"
# Above this many cells a whole-country run needs --region or an explicit --whole-country.
LARGE_COUNTRY_CELLS = 5000
SECONDS_PER_CELL = 115       # measured average for one Maps search incl. container start
COST_PER_CELL = 0.004        # USD, rough Modal estimate: 2 CPU, 4 GB, ~2 min
CONCURRENCY = 12


def grid_path(country: str) -> pathlib.Path:
    return REGIONS / f"{country.upper()}_postcodes.json"


def countries() -> list[str]:
    """Every country with a grid: the shipped six plus any built with build_grid.py."""
    return sorted(p.name.split("_")[0] for p in REGIONS.glob("*_postcodes.json"))


def load_grid(country: str) -> list[dict]:
    path = grid_path(country)
    if not path.is_file():
        raise SystemExit(f"No postcode grid for {country.upper()} yet. Build it (free, a few seconds): "
                         f"{BUILD_HINT.format(cc=country.upper())}")
    return json.loads(path.read_text(encoding="utf-8"))["liste"]


def info(country: str) -> dict:
    """regions/<CC>.json: country name, Google language, and for built countries box and postcode shape."""
    path = REGIONS / f"{country.upper()}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def language(country: str) -> str:
    """Google result language for a country (regions/<CC>.json), English by default."""
    return info(country).get("language") or "en"


def select_cells(country: str, region: str | None = None, limit: int = 0) -> list[dict]:
    """All cells of a country, or the ones of a region. `region` matches the county/state
    (`region`) or the larger part (`land_region`, e.g. England, Wales, Texas), case-insensitive."""
    cells = load_grid(country)
    if region:
        wanted = region.strip().lower()
        cells = [c for c in cells
                 if wanted in ((c.get("region") or "").lower(), (c.get("land_region") or "").lower())]
        if not cells:
            raise SystemExit(f"No cell has the region {region!r} in {country}. "
                             f"Try one of: {', '.join(sample_regions(country))}")
    return cells[:limit] if limit else cells


def sample_regions(country: str, n: int = 8) -> list[str]:
    names = sorted({c.get("region") or "" for c in load_grid(country)} - {""})
    return names[:n] + (["..."] if len(names) > n else [])


def check_scope(country: str, region: str | None, cells: int, whole_country: bool) -> int:
    """The guard against an accidental 41,000-cell run. Returns the number of cells planned."""
    total = len(load_grid(country))
    if not region and not cells and total > LARGE_COUNTRY_CELLS and not whole_country:
        raise SystemExit(
            f"{country} has {total:,} cells (about ${total * COST_PER_CELL:,.0f} and "
            f"{total * SECONDS_PER_CELL / CONCURRENCY / 3600:.0f} hours). Run one region at a time "
            f"(--region Texas) or pass --whole-country to really mean it.")
    return len(select_cells(country, region, cells))


def run_name(country: str, slug: str, region: str | None = None, search: str | None = None) -> str:
    """<CC>-<niche-slug>[--<search-slug>][-<region-slug>], e.g. GB-roofer-west-yorkshire.

    A different search phrase is a different search, so it gets its own name and its own cells."""
    from pipeline.scrape.niches import slugify
    name = f"{country.upper()}-{slug}"
    if search:
        name += "--" + slugify(search)
    if region:
        name += "-" + slugify(region)
    return name


VOLUME_NAME = "maps-dm-outreach"   # the Modal volume holding the cell files (same in modal_scrape.py)
