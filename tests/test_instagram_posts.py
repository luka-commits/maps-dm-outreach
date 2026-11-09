import json
import sqlite3
from datetime import datetime, timezone

import httpx

from pipeline import _paths
from pipeline.social import instagram_posts as ip
from tests.test_activity import make_db

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def profile(handle="acmeroofing", **over):
    p = {"username": handle, "private": False, "postsCount": 40, "followersCount": 900, "biography": "Roofers",
         "latestPosts": [{"timestamp": f"2026-10-0{i}T10:00:00.000Z", "caption": f"cap {i}", "type": "Image",
                          "likesCount": i, "url": f"https://ig.example/p/{i}", "displayUrl": f"https://cdn.example/{i}.jpg"}
                         for i in range(1, 8)]}
    p.update(over)
    return p


def test_verdicts():
    assert ip.verdict(profile(), "Acme Roofing Ltd", NOW) is None
    assert ip.verdict(profile(private=True), "Acme Roofing", NOW) == "private"
    assert ip.verdict(profile(postsCount=2), "Acme Roofing", NOW).startswith("fewer than")
    assert "portal" in ip.verdict(profile(followersCount=900_000), "Acme Roofing", NOW)
    assert "does not match" in ip.verdict(profile(), "Zed Plumbing", NOW)
    old = profile(latestPosts=[{"timestamp": "2025-01-01T00:00:00Z"}])
    assert ip.verdict(old, "Acme Roofing", NOW).startswith("last post 2025-01-01")
    assert ip.verdict({"error": "x"}, "Acme", NOW) == "no profile"


def test_name_match_uses_squeezed_handle():
    assert ip.belongs_to_business("Door & Window Medic", "doorandwindowmedic")
    assert not ip.belongs_to_business("Acme Roofing", "checkatrade")


def setup_db(tmp_path, day="2026-11-09"):
    f = tmp_path / "l.db"
    db = make_db(f, [
        {"id": "a", "instagram": "https://www.instagram.com/acmeroofing/", "strategy": "opener-offer"},
        {"id": "b", "instagram": "https://www.instagram.com/bbb/", "strategy": "area-question"},
        {"id": "c", "instagram": "https://www.instagram.com/ccc/", "strategy": "opener-offer", "opener": "already written"},
        {"id": "d", "strategy": "opener-offer"},
        {"id": "e", "instagram": "https://www.instagram.com/eee/", "strategy": "opener-offer"},
    ])
    for pos, lid in enumerate("abcd"):
        db.execute("INSERT INTO batches (date, lead_id, position) VALUES (?,?,?)", (day, lid, pos))
    db.commit()
    return f


def test_who_needs_an_opener(tmp_path):
    f = setup_db(tmp_path)
    db = sqlite3.connect(f); db.row_factory = sqlite3.Row
    assert [l["id"] for l in ip.leads_needing_opener(db, "2026-11-09")] == ["a"]
    assert [l["id"] for l in ip.leads_needing_opener(db, "2026-11-09", ["e", "c"])] == ["e"]
    assert ip.leads_needing_opener(db, "2020-01-01") == []


def test_fetch_writes_profiles_images_and_reuses_raw(tmp_path, data_dir):
    f = setup_db(tmp_path)
    db = sqlite3.connect(f); db.row_factory = sqlite3.Row
    leads = ip.leads_needing_opener(db, "2026-11-09", ["a"])
    leads[0]["name"] = "Acme Roofing"
    calls = []

    def fake_run(token, actor, actor_input, cap):
        calls.append(actor_input)
        return [profile()], True, 0.0031

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"jpgbytes")))
    out = data_dir / "openers" / "2026-11-09"
    res = ip.fetch(leads, out, "tok", run_actor=fake_run, client=client)
    data = json.loads((out / "profiles.json").read_text())
    assert res["profiles"] == 1 and res["usable"] == 1 and res["cost_usd"] == 0.0031
    assert len(data[0]["posts"]) == 6 and data[0]["usable"]
    first = data[0]["posts"][0]["image"]
    assert first.endswith("images/acmeroofing__00.jpg")
    assert ip._display_path(_paths.ROOT / "data" / "openers" / "x.jpg") == "data/openers/x.jpg"
    assert len(list((out / "images").glob("*.jpg"))) == 6
    # second call: no second payment
    res2 = ip.fetch(leads, out, "tok", run_actor=fake_run, client=client)
    assert len(calls) == 1 and res2["fetched"] == 0
