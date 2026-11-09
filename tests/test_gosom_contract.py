from pipeline.scrape.gosom_contract import (field_coverage, identity_key, parse_gosom_output,
                                            to_apify_shape)

RAW = {"place_id": "pid1", "title": "  Acme Roofing ", "category": "Roofing contractor",
       "categories": ["Roofing contractor", "Gutter service"], "address": "1 Test Road",
       "complete_address": {"city": "Alderton", "state": "Northshire", "country": "GB"},
       "latitude": 53.8, "longitude": -1.5, "web_site": "https://acme.example.com", "phone": "01234 567890",
       "review_rating": 4.5, "review_count": 12, "emails": ["Info@Acme.example.com", "info@acme.example.com"],
       "status": "OPERATIONAL", "link": "https://maps.example/x"}


def test_shape_maps_fields_and_dedupes_emails():
    row = to_apify_shape(RAW, "2026-01-01T00:00:00Z", query="roofer in Alderton AA1, GB")
    assert row["placeId"] == "pid1" and row["title"] == "Acme Roofing"
    assert row["location"] == {"lat": 53.8, "lng": -1.5}
    assert row["emails"] == ["info@acme.example.com"]
    assert row["reviewsCount"] == 12 and row["totalScore"] == 4.5
    assert row["city"] == "Alderton" and row["state"] == "Northshire"
    assert row["instagrams"] == [] and row["facebooks"] == []


def test_id_fallbacks_and_misspelled_longitude():
    row = to_apify_shape({"cid": "99", "title": "X", "latitude": 1, "longtitude": 2}, "t")
    assert row["placeId"] == "cid:99" and row["location"]["lng"] == 2.0


def test_identity_key_order():
    assert identity_key({"placeId": "p"}) == "place:p"
    assert identity_key({"website": "https://www.Foo.com/x"}) == "domain:foo.com"
    assert identity_key({"phone": "+44 1234 567890"}) == "phone:1234567890"
    assert identity_key({"title": "A", "address": "B"}) == "name-address:a|b"
    assert identity_key({}) is None


def test_parse_accepts_json_lines_and_array():
    assert len(parse_gosom_output('{"a":1}\n{"a":2}\n')) == 2
    assert parse_gosom_output('[{"a":1}]') == [{"a": 1}]
    assert parse_gosom_output("  ") == []


def test_field_coverage():
    cov = field_coverage([{"website": "x", "location": {"lat": 1, "lng": 2}}, {}])
    assert cov["website"]["count"] == 1 and cov["location"]["rate"] == 0.5
