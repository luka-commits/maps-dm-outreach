import json

import pytest

import run
from pipeline import _paths
from pipeline.scrape import grid, niches


def args(*argv):
    return run.parse_args(["--country", "GB", "--niche", "roofer", *argv])


def test_step_planning():
    assert run.plan_steps("scrape", "activity") == ["scrape", "fetch", "collect", "enrich", "import", "activity"]
    assert run.plan_steps("enrich", "import") == ["enrich", "import"]
    assert run.plan_steps("scrape", "activity", no_activity=True)[-1] == "import"
    with pytest.raises(SystemExit):
        run.plan_steps("import", "collect")


def test_arguments():
    a = args("--region", " West Yorkshire ", "--cells", "20", "--from", "collect")
    assert a.region == "West Yorkshire" and a.cells == 20 and a.start == "collect" and a.country == "GB"
    with pytest.raises(SystemExit):
        args("--region", "  ")
    with pytest.raises(SystemExit):
        run.parse_args(["--country", "GB", "--niche", "x", "--from", "nonsense"])


def test_large_country_guard():
    steps = run.plan_steps("scrape", "activity")
    with pytest.raises(SystemExit) as e:
        run.validate(run.parse_args(["--country", "US", "--niche", "roofer"]), steps)
    assert "--region" in str(e.value) and "--whole-country" in str(e.value)
    run.validate(run.parse_args(["--country", "US", "--niche", "roofer", "--region", "Texas"]), steps)
    run.validate(run.parse_args(["--country", "US", "--niche", "roofer", "--cells", "20"]), steps)
    run.validate(run.parse_args(["--country", "US", "--niche", "roofer", "--whole-country"]), steps)
    # later steps never need the guard
    run.validate(run.parse_args(["--country", "US", "--niche", "roofer"]), ["enrich", "import"])


def test_unknown_country_and_region():
    with pytest.raises(SystemExit):
        run.validate(run.parse_args(["--country", "FR", "--niche", "roofer"]), ["scrape"])
    with pytest.raises(SystemExit):
        run.validate(run.parse_args(["--country", "GB", "--niche", "roofer", "--region", "Narnia"]), ["scrape"])


def test_cells_and_region_selection():
    assert len(grid.select_cells("GB", None, 20)) == 20
    wy = grid.select_cells("GB", "west yorkshire")
    assert wy and all(c["region"] == "West Yorkshire" for c in wy)
    england = grid.select_cells("GB", "England")        # matches land_region too
    assert len(england) > len(wy)
    assert grid.language("DE") == "de" and grid.language("GB") == "en"


def test_all_six_grids_have_the_contract_shape():
    for cc in grid.COUNTRIES:
        cells = grid.load_grid(cc)
        assert cells and {"code", "ort", "region", "land_region", "lat", "lng"} <= set(cells[0])
    assert len(grid.load_grid("US")) > 40000


def test_run_names():
    a = args("--region", "West Yorkshire")
    assert run.run_name(a, niches.resolve("roofer")) == "GB-roofer-west-yorkshire"
    a = args("--search", "emergency roofer")
    assert run.run_name(a, niches.resolve("roofer", "emergency roofer")) == "GB-roofer--emergency-roofer"
    assert run.run_name(args(), niches.resolve("Schlüsseldienst")) == "GB-schluesseldienst"


def test_resume_command_quotes_and_names_the_step():
    cmd = run.resume_command(args("--region", "West Yorkshire", "--cells", "20"), "enrich")
    assert cmd == "python run.py --country GB --niche roofer --region 'West Yorkshire' --cells 20 --from enrich"


def test_normalize_fetch_flattens_nested_download(tmp_path):
    nested = tmp_path / "stage" / "GB-roofer" / "LS1.json"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}")
    (tmp_path / "stage" / "LS2.json").write_text("{}")
    dest = tmp_path / "runs" / "GB-roofer"
    assert run.normalize_fetch(tmp_path / "stage", dest) == 2
    assert sorted(p.name for p in dest.iterdir()) == ["LS1.json", "LS2.json"]


def test_registry_entry_is_replaced_not_duplicated(data_dir):
    a, spec = args("--region", "West Yorkshire"), niches.resolve("roofer")
    name = run.run_name(a, spec)
    run.update_registry(name, a, spec, {"cells": 85, "hits": 900, "unique": 400})
    run.update_registry(name, a, spec, {"cells": 85, "hits": 900, "unique": 400, "imported": 120})
    runs = json.loads((data_dir / "runs.json").read_text())["runs"]
    assert len(runs) == 1 and runs[0]["imported"] == 120 and runs[0]["region"] == "West Yorkshire"
    assert {"country", "niche", "cells", "businesses", "date"} <= set(runs[0])


def test_end_to_end_offline_after_scrape(data_dir, tmp_path, monkeypatch, capsys):
    """collect -> enrich -> import -> funnel from a fake fetched folder, with the network step replaced."""
    from pipeline.enrich import enrich
    folder = data_dir / "runs" / "GB-roofer-west-yorkshire"
    folder.mkdir(parents=True)
    cell = {"code": "LS1", "query": "q", "town": "Leeds", "region": "x", "hits": 1, "blocked": False, "rows": [
        {"place_id": "p1", "title": "Invented Roofing", "category": "Roofing contractor", "address": "1 Test St, Leeds LS1 4AB",
         "latitude": 53.797, "longitude": -1.545, "web_site": "https://invented-roofing.example", "review_count": 30,
         "review_rating": 4.8}]}
    (folder / "LS1.json").write_text(json.dumps(cell))
    monkeypatch.setattr(enrich, "enrich_websites", lambda rows, **k: _add_instagram(rows))
    monkeypatch.setattr(_paths, "SCHEMA", _paths.SCHEMA)
    monkeypatch.setenv("OUTREACH_DB", str(tmp_path / "x.db"))
    code = run.main(["--country", "GB", "--niche", "roofer", "--region", "West Yorkshire", "--from", "collect", "--no-activity"])
    out = capsys.readouterr().out
    assert code == 0 and "imported as leads" in out and "npm run dev" in out
    funnel = json.loads((folder / "funnel.json").read_text())
    assert funnel["imported"] == 1 and funnel["with_dm_channel"] == 1 and "email" not in out.lower()
    assert (data_dir / "runs.json").exists()


async def _add_instagram(rows):
    for r in rows:
        r["instagrams"] = ["https://www.instagram.com/inventedroofing/"]
    return {}
