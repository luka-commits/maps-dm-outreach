import json
import sqlite3
from datetime import date

import pytest

from pipeline import _paths
from pipeline.social import activity, apify

TODAY = date(2026, 11, 9)
OLD, NEW = "2023-08-17", "2026-10-01"


def make_db(db_file, leads):
    db = sqlite3.connect(db_file)
    db.executescript(_paths.SCHEMA.read_text())
    for lead in leads:
        cols = {"id": lead["id"], "name": lead["id"], "imported_at": "2026-01-01", **{k: v for k, v in lead.items() if k != "id"}}
        db.execute(f"INSERT INTO leads ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", list(cols.values()))
    db.commit()
    return db


def ig(handle):
    return f"https://www.instagram.com/{handle}/"


def fb(page):
    return f"https://www.facebook.com/{page}/"


class FakeApify:
    """Stands in for activity.query_apify; records what was asked."""

    def __init__(self, answers, finished=True, cost=0.01):
        self.answers, self.finished, self.cost, self.calls = answers, finished, cost, []

    def __call__(self, channel, keys, urls, token, cap, today):
        self.calls.append((channel, list(keys)))
        found = {k: v for k, v in self.answers.get(channel, {}).items() if k in keys}
        if self.finished:
            for k in keys:
                found.setdefault(k, {"last_post": None, "error": "no_data", "checked": today})
        return found, self.finished, self.cost


def rows(db_file):
    db = sqlite3.connect(db_file); db.row_factory = sqlite3.Row
    return {r["id"]: dict(r) for r in db.execute("SELECT * FROM leads")}


@pytest.fixture
def leads_db(tmp_path, data_dir):
    f = tmp_path / "l.db"
    make_db(f, [
        {"id": "both-dead", "instagram": ig("bothdead"), "facebook": fb("bothdead")},
        {"id": "one-dead", "instagram": ig("onedead"), "facebook": fb("onedead")},
        {"id": "alive", "instagram": ig("alive")},
        {"id": "zero-posts", "instagram": ig("empty")},
        {"id": "unknown-fb", "instagram": ig("igdead"), "facebook": fb("private")},
        {"id": "contacted", "instagram": ig("olddead"), "contacted_on": "2026-05-01"},
        {"id": "disq", "instagram": ig("olddead2"), "disqualified": "manual"},
        {"id": "no-social", "linkedin": "https://linkedin.example/in/x"},
    ])
    return f


ANSWERS = {
    "instagram": {"bothdead": {"posts": 90, "last_post": OLD}, "onedead": {"posts": 90, "last_post": OLD},
                  "alive": {"posts": 50, "last_post": NEW}, "empty": {"posts": 0, "last_post": None},
                  "igdead": {"posts": 9, "last_post": OLD}},
    "facebook": {fb("bothdead").lower().rstrip("/"): {"last_post": OLD},
                 fb("onedead").lower().rstrip("/"): {"last_post": NEW}},
}


def test_dry_run_changes_nothing_but_caches(leads_db, data_dir):
    fake = FakeApify(ANSWERS)
    res = activity.check(leads_db, write=False, today=TODAY, token="t", query=fake)
    assert {d["id"] for d in res["disqualified"]} == {"both-dead", "zero-posts"}
    assert all(r["disqualified"] in (None, "manual") for r in rows(leads_db).values())
    assert (data_dir / "social_cache" / "instagram.json").exists()


def test_write_disqualifies_only_when_every_social_channel_is_dead(leads_db, data_dir):
    activity.check(leads_db, write=True, today=TODAY, token="t", query=FakeApify(ANSWERS))
    r = rows(leads_db)
    assert r["both-dead"]["disqualified"].startswith("inactive: Instagram last post 2023-08-17")
    assert "Facebook last post 2023-08-17" in r["both-dead"]["disqualified"]
    assert r["zero-posts"]["disqualified"] == "inactive: Instagram no posts"
    # only one channel dead (the other alive): the lead stays, the channel is marked
    assert r["one-dead"]["disqualified"] is None
    assert r["one-dead"]["instagram_inactive"] == "last post 2023-08-17" and r["one-dead"]["facebook_inactive"] is None
    # dead channel plus an unknown one: not every channel is dead
    assert r["unknown-fb"]["disqualified"] is None and r["unknown-fb"]["instagram_inactive"]
    assert r["alive"]["disqualified"] is None and r["alive"]["instagram_inactive"] is None
    # contacted, already disqualified, no social channel: untouched
    assert r["contacted"]["disqualified"] is None and r["disq"]["disqualified"] == "manual"
    assert r["no-social"]["disqualified"] is None


def test_each_profile_is_paid_once(leads_db, data_dir):
    first = FakeApify(ANSWERS)
    activity.check(leads_db, write=True, today=TODAY, token="t", query=first)
    assert first.calls
    second = FakeApify(ANSWERS)
    activity.check(leads_db, write=True, today=TODAY, token="t", query=second)
    assert second.calls == []
    asked = {k for c, ks in first.calls for k in ks}
    assert "olddead" not in asked and "olddead2" not in asked          # contacted / disqualified are never asked


def test_touched_lead_is_left_alone(leads_db, data_dir):
    db = sqlite3.connect(leads_db)
    db.execute("INSERT INTO touches (lead_id, channel, kind, date, created_at) VALUES ('both-dead','instagram','sent','2026-11-01','x')")
    db.commit(); db.close()
    res = activity.check(leads_db, write=True, today=TODAY, token="t", query=FakeApify(ANSWERS))
    assert "both-dead" not in {d["id"] for d in res["disqualified"]}


def test_revived_channel_clears_mark(leads_db, data_dir):
    db = sqlite3.connect(leads_db)
    db.execute("UPDATE leads SET instagram_inactive='last post 2020-01-01' WHERE id='alive'"); db.commit(); db.close()
    activity.check(leads_db, write=True, today=TODAY, token="t", query=FakeApify(ANSWERS))
    assert rows(leads_db)["alive"]["instagram_inactive"] is None


def test_months_threshold_comes_from_config(leads_db, data_dir):
    answers = {"instagram": {"alive": {"posts": 50, "last_post": "2026-07-01"}}}
    res = activity.check(leads_db, write=False, today=TODAY, token="t", months=3, query=FakeApify(answers))
    assert "alive" in {d["id"] for d in res["disqualified"]}
    res = activity.check(leads_db, write=False, today=TODAY, token="t", months=6, query=FakeApify(answers))
    assert "alive" not in {d["id"] for d in res["disqualified"]}


def test_no_token_skips_cleanly(leads_db, data_dir, capsys, monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.setattr(_paths, "ENV_FILE", data_dir / "no.env")
    fake = FakeApify(ANSWERS)
    res = activity.check(leads_db, write=True, today=TODAY, token=None, query=fake)
    assert res["skipped_no_token"] and fake.calls == []
    assert "No APIFY_TOKEN" in capsys.readouterr().out


def test_free_limit_stops_gracefully(leads_db, data_dir, capsys):
    def limit(*a, **k):
        raise apify.ApifyLimit("HTTP 402")
    res = activity.check(leads_db, write=True, today=TODAY, token="t", query=limit)
    assert res["stopped_early"] and res["disqualified"] == []
    assert not (data_dir / "social_cache" / "instagram.json").exists()   # nothing recorded as asked
    assert "refused" in capsys.readouterr().out


def test_unfinished_run_does_not_record_missing_as_asked(leads_db, data_dir):
    activity.check(leads_db, write=True, today=TODAY, token="t",
                   query=FakeApify({"instagram": {"alive": {"posts": 5, "last_post": NEW}}}, finished=False))
    cache = json.loads((data_dir / "social_cache" / "instagram.json").read_text())
    assert set(cache) == {"alive"}


def test_estimate_makes_no_calls(leads_db, data_dir, capsys):
    fake = FakeApify(ANSWERS)
    res = activity.check(leads_db, estimate=True, today=TODAY, token="t", query=fake)
    assert fake.calls == [] and res["estimated_usd"] > 0


def test_run_actor_against_mock_transport():
    import httpx

    def handler(req: httpx.Request):
        if req.method == "POST":
            assert req.url.params["maxTotalChargeUsd"] == "0.5"
            return httpx.Response(201, json={"data": {"id": "r1", "status": "RUNNING"}})
        if "actor-runs" in req.url.path:
            return httpx.Response(200, json={"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1", "usageTotalUsd": 0.0123}})
        return httpx.Response(200, json=[{"username": "x"}])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    items, ok, cost = apify.run_actor("tok", apify.INSTAGRAM_ACTOR, {"usernames": ["x"]}, 0.5, client=client, poll_seconds=0)
    assert items == [{"username": "x"}] and ok and cost == 0.0123
    refuse = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(402)))
    with pytest.raises(apify.ApifyLimit):
        apify.run_actor("tok", apify.FACEBOOK_ACTOR, {}, 1, client=refuse)
