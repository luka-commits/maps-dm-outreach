import re

from pipeline import geo
from pipeline.import_leads import postcode_of
from pipeline.scrape import build_grid, grid


def row(code, place, admin1, admin2, lat, lng):
    return ["XX", code, place, admin1, "", admin2, "", "", "", str(lat), str(lng), "4"]


ROWS = [
    row("1011 AB", "Amsterdam", "North Holland", "Amsterdam", 52.37, 4.90),
    row("1011 AC", "Amsterdam", "North Holland", "Amsterdam", 52.38, 4.91),
    row("3011 AA", "Rotterdam", "South Holland", "", 51.92, 4.48),
    row("75021 CEDEX 01", "Paris 01", "Île-de-France", "Paris", 48.86, 2.34),
    row("", "empty", "x", "x", 1, 1),
    row("9999", "no coordinates", "x", "x", "", ""),
]


def test_one_cell_per_district_and_bulk_mail_codes_dropped():
    cells, extra = build_grid.build("XX", ROWS)
    assert [c["code"] for c in cells] == ["1011", "3011"]
    ams = cells[0]
    assert ams["ort"] == "Amsterdam" and ams["lat"] == 52.375
    assert ams["region"] == "Amsterdam" and ams["land_region"] == "North Holland"
    assert cells[1]["region"] == "South Holland"          # no second level: falls back to the first


def test_prefix_groups_codes():
    cells, _ = build_grid.build("XX", ROWS, prefix=2)
    assert [c["code"] for c in cells] == ["10", "30"]


def test_box_and_postcode_pattern():
    _, extra = build_grid.build("XX", ROWS)
    lo_lat, hi_lat, lo_lng, hi_lng = extra["box"]
    assert lo_lat < 51.92 and hi_lat > 52.38 and lo_lng < 4.48 and hi_lng > 4.91
    pattern = extra["postcode_pattern"]
    assert re.search(pattern, "Damrak 1, 1012 LG Amsterdam").group(0) == "1012 LG"
    assert re.search(pattern, "1012LG").group(0) == "1012LG"


def test_built_country_is_used_by_run_geo_and_import(tmp_path, monkeypatch):
    monkeypatch.setattr(grid, "REGIONS", tmp_path)
    (tmp_path / "XX_postcodes.json").write_text('{"liste": [{"code": "1011", "ort": "A", "region": "R", '
                                                '"land_region": "L", "lat": 52.0, "lng": 4.0}]}')
    (tmp_path / "XX.json").write_text('{"language": "nl", "box": [50, 54, 3, 8], '
                                      r'"postcode_pattern": "\\b\\d{4}\\s?[A-Z]{2}\\b"}')
    assert "XX" in grid.countries() and grid.language("XX") == "nl"
    assert geo.in_country(52.3, 4.9, "XX") is True and geo.in_country(48.8, 2.3, "XX") is False
    assert geo.foreign_country(48.8, 2.3, "https://bakker.xx", "XX") is False
    assert postcode_of("Damrak 1, 1012 lg Amsterdam", "XX") == "1012 LG"


def test_missing_grid_names_the_build_command(tmp_path, monkeypatch):
    monkeypatch.setattr(grid, "REGIONS", tmp_path)
    try:
        grid.load_grid("FR")
    except SystemExit as e:
        assert "build_grid.py FR" in str(e)
    else:
        raise AssertionError("expected SystemExit")
