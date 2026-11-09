"""Shared fixtures. Everything here is invented; no test touches the network, Modal or Apify."""
import json
import pathlib
import sqlite3

import pytest

from pipeline import _paths

# A tiny invented postcode grid: three towns in a line, plus a far one.
GRID = [
    {"code": "AA1", "ort": "Alderton", "region": "Northshire", "land_region": "England", "lat": 53.80, "lng": -1.55},
    {"code": "AA2", "ort": "Alderton", "region": "Northshire", "land_region": "England", "lat": 53.801, "lng": -1.551},
    {"code": "BB1", "ort": "Bexley Green", "region": "Northshire", "land_region": "England", "lat": 53.85, "lng": -1.55},
    {"code": "CC1", "ort": "Carrow", "region": "Northshire", "land_region": "England", "lat": 53.70, "lng": -1.50},
    {"code": "DD1", "ort": "Dunmere", "region": "Southshire", "land_region": "England", "lat": 51.50, "lng": -0.12},
]


def make_row(i, **over):
    row = {
        "placeId": f"place-{i}", "title": f"Test Roofing Co {i}", "categoryName": "Roofing contractor",
        "categories": ["Roofing contractor"], "address": f"{i} High Street, Alderton AA1 2BC, UK",
        "city": "Alderton", "location": {"lat": 53.80, "lng": -1.55}, "phone": "01234 567890",
        "website": f"https://roofing{i}.example-site.co.uk", "totalScore": 4.6, "reviewsCount": 25,
        "emails": [f"info@roofing{i}.example-site.co.uk"], "instagrams": [f"https://www.instagram.com/roofing{i}/"],
        "facebooks": [], "_region": "Northshire", "_ort": "Alderton", "_cell": "AA1",
    }
    row.update(over)
    return row


@pytest.fixture
def grid():
    return [dict(g) for g in GRID]


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "leads.db"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "DATA", tmp_path / "data")
    return tmp_path / "data"


@pytest.fixture
def spec():
    from pipeline.scrape import niches
    return niches.resolve("roofer")


def read_leads(db_file):
    db = sqlite3.connect(db_file)
    db.row_factory = sqlite3.Row
    try:
        return {r["id"]: dict(r) for r in db.execute("SELECT * FROM leads")}
    finally:
        db.close()
