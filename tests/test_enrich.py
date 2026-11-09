import asyncio
import json

import httpx

from pipeline.enrich import enrich, owner
from pipeline.enrich.domains import chain_domains, domain_of, is_builder, is_shared_host
from pipeline.enrich.filter_niche import classify
from pipeline.scrape import niches
from tests.conftest import make_row

HOME = """<html><body>
<a href="mailto:Info@acme-roofing.example?subject=hi">mail</a>
<a href="/contact-us">Contact</a><a href="/about">About</a>
<a href="https://www.instagram.com/acmeroofing/?hl=en">ig</a>
<a href="https://facebook.com/acmeroofing">fb</a>
<a href="https://[bad host/">broken</a>
<span data-cfemail="%s"></span>
</body></html>"""


def cf(email, key=0x2A):
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


def test_extract_contacts_all_sources():
    html = HOME % cf("sales@acme-roofing.example") + " write to dave [at] acme-roofing [dot] example"
    found = enrich.extract_contacts(html, "https://acme-roofing.example/")
    assert "info@acme-roofing.example" in found["emails"]
    assert "sales@acme-roofing.example" in found["emails"]
    assert "dave@acme-roofing.example" in found["emails"]
    assert found["instagrams"] == ["https://www.instagram.com/acmeroofing/"]
    assert found["facebooks"] == ["https://facebook.com/acmeroofing"]
    assert "https://acme-roofing.example/contact-us" in found["pages"]


def test_email_cleaning():
    assert enrich.clean_contact_email("x@sentry.io") is None
    assert enrich.clean_contact_email("noreply@foo.com") is None
    assert enrich.clean_contact_email("logo@2x.png") is None
    assert enrich.clean_contact_email("(Info@Foo.com).") == "info@foo.com"


def test_own_domain_and_role_inbox_first():
    ordered = enrich.order_contact_emails(["z@gmail.com", "bob@foo.com", "info@foo.com"], "foo.com")
    assert ordered == ["info@foo.com", "bob@foo.com", "z@gmail.com"]


def test_candidate_pages_limit_and_fallbacks():
    pages = enrich.candidate_contact_pages("https://a.example/", ["/contact", "https://other.example/contact", "/x"])
    assert len(pages) <= 4 and "https://a.example/contact" in pages
    assert all("other.example" not in p for p in pages)


def test_domains_chain_shared_builder():
    assert domain_of({"website": "https://www.Foo.com/x"}) == "foo.com"
    assert domain_of({"website": "foo.com"}) == "foo.com"
    assert is_shared_host("facebook.com") and is_builder("x.wixsite.com")
    rows = [{"website": f"https://chain.example/{i}"} for i in range(10)] + [{"website": "https://one.example"}]
    rows += [{"website": f"https://facebook.com/p{i}"} for i in range(12)]
    assert chain_domains(rows) == {"chain.example"}


def test_target_rows_skip_off_niche_chains_and_no_website():
    spec = niches.resolve("roofer")
    rows = [make_row(1), make_row(2, website=None), make_row(3, categoryName="Pizza restaurant", categories=["Pizza restaurant"], title="Luigi"),
            *[make_row(10 + i, website="https://bigchain.example/x") for i in range(10)]]
    targets = enrich.target_rows(rows, spec["terms"])
    assert [r["placeId"] for r in targets] == ["place-1"]


def test_classify_does_not_treat_the_niche_itself_as_foreign_trade():
    terms = niches.resolve("roofer")["terms"]
    assert classify(make_row(1, categories=["Roofing contractor", "Gutter service"]), terms) == "keep"
    assert classify(make_row(2, title="Dave", categoryName="Pizza restaurant", categories=["Pizza restaurant"]), terms) == "drop"
    assert classify(make_row(3, categoryName=None, categories=[], title="Dave"), terms) == "verify"
    assert classify(make_row(4, title="Town Hall", categoryName="Government office"), terms) == "drop"
    assert classify(make_row(5, categoryName="Towing equipment provider", title="X Towbars"),
                    niches.resolve("towing")["terms"], niches.resolve("towing")["exclusions"]) == "drop"


def test_owner_names():
    towns = {"marietta"}
    assert owner.from_email("steve@thekeymarket.example", towns) == "steve"
    assert owner.from_email("info@x.example", towns) is None
    assert owner.from_business_name("Brian Smith Heating & Plumbing", towns) == "Brian"
    assert owner.from_business_name("MAB Locksmiths", towns) is None
    assert owner.from_business_name("Marietta Top Locksmith", towns) is None      # a town, not a person
    assert owner.from_business_name("Sparkle Cleaning", towns) is None            # a brand word
    assert owner.from_website_text("Hi, I'm Dave and I have been a roofer for 20 years", towns) == "Dave"
    assert owner.find(business_name="Brian Smith Roofing", email="neil@x.example")["first_name"] == "Neil"
    assert owner.find(business_name="Zzzz Qqq") is None


def fake_site(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    if host == "down.example":
        return httpx.Response(500)
    if path in ("/", ""):
        return httpx.Response(200, headers={"content-type": "text/html"},
                              text=HOME % cf("sales@acme-roofing.example") + "<p>Hi, I'm Dave, owner.</p>")
    if path == "/contact-us":
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>mail office@acme-roofing.example</p>")
    return httpx.Response(404)


def test_enrich_websites_with_mock_transport(tmp_path):
    rows = [make_row(1, website="https://acme-roofing.example/", emails=[], instagrams=[], title="Acme Roofing"),
            make_row(2, website="https://down.example/", emails=[], instagrams=[])]
    stats = enrich.RunStats()
    cache_path = tmp_path / "website_enrichment.json"

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake_site), follow_redirects=True) as client:
            return await enrich.enrich_websites(rows, cache_path=cache_path, stats=stats, client=client)

    cache = asyncio.run(go())
    assert rows[0]["emails"][0] == "info@acme-roofing.example"
    assert "office@acme-roofing.example" in rows[0]["emails"]           # from the contact page
    assert rows[0]["instagrams"] == ["https://www.instagram.com/acmeroofing/"]
    assert rows[0]["ownerName"] == "Dave" and rows[0]["ownerSource"] == "website"
    assert rows[1]["emails"] == [] and cache["down.example"]["status"] == "failed"
    assert stats["website_errors"] == 1 and stats["unique_websites"] == 2
    assert json.loads(cache_path.read_text())["acme-roofing.example"]["status"] == "measured"

    # second run is served from the cache: a transport that always fails changes nothing
    again = [make_row(1, website="https://acme-roofing.example/", emails=[], instagrams=[], title="Acme Roofing")]

    async def go2():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
            await enrich.enrich_websites(again, cache_path=cache_path, client=client)

    asyncio.run(go2())
    assert again[0]["emails"][0] == "info@acme-roofing.example"


# ---- regression tests for the first live probe -------------------------------------------------

def test_email_that_is_the_business_label_is_not_a_person():
    t = ("roofer", "roof")
    assert owner.from_email("clarkroofing@live.example", set(), business_name="Clark Roofing", trade_terms=t) is None
    assert owner.from_email("clark.roofing@live.example", set(), trade_terms=t) is None
    assert owner.from_email("clark@live.example", set(), business_name="Clark Roofing", trade_terms=t) == "clark"
    assert owner.from_email("lukehartley896@yahoo.example", {"hartley"}, business_name="L Hartley's Roofing", trade_terms=t) == "luke"
    assert owner.from_email("smartroofingjoinery@gmail.example", set(), business_name="Smart Roofing & Joinery") is None


def test_one_word_before_the_trade_is_a_surname_not_a_first_name():
    t = ("roofer", "roof")
    assert owner.from_business_name("Clark Roofing", set(), trade_terms=t) is None
    assert owner.from_business_name("Brian Smith Roofing", set(), trade_terms=t) == "Brian"
    assert owner.from_business_name("Dave's Roofing", set(), trade_terms=t) == "Dave"
    assert owner.find(business_name="Clark Roofing", emails=["clarkroofing@live.example"], trade_terms=t) is None


def test_any_email_wins_over_website_text_and_months_are_not_names():
    emails = ["info@yorkshireroofing.example", "tracey@yorkshireroofing.example"]
    found = owner.find(business_name="Yorkshire Roofing", emails=emails, website_name="May",
                       website_text="Director, May 2019 since 1999", trade_terms=("roof",))
    assert found == {"first_name": "Tracey", "source": "email"}
    for month in ("May", "June", "April", "August", "March"):
        assert owner.from_website_text(f"Managing director {month} 2020", set()) is None
        assert not owner.valid_website_name(month)
    assert owner.valid_website_name("Dave")
    # a cached month from an older run is ignored at use time
    assert owner.find(business_name="Zed Qux", emails=[], website_name="May") is None
    assert owner.find(business_name="Zed Qux", emails=[], website_name="Dave")["first_name"] == "Dave"


def test_two_different_names_in_the_emails_is_ambiguous():
    assert owner.from_emails(["tracey@x.example", "steve@x.example"], set()) is None
    assert owner.from_emails(["tracey@x.example", "tracey.b@x.example"], set()) == "tracey"


def test_retail_category_is_not_fetched():
    spec = niches.resolve("roofer")
    rows = [make_row(1), make_row(2, categoryName="Roofing supply store", categories=["Roofing supply store"], title="SIG Roofing")]
    assert [r["placeId"] for r in enrich.target_rows(rows, spec["terms"])] == ["place-1"]
