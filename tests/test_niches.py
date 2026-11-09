from pipeline.scrape import niches


def test_free_keyword_derives_slug_search_and_terms():
    spec = niches.resolve("roofer")
    assert spec["slug"] == "roofer"
    assert spec["search"] == "roofer"
    assert not spec["preset"] and spec["exclusions"] == ()
    assert "roofer" in spec["terms"] and "roof" in spec["terms"]   # matches "Roofing contractor"
    assert spec["plural"] == "roofers"


def test_plural_keyword_and_multiword():
    assert "dentist" in niches.resolve("dentists")["terms"]
    spec = niches.resolve("emergency roofer")
    assert spec["slug"] == "emergency-roofer"
    assert "emergency" not in spec["terms"] and "roofer" in spec["terms"]
    assert niches.resolve("med spa")["plural"] == "med spas"
    assert niches.plural("pharmacy") == "pharmacies"


def test_search_override_marks_search_as_overridden():
    spec = niches.resolve("roofer", search="emergency roofer")
    assert spec["search"] == "emergency roofer" and spec["search_overridden"]
    assert not niches.resolve("roofer")["search_overridden"]


def test_preset_keeps_measured_terms_and_exclusions():
    spec = niches.resolve("towing")
    assert spec["preset"] and spec["search"] == "towing service"
    assert "towbar" in spec["exclusions"] and "recovery" in spec["terms"]
    assert len(niches.PRESETS) == 7


def test_german_keyword_hits_preset_via_transliterated_slug():
    spec = niches.resolve("Schlüsseldienst")
    assert spec["slug"] == "schluesseldienst" and spec["preset"]
    assert spec["search"] == "Schlüsseldienst"


def test_explicit_terms_override():
    assert niches.resolve("tiler", terms="tile, tiler ,tiling")["terms"] == ("tile", "tiler", "tiling")


def test_empty_keyword_is_an_error():
    import pytest
    with pytest.raises(SystemExit):
        niches.resolve("  ")
