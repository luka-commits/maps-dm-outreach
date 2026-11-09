import sqlite3

import pytest

from pipeline import import_leads as imp
from tests.conftest import make_row, read_leads

CONFIG = {"import": {"min_reviews": 5, "require_website": True}}


def run_import(rows, db_file, spec, grid, monkeypatch, country="GB", config=CONFIG, run="GB-roofer-northshire"):
    monkeypatch.setattr(imp, "load_grid", lambda c: grid)
    return imp.import_rows(rows, run, spec, country, db_file, config)


def test_profile_normalisation_junk_paths():
    p = imp.profile
    assert p("instagram.com/ACME_Roofing?hl=en", "instagram") == "https://www.instagram.com/acme_roofing/"
    for junk in ("https://instagram.com/p/Abc123", "https://instagram.com/explore", "https://instagram.com/a/b",
                 "https://evil.example/instagram.com/x"):
        assert p(junk, "instagram") is None
    assert p("https://facebook.com/acmeroofing/", "facebook") == "https://www.facebook.com/acmeroofing/"
    assert p("https://www.facebook.com/profile.php?id=12345", "facebook") == "https://www.facebook.com/profile.php?id=12345"
    for junk in ("https://facebook.com/policy.php", "https://facebook.com/policy/", "https://facebook.com/sharer/sharer.php",
                 "https://facebook.com/acme/posts/123", "https://facebook.com/groups/foo", "https://facebook.com/"):
        assert p(junk, "facebook") is None
    assert p("https://facebook.com/pages/Acme/12345", "facebook") == "https://www.facebook.com/pages/Acme/12345/"



def test_postcodes_per_country():
    assert imp.postcode_of("1 High St, Leeds LS1 4AB, UK", "GB") == "LS1 4AB"
    assert imp.postcode_of("12 Main St, Austin, TX 78701, USA", "US") == "78701"
    assert imp.postcode_of("Hauptstr. 5, 01067 Dresden, Germany", "DE") == "01067"
    assert imp.postcode_of("5 George St, Sydney NSW 2000, Australia", "AU") == "2000"
    assert imp.postcode_of("1 Rue St, Toronto, ON M5V 2T6, Canada", "CA") == "M5V 2T6"
    assert imp.postcode_of("Main St, Dublin D02 X285, Ireland", "IE") == "D02 X285"
    assert imp.postcode_of(None, "GB") is None


def test_import_fields_town_neighbour_region(db_file, spec, grid, monkeypatch):
    summary = run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    lead = read_leads(db_file)["place-1"]
    assert summary["new"] == 1 and summary["imported"] == 1 and summary["with_instagram"] == 1
    assert lead["town"] == "Alderton" and lead["region"] == "Northshire" and lead["country"] == "GB"
    assert lead["neighbour_town"] == "Bexley Green"   # nearest other town >= 2 km
    assert lead["neighbour_town"] != "Alderton"
    assert lead["postcode"] == "AA1 2BC" and lead["niche"] == "roofer" and lead["run"] == "GB-roofer-northshire"
    assert lead["instagram"] == "https://www.instagram.com/roofing1/" and lead["imported_at"]


def test_neighbour_town_us_fixture(db_file, spec, monkeypatch):
    us = [{"code": "78701", "ort": "Springfield", "region": "Texas", "land_region": "Texas", "lat": 30.27, "lng": -97.74},
          {"code": "78702", "ort": "Springfield", "region": "Texas", "land_region": "Texas", "lat": 30.271, "lng": -97.741},
          {"code": "78610", "ort": "Buda", "region": "Texas", "land_region": "Texas", "lat": 30.08, "lng": -97.84},
          {"code": "78660", "ort": "Pflugerville", "region": "Texas", "land_region": "Texas", "lat": 30.44, "lng": -97.62}]
    row = make_row(7, address="5 Main St, Springfield, TX 78701, USA", location={"lat": 30.27, "lng": -97.74},
                   _region="Texas", city=None, website="https://us-roofer.example.com")
    run_import([row], db_file, spec, us, monkeypatch, country="US", run="US-roofer-texas")
    lead = read_leads(db_file)["place-7"]
    assert lead["town"] == "Springfield" and lead["neighbour_town"] == "Pflugerville"
    assert lead["postcode"] == "78701" and lead["country"] == "US" and lead["region"] == "Texas"


def test_filters(db_file, spec, grid, monkeypatch):
    rows = [
        make_row(1),
        make_row(2, categoryName="Pizza restaurant", categories=["Pizza restaurant"], title="Luigi"),
        make_row(3, reviewsCount=2),
        make_row(4, website=None),
        make_row(5, instagrams=[], facebooks=[]),   # an email alone is no DM channel
        make_row(6, location={"lat": 40.0, "lng": 10.0}, website="https://foreign.example.com"),
        make_row(7, title="Halfords Roofing"),
        make_row(8, businessStatus="Permanently closed"),
        *[make_row(20 + i, website="https://chain.example.co.uk/s") for i in range(10)],
        make_row(9, instagrams=["https://instagram.com/p/Abc"], facebooks=[]),
    ]
    s = run_import(rows, db_file, spec, grid, monkeypatch)
    assert set(read_leads(db_file)) == {"place-1"}
    assert s["not niche"] == 1 and s["too small"] == 2 and s["no channel"] == 2
    assert s["outside country"] == 1 and s["chain"] == 11 and s["closed"] == 1


def test_config_switches(db_file, spec, grid, monkeypatch):
    rows = [make_row(1, reviewsCount=3), make_row(2, website=None)]
    run_import(rows, db_file, spec, grid, monkeypatch, config={"import": {"min_reviews": 1, "require_website": False}})
    assert set(read_leads(db_file)) == {"place-1", "place-2"}


def test_reimport_preserves_hand_kept_fields(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    db = sqlite3.connect(db_file)
    db.execute("UPDATE leads SET linkedin='li', neighbour_town_manual='Handtown', opener='nice roof', notes='n', "
               "contacted_on='2026-01-02', disqualified='no thanks', strategy='area-question', "
               "instagram_inactive='last post 2020-01-01', imported_at='2000-01-01T00:00:00+00:00' WHERE id='place-1'")
    db.commit(); db.close()
    changed = make_row(1, title="Renamed Roofing", phone="999", reviewsCount=40, instagrams=[], facebooks=["https://facebook.com/newpage"])
    s = run_import([changed], db_file, spec, grid, monkeypatch, run="GB-roofer-other-run")
    lead = read_leads(db_file)["place-1"]
    assert s["updated"] == 1 and s["new"] == 0
    # scraped fields refreshed
    assert lead["name"] == "Renamed Roofing" and lead["phone"] == "999" and lead["reviews"] == 40
    assert lead["facebook"] == "https://www.facebook.com/newpage/"
    # empty channels never delete existing ones; no email column exists
    assert lead["instagram"] == "https://www.instagram.com/roofing1/"
    # hand-kept fields and first-import metadata untouched
    assert (lead["linkedin"], lead["neighbour_town_manual"], lead["opener"], lead["notes"]) == ("li", "Handtown", "nice roof", "n")
    assert (lead["contacted_on"], lead["disqualified"], lead["strategy"]) == ("2026-01-02", "no thanks", "area-question")
    assert lead["imported_at"].startswith("2000") and lead["run"] == "GB-roofer-northshire"
    assert lead["instagram_inactive"] == "last post 2020-01-01"      # instagram did not change


def test_changed_profile_clears_stale_inactive_mark(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    db = sqlite3.connect(db_file)
    db.execute("UPDATE leads SET instagram_inactive='last post 2020-01-01'"); db.commit(); db.close()
    run_import([make_row(1, instagrams=["https://instagram.com/otheraccount"])], db_file, spec, grid, monkeypatch)
    assert read_leads(db_file)["place-1"]["instagram_inactive"] is None


def test_idempotent_reimport(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    s = run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    assert s["updated"] == 0 and s["new"] == 0


def test_row_without_id_is_an_error(db_file, spec, grid, monkeypatch):
    with pytest.raises(ValueError):
        run_import([make_row(1, placeId=None)], db_file, spec, grid, monkeypatch)


# ---- regression tests for the first live probe -------------------------------------------------

def test_platform_handles_are_never_the_business():
    for handle in ("wix", "squarespace", "godaddy", "wordpress", "shopify", "weebly", "jimdo", "checkatrade",
                   "yell", "mybuilder", "ratedpeople", "trustatrader", "houzz", "facebook", "meta", "google"):
        assert imp.profile(f"https://www.instagram.com/{handle}/", "instagram") is None, handle
        assert imp.profile(f"https://www.facebook.com/{handle}/", "facebook") is None, handle
    assert imp.profile("https://www.instagram.com/wix_roofing_co/", "instagram")     # only the exact handle
    assert imp.profile("https://www.facebook.com/Wix/", "facebook") is None          # case-insensitive


def test_handle_shared_by_three_websites_is_a_platform(db_file, spec, grid, monkeypatch):
    agency = "https://www.instagram.com/webagencyxyz/"
    rows = [make_row(i, instagrams=[agency, f"https://www.instagram.com/own{i}/"],
                     website=f"https://site{i}.example.com") for i in (1, 2, 3)]
    rows += [make_row(4, instagrams=["https://www.instagram.com/twice/"], website="https://four.example.com"),
             make_row(5, instagrams=["https://www.instagram.com/twice/"], website="https://five.example.com")]
    assert imp.platform_profiles(rows) == {agency}
    run_import(rows, db_file, spec, grid, monkeypatch)
    leads = read_leads(db_file)
    assert [leads[f"place-{i}"]["instagram"] for i in (1, 2, 3)] == [f"https://www.instagram.com/own{i}/" for i in (1, 2, 3)]
    assert leads["place-4"]["instagram"] == "https://www.instagram.com/twice/"      # two sites: still a plausible own account


def test_platform_only_lead_is_skipped_and_a_stored_platform_link_is_dropped(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    db = sqlite3.connect(db_file)
    db.execute("UPDATE leads SET instagram='https://www.instagram.com/wix/', facebook='https://www.facebook.com/realpage/' WHERE id='place-1'")
    db.execute("INSERT INTO leads (id, name, instagram, imported_at) VALUES ('place-2','Stale','https://www.instagram.com/wix/','x')")
    db.commit(); db.close()
    rows = [make_row(1, instagrams=["https://www.instagram.com/wix/"], facebooks=["https://facebook.com/realpage"]),
            make_row(2, instagrams=["https://www.instagram.com/wix/"], facebooks=[])]
    s = run_import(rows, db_file, spec, grid, monkeypatch)
    leads = read_leads(db_file)
    assert leads["place-1"]["instagram"] is None and leads["place-1"]["facebook"] == "https://www.facebook.com/realpage/"
    assert "place-2" not in leads and s["removed"] == 1 and s["no channel"] == 1


def test_touched_lead_is_not_removed_when_rules_reject_it(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    db = sqlite3.connect(db_file)
    db.execute("UPDATE leads SET notes='called them' WHERE id='place-1'"); db.commit(); db.close()
    s = run_import([make_row(1, categoryName="Roofing supply store", categories=["Roofing supply store"])],
                   db_file, spec, grid, monkeypatch)
    assert "place-1" in read_leads(db_file) and s["removed"] == 0 and s["not niche"] == 1


CASTLEFORD_GRID = [
    {"code": "WF10", "ort": "Castleford", "region": "West Yorkshire", "land_region": "England", "lat": 53.725, "lng": -1.35},
    {"code": "WF10A", "ort": "Castleford Central", "region": "West Yorkshire", "land_region": "England", "lat": 53.726, "lng": -1.351},
    {"code": "WF3", "ort": "Ledston", "region": "West Yorkshire", "land_region": "England", "lat": 53.757, "lng": -1.34},
    {"code": "WF7", "ort": "Featherstone", "region": "West Yorkshire", "land_region": "England", "lat": 53.70, "lng": -1.36},
]


def test_town_prefers_googles_city_over_the_nearest_centroid(db_file, spec, monkeypatch):
    # the business is closest to the Ledston centroid, but Google says Castleford
    row = make_row(1, city="Castleford", address="53 Front St, Castleford WF10 4FQ, United Kingdom",
                   location={"lat": 53.756, "lng": -1.341}, _region="West Yorkshire")
    run_import([row], db_file, spec, CASTLEFORD_GRID, monkeypatch)
    lead = read_leads(db_file)["place-1"]
    assert lead["town"] == "Castleford" and lead["region"] == "West Yorkshire"
    # neighbour: nearest other town >= 2 km from the business, never the town, a part of it or one next to it
    assert lead["neighbour_town"] == "Featherstone"


def test_town_from_address_when_city_is_missing_then_grid():
    assert imp.locality_from_address("53 Front St, Castleford WF10 4FQ, United Kingdom") == "Castleford"
    assert imp.locality_from_address("Allerton Bywater, Castleford WF10 2BS, UK") == "Castleford"
    assert imp.locality_from_address("5 Main St, Springfield, TX 78701, USA") == "Springfield"
    assert imp.locality_from_address("1 Rue St, Toronto, ON M5V 2T6, Canada") == "Toronto"
    assert imp.locality_from_address("Hauptstr. 5, 01067 Dresden, Germany") == "Dresden"
    assert imp.locality_from_address("5 George St, Sydney NSW 2000, Australia") == "Sydney"
    assert imp.locality_from_address("Sherburn Rd") is None                  # no postcode: no anchor
    assert imp.plausible_city("United Kingdom") is None and imp.plausible_city("LS1 4AB") is None
    assert imp.plausible_city("  Leeds ") == "Leeds"


def test_town_falls_back_to_grid_without_city_or_postcode(db_file, spec, monkeypatch):
    row = make_row(1, city=None, address="Somewhere unnamed", location={"lat": 53.756, "lng": -1.341})
    run_import([row], db_file, spec, CASTLEFORD_GRID, monkeypatch)
    assert read_leads(db_file)["place-1"]["town"] == "Ledston"


def test_retail_and_wholesale_categories_are_not_the_trade():
    terms = ("roofer", "roof")
    for cat in ("Roofing supply store", "Roofing wholesaler", "Roofing tile manufacturer", "Steel supplier",
                "Roofing distributor"):
        assert not imp.niche_match(make_row(1, categoryName=cat, categories=[cat]), terms), cat
    assert imp.niche_match(make_row(1), terms)
    # the keyword itself names a store: allowed
    assert imp.niche_match(make_row(1, categoryName="Mattress store", categories=["Mattress store"], title="Sleep Co"),
                           ("mattress", "mattress store"))


def test_title_alone_only_counts_for_missing_or_generic_categories():
    terms = ("roofer", "roof")
    joiner = make_row(1, title="Smart Roofing & Joinery", categoryName="Joiner", categories=["Joiner"])
    assert not imp.niche_match(joiner, terms)                      # a joiner, whatever the name says
    generic = make_row(2, title="Hill Roofing", categoryName="General contractor", categories=["General contractor"])
    assert imp.niche_match(generic, terms)
    nocat = make_row(3, title="Hill Roofing", categoryName=None, categories=[])
    assert imp.niche_match(nocat, terms)
    secondary = make_row(4, title="Dave Smith", categoryName="Joiner", categories=["Joiner", "Roofing contractor"])
    assert imp.niche_match(secondary, terms)                        # a secondary category of the trade is enough


def test_lead_with_a_real_channel_survives_a_run_where_enrichment_found_nothing(db_file, spec, grid, monkeypatch):
    run_import([make_row(1)], db_file, spec, grid, monkeypatch)
    s = run_import([make_row(1, instagrams=[], facebooks=[])], db_file, spec, grid, monkeypatch)
    assert "place-1" in read_leads(db_file) and s["removed"] == 0 and s["no channel"] == 1
