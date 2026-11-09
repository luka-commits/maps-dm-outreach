#!/usr/bin/env python3
"""run.py - one command from "niche + country" to a table of businesses with their social channels.

  python run.py --country GB --niche roofer --region "West Yorkshire"
  python run.py --country GB --niche roofer --region "West Yorkshire" --cells 20     # probe run
  python run.py --country US --niche "med spa" --region Texas
  python run.py --country DE --niche schluesseldienst --region Sachsen
  python run.py --country GB --niche roofer --region "West Yorkshire" --from enrich   # continue

Steps, each resumable:

  scrape    Google Maps, one search per postcode cell, on Modal (needs `modal setup`)
  fetch     download the cell files from the Modal volume to data/runs/<run>/
  collect   one raw.json, deduplicated by place id
  enrich    websites: Instagram, Facebook, owner's first name (plain HTTP)
  import    filters, neighbour town, region -> the SQLite database
  activity  optional, Apify: marks Instagram/Facebook accounts without recent posts

Run name: <CC>-<niche-slug>[--<search-slug>][-<region-slug>], e.g. GB-roofer-west-yorkshire.
Free keyword: any --niche works. --search changes the Google phrase only, --terms the words used
to recognise the niche in categories and names.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
SETUP_COMMAND = "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"


def ensure_environment() -> None:
    """Needs Python 3.10+ and the packages in requirements.txt. If they are missing and .venv
    exists, run again inside it; otherwise say exactly what to run."""
    if sys.version_info < (3, 10):
        raise SystemExit(f"Python 3.10 or newer is required (this is {sys.version.split()[0]}). "
                         f"Install a newer Python, then: {SETUP_COMMAND.replace('python3', 'python3.12')}")
    try:
        import httpx  # noqa: F401
        import modal  # noqa: F401
    except ImportError:
        if VENV_PYTHON.exists() and not os.environ.get("OUTREACH_REEXEC") \
                and pathlib.Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
            os.environ["OUTREACH_REEXEC"] = "1"
            os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])
        raise SystemExit("Python packages are missing. Run once:\n  " + SETUP_COMMAND
                         + "\nthen use:  .venv/bin/python run.py ...")


if __name__ == "__main__":
    ensure_environment()
    sys.path.insert(0, str(ROOT))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

STEPS = ["scrape", "fetch", "collect", "enrich", "import", "activity"]


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", required=True,
                    help="US, GB, CA, AU, IE, DE, or any country added with pipeline/scrape/build_grid.py")
    ap.add_argument("--niche", required=True, help="any keyword, e.g. roofer, or a preset such as locksmith")
    ap.add_argument("--region", help="county / state / part of the country, e.g. 'West Yorkshire', Texas")
    ap.add_argument("--cells", type=int, default=0, help="probe run: only the first N cells")
    ap.add_argument("--search", help="Google search phrase if it should differ from the keyword")
    ap.add_argument("--terms", help="comma-separated words that mark a business as in the niche")
    ap.add_argument("--from", dest="start", choices=STEPS, default=STEPS[0], metavar="STEP")
    ap.add_argument("--to", dest="stop", choices=STEPS, default=STEPS[-1], metavar="STEP")
    ap.add_argument("--no-activity", action="store_true", help="skip the Apify activity check")
    ap.add_argument("--whole-country", action="store_true",
                    help="allow a country with more than 5,000 cells without --region")
    ap.add_argument("--fresh", action="store_true",
                    help="scrape cells again even if already scraped, and ignore the website cache")
    a = ap.parse_args(argv)
    a.country = a.country.upper()
    if a.region is not None:
        a.region = a.region.strip()
        if not a.region:
            ap.error("--region must not be empty")
    return a


def plan_steps(start: str, stop: str, no_activity: bool = False) -> list[str]:
    i, j = STEPS.index(start), STEPS.index(stop)
    if i > j:
        raise SystemExit(f"--from {start} comes after --to {stop}")
    steps = STEPS[i:j + 1]
    return [s for s in steps if not (s == "activity" and no_activity)]


def validate(a: argparse.Namespace, steps: list[str]) -> dict:
    """Guards that must fail BEFORE anything is paid for. Returns the resolved niche spec."""
    from pipeline.scrape import grid, niches
    if a.country not in grid.countries():
        raise SystemExit(f"No postcode grid for {a.country} yet. Build it once (free, a few seconds): "
                         f"{grid.BUILD_HINT.format(cc=a.country)}\nCountries ready now: {', '.join(grid.countries())}")
    spec = niches.resolve(a.niche, a.search, a.terms)
    if "scrape" in steps:
        grid.check_scope(a.country, a.region, a.cells, a.whole_country)
    else:
        grid.load_grid(a.country)
    return spec


def run_name(a: argparse.Namespace, spec: dict) -> str:
    from pipeline.scrape import grid
    return grid.run_name(a.country, spec["slug"], a.region, spec["search"] if spec["search_overridden"] else None)


def resume_command(a: argparse.Namespace, step: str) -> str:
    parts = ["python", "run.py", "--country", a.country, "--niche", a.niche]
    for flag, value in (("--region", a.region), ("--search", a.search), ("--terms", a.terms)):
        if value:
            parts += [flag, value]
    if a.cells:
        parts += ["--cells", str(a.cells)]
    parts += ["--from", step]
    return shlex.join(parts)


def find_modal() -> str:
    beside = pathlib.Path(sys.executable).parent / "modal"
    found = str(beside) if beside.exists() else shutil.which("modal")
    if not found:
        raise SystemExit("The modal CLI is not installed. Run: " + SETUP_COMMAND)
    return found


def normalize_fetch(downloaded: pathlib.Path, dest: pathlib.Path) -> int:
    """`modal volume get` may or may not nest the downloaded folder under its own name. Wherever the
    cell files landed, move them flat into the run folder. Returns the number of files."""
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for path in sorted(downloaded.rglob("*.json")):
        target = dest / path.name
        if path.resolve() != target.resolve():
            shutil.move(str(path), str(target))
        moved += 1
    return moved


def step_scrape(a, spec, name, folder) -> None:
    cmd = [find_modal(), "run", str(ROOT / "pipeline" / "scrape" / "modal_scrape.py"),
           "--country", a.country, "--niche", a.niche, "--run", name]
    if a.region:
        cmd += ["--region", a.region]
    if a.cells:
        cmd += ["--cells", str(a.cells)]
    if spec["search_overridden"]:
        cmd += ["--search", spec["search"]]
    if a.fresh:
        cmd += ["--fresh"]
    if a.whole_country:
        cmd += ["--whole-country"]
    env = {**os.environ, "OUTREACH_RUN_ID": name}
    print(" ".join(shlex.quote(c) for c in cmd), flush=True)
    code = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    if code != 0:
        raise RuntimeError(f"modal run exited with code {code}. If Modal asked you to log in: "
                           f"{pathlib.Path(find_modal()).name} setup")


def step_fetch(a, spec, name, folder) -> None:
    from pipeline.scrape.grid import VOLUME_NAME
    staging = folder.parent / f".fetch-{name}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    cmd = [find_modal(), "volume", "get", "--force", VOLUME_NAME, name, str(staging)]
    print(" ".join(shlex.quote(c) for c in cmd), flush=True)
    code = subprocess.run(cmd, cwd=ROOT).returncode
    if code != 0:
        raise RuntimeError(f"modal volume get exited with code {code}")
    count = normalize_fetch(staging, folder)
    shutil.rmtree(staging, ignore_errors=True)
    if not count:
        raise RuntimeError(f"No cell files for {name} in the Modal volume. Did the scrape step finish?")
    print(f"  {count} files in {folder}")


def step_collect(a, spec, name, folder) -> dict:
    from pipeline import _paths
    from pipeline.scrape import collect
    rows, report = collect.collect(folder, a.country)
    _paths.atomic_json(folder / "raw.json", rows)
    _paths.atomic_json(folder / "collect.json", report)
    print(f"  {report['cells']} cells, {report['hits']} hits, {report['unique']} unique businesses, "
          f"{report['with_website']} with a website")
    return report


def step_enrich(a, spec, name, folder) -> dict:
    from pipeline.enrich import enrich
    return enrich.enrich_run(folder, a.country, spec, fresh=a.fresh)


def step_import(a, spec, name, folder) -> dict:
    from pipeline import import_leads
    summary = import_leads.import_file(folder / "enriched_raw.json", a.country, run=name)
    print("  " + " | ".join(f"{k}: {v}" for k, v in summary.items()))
    return summary


def step_activity(a, spec, name, folder) -> dict:
    from pipeline import _paths
    from pipeline.social import activity
    if not _paths.load_config().get("activity_check", {}).get("enabled", True):
        print("  activity_check.enabled is false in outreach.config.json: skipped.")
        return {}
    return activity.check(write=True)


def update_registry(name: str, a, spec: dict, funnel: dict) -> None:
    """data/runs.json: what was actually scraped, per run (the database only knows cells with hits)."""
    from pipeline import _paths
    path = _paths.DATA / "runs.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"runs": []}
    entry = {"run": name, "country": a.country, "niche": spec["slug"], "keyword": spec["keyword"],
             "search": spec["search"], "region": a.region or None,
             "cells": funnel.get("cells", 0), "hits": funnel.get("hits", 0),
             "businesses": funnel.get("unique", 0), "imported": funnel.get("imported"),
             "date": dt.date.today().isoformat()}
    data["runs"] = [r for r in data.get("runs", []) if r.get("run") != name] + [entry]
    data["runs"].sort(key=lambda r: r["run"])
    _paths.atomic_json(path, data)


def print_funnel(name: str, funnel: dict, port) -> None:
    print(f"\n== Funnel {name} ==")
    rows = [("cells searched", funnel.get("cells")), ("hits", funnel.get("hits")),
            ("unique businesses", funnel.get("unique")), ("with website", funnel.get("with_website")),
            ("imported as leads", funnel.get("imported")),
            ("  with Instagram", funnel.get("with_instagram")),
            ("  with Facebook", funnel.get("with_facebook")),
            ("  with at least one DM channel", funnel.get("with_dm_channel")),
            ("disqualified as inactive", funnel.get("inactive"))]
    for label, value in rows:
        if value is not None:
            print(f"  {value:>7}  {label}")
    print(f"\nOpen the app: cd app && npm run dev  ->  http://localhost:{port}")


def main(argv=None) -> int:
    a = parse_args(argv)
    steps = plan_steps(a.start, a.stop, a.no_activity)
    spec = validate(a, steps)
    from pipeline import _paths
    name = run_name(a, spec)
    folder = _paths.DATA / "runs" / name
    folder.mkdir(parents=True, exist_ok=True)
    _paths.atomic_json(folder / "niche.json", {**spec, "country": a.country, "region": a.region, "run": name})
    funnel_file = folder / "funnel.json"
    funnel = json.loads(funnel_file.read_text(encoding="utf-8")) if funnel_file.is_file() else {}
    print(f"{name}: {' -> '.join(steps)}")
    print(f"  search phrase: {spec['search']!r}   niche terms: {', '.join(spec['terms'])}")

    handlers = {"scrape": step_scrape, "fetch": step_fetch, "collect": step_collect,
                "enrich": step_enrich, "import": step_import, "activity": step_activity}
    for step in steps:
        print(f"\n== {step} ==", flush=True)
        started = time.monotonic()
        try:
            result = handlers[step](a, spec, name, folder)
        except KeyboardInterrupt:
            print(f"\nInterrupted during {step}. Continue with: {resume_command(a, step)}")
            return 130
        except SystemExit as error:
            if error.code in (0, None):
                continue
            print(f"\nStep '{step}' failed: {error.code}\nContinue with: {resume_command(a, step)}")
            return 1
        except Exception as error:  # noqa: BLE001 - one place that names the way back
            print(f"\nStep '{step}' failed: {error}\nContinue with: {resume_command(a, step)}")
            return 1
        print(f"  ({time.monotonic() - started:.0f} s)")
        if step == "collect":
            funnel.update({k: result[k] for k in ("cells", "hits", "unique", "with_website")})
            update_registry(name, a, spec, funnel)
        elif step == "import":
            funnel.update({"imported": result["imported"],
                           "with_instagram": result["with_instagram"], "with_facebook": result["with_facebook"],
                           "with_dm_channel": result["with_dm_channel"]})
            update_registry(name, a, spec, funnel)
        elif step == "activity" and result:
            funnel["inactive"] = len(result.get("disqualified", []))
        _paths.atomic_json(funnel_file, funnel)

    print_funnel(name, funnel, _paths.load_config().get("app_port", 4319))
    return 0


if __name__ == "__main__":
    sys.exit(main())
