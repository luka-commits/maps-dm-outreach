import json

import pytest

from pipeline.scrape import collect


def cell(code, rows, **extra):
    return {"code": code, "query": f"roofer in {code}", "town": "Whatever", "region": "Old",
            "hits": len(rows), "blocked": False, "rows": rows, **extra}


def test_collect_dedupes_across_cells_and_takes_region_from_grid(tmp_path, grid):
    shared = {"place_id": "same", "title": "Shared Roofing", "web_site": "https://s.example.com"}
    (tmp_path / "AA1.json").write_text(json.dumps(cell("AA1", [shared, {"place_id": "a", "title": "A"}])))
    (tmp_path / "BB1.json").write_text(json.dumps(cell("BB1", [shared, {"place_id": "b", "title": "B"}], blocked=True)))
    (tmp_path / "CC1.json").write_text(json.dumps(cell("CC1", [])))
    (tmp_path / "niche.json").write_text("{}")
    rows, report = collect.collect(tmp_path, "GB", grid=grid)
    assert sorted(r["placeId"] for r in rows) == ["a", "b", "same"]
    assert report["cells"] == 3 and report["hits"] == 4 and report["unique"] == 3
    assert report["cells_blocked"] == 1 and report["cells_empty"] == 1
    first = next(r for r in rows if r["placeId"] == "same")
    assert first["_cell"] == "AA1" and first["_region"] == "Northshire" and first["_ort"] == "Alderton"
    assert report["with_website"] == 1


def test_empty_folder_is_an_error(tmp_path, grid):
    with pytest.raises(SystemExit):
        collect.collect(tmp_path, "GB", grid=grid)


def test_broken_cell_file_is_skipped(tmp_path, grid, capsys):
    (tmp_path / "AA1.json").write_text("{not json")
    (tmp_path / "BB1.json").write_text(json.dumps(cell("BB1", [{"place_id": "b", "title": "B"}])))
    rows, _ = collect.collect(tmp_path, "GB", grid=grid)
    assert len(rows) == 1 and "not JSON" in capsys.readouterr().out
