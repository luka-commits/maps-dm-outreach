#!/usr/bin/env python3
"""activity.py - are the Instagram and Facebook accounts of open leads still alive?

  python pipeline/social/activity.py --estimate      # count profiles and estimate the cost, no calls
  python pipeline/social/activity.py                 # ask Apify, show who WOULD be marked, change nothing
  python pipeline/social/activity.py --write         # apply

Open = not contacted (no `contacted_on`, no touches) and not disqualified. Instagram is checked
with apify/instagram-profile-scraper (about $0.003 per profile), Facebook with
apify/facebook-posts-scraper and the newest post of each page (about $0.005 per page).

A channel is DEAD when it has 0 posts or its last post is older than `activity_check.
inactive_after_months` (config, default 6). Without data (private profile, deleted page, no
dated post) a channel stays UNKNOWN: never counted as dead.

  * every social channel of a lead is dead  -> `disqualified = "inactive: <reasons>"`
  * only some channels are dead              -> only `<channel>_inactive` is set (the app greys it out)
  * a dead channel that came back to life    -> its `_inactive` mark is cleared
  * leads already contacted or already disqualified are never touched

Each profile is paid ONCE: answers are cached in data/social_cache/<channel>.json, including
"no data" answers (a second call re-asking the same deleted pages is how a free limit is burnt).
A run that stops at the Apify limit records nothing for the rest; they are asked next time.
Without APIFY_TOKEN the step prints a skip message and exits 0. Token: .env or environment.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline import _paths  # noqa: E402
from pipeline.social import apify  # noqa: E402

CHANNELS = ("instagram", "facebook")
LABEL = {"instagram": "Instagram", "facebook": "Facebook"}
PRICE = {"instagram": apify.PRICE_INSTAGRAM_PROFILE, "facebook": apify.PRICE_FACEBOOK_PAGE}


def cache_file(channel: str) -> pathlib.Path:
    return _paths.DATA / "social_cache" / f"{channel}.json"


def cache_key(channel: str, url: str | None) -> str | None:
    """Instagram: the handle. Facebook: the URL, lowercase, no trailing slash."""
    if channel == "instagram":
        m = re.match(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)", url or "")
        return m.group(1).lower() if m else None
    return (url or "").strip().lower().rstrip("/") or None


def open_leads(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT * FROM leads WHERE disqualified IS NULL AND contacted_on IS NULL "
        "AND id NOT IN (SELECT lead_id FROM touches)").fetchall()


def query_apify(channel: str, keys: list[str], urls: dict[str, str], token: str, cap: float,
                today: str) -> tuple[dict, bool, float]:
    """Ask Apify about `keys`. -> (new cache entries, finished, cost). Raises ApifyLimit."""
    found: dict[str, dict] = {}
    if channel == "instagram":
        items, finished, cost = apify.run_actor(token, apify.INSTAGRAM_ACTOR, {"usernames": keys}, cap)
        for item in items:
            name = (item.get("username") or "").lower()
            if name:
                stamps = [p["timestamp"][:10] for p in item.get("latestPosts") or [] if p.get("timestamp")]
                found[name] = {"posts": item.get("postsCount"), "last_post": max(stamps) if stamps else None,
                               "private": bool(item.get("private")), "checked": today}
    else:
        actor_input = {"startUrls": [{"url": urls[k]} for k in keys], "resultsLimit": 1}
        items, finished, cost = apify.run_actor(token, apify.FACEBOOK_ACTOR, actor_input, cap)
        for item in items:
            key = cache_key("facebook", item.get("inputUrl") or item.get("url"))
            if key not in urls:
                continue
            if item.get("error"):
                found[key] = {"last_post": None, "error": str(item["error"]), "checked": today}
            elif item.get("time"):
                found[key] = {"last_post": str(item["time"])[:10], "checked": today}
    if finished:
        # Pages Apify does not return (deleted, renamed, no posts) are recorded as "no data" so
        # they are not paid for again. A run that stopped early records nothing for the rest.
        for k in keys:
            found.setdefault(k, {"last_post": None, "error": "no_data", "checked": today})
    return found, finished, cost


def channel_state(channel: str, entry: dict | None, cutoff: str):
    """-> ("alive" | "dead" | "unknown", reason or None)"""
    if not entry:
        return "unknown", None
    if channel == "instagram" and entry.get("posts") == 0:
        return "dead", "no posts"
    if not entry.get("last_post"):
        return "unknown", None
    if entry["last_post"] < cutoff:
        return "dead", f"last post {entry['last_post']}"
    return "alive", None


def check(db_file=None, *, write=False, only=None, cap=1.0, estimate=False, max_profiles=0,
          months=None, today=None, token=None, query=query_apify) -> dict:
    """The whole step. `query` can be replaced in tests; nothing else here touches the network."""
    config = _paths.load_config()
    months = months if months is not None else config.get("activity_check", {}).get("inactive_after_months", 6)
    today_d = today or date.today()
    cutoff = (today_d - timedelta(days=round(months * 30.44))).isoformat()
    token = token if token is not None else _paths.apify_token()
    result = {"checked": 0, "cost_usd": 0.0, "estimated_usd": 0.0, "stopped_early": False,
              "skipped_no_token": False, "disqualified": [], "channel_marks": [], "revived": []}

    db = sqlite3.connect(db_file or _paths.db_path())
    db.row_factory = sqlite3.Row
    try:
        db.executescript(_paths.SCHEMA.read_text(encoding="utf-8"))
        leads = open_leads(db)
        caches, wanted = {}, {}
        for channel in CHANNELS:
            path = cache_file(channel)
            caches[channel] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            urls: dict[str, str] = {}
            for lead in leads:
                key = cache_key(channel, lead[channel])
                if key:
                    urls.setdefault(key, lead[channel])
            todo = sorted(urls.keys() - caches[channel].keys())
            if max_profiles:
                todo = todo[:max_profiles]
            wanted[channel] = (urls, todo)
            print(f"{LABEL[channel]}: {len(urls)} open profiles, {len(todo)} not asked yet "
                  f"(about ${len(todo) * PRICE[channel]:.2f})")
            result["estimated_usd"] += len(todo) * PRICE[channel]

        if estimate:
            return result
        if any(todo for _, todo in wanted.values()) and not token:
            result["skipped_no_token"] = True
            print("No APIFY_TOKEN (.env or environment): skipping the activity check. "
                  "Nothing is lost, run it later with the token set.")
            return result

        for channel in only or CHANNELS:
            urls, todo = wanted[channel]
            if not todo:
                continue
            try:
                new, finished, cost = query(channel, todo, urls, token, cap, today_d.isoformat())
            except apify.ApifyLimit as limit:
                print(f"  Apify refused ({limit}), free credit used up? Continuing with cached answers; "
                      f"the rest is asked next time.")
                result["stopped_early"] = True
                continue
            caches[channel].update(new)
            result["checked"] += len(new)
            result["cost_usd"] += cost
            print(f"  {LABEL[channel]}: {len(new)} answers, cost ${cost:.4f}"
                  + ("" if finished else "  (stopped early: cap or limit, the rest is asked next time)"))
            if not finished:
                result["stopped_early"] = True
            path = cache_file(channel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(caches[channel], indent=1, ensure_ascii=False, sort_keys=True),
                            encoding="utf-8")

        for lead in leads:
            states = {c: channel_state(c, caches[c].get(cache_key(c, lead[c])), cutoff)
                      for c in CHANNELS if lead[c]}
            for channel, (state, _) in states.items():
                if state == "alive" and lead[f"{channel}_inactive"]:
                    result["revived"].append((lead["id"], channel))
            dead = {c: r for c, (s, r) in states.items() if s == "dead"}
            if not dead:
                continue
            if all(s == "dead" for s, _ in states.values()):
                reason = "inactive: " + ", ".join(f"{LABEL[c]} {r}" for c, r in dead.items())
                result["disqualified"].append({"id": lead["id"], "name": lead["name"], "reason": reason})
            else:
                result["channel_marks"] += [(lead["id"], c, r) for c, r in dead.items()]
        print(f"{len(result['disqualified'])} leads would be disqualified (no post since {cutoff} on "
              f"any social channel), {len(result['channel_marks'])} dead channels on leads with another channel")
        for item in result["disqualified"][:5]:
            print(f"    {item['name']}: {item['reason']}")
        print(f"Apify cost this run: ${result['cost_usd']:.4f}")

        if write:
            for lead_id, channel in result["revived"]:
                db.execute(f"UPDATE leads SET {channel}_inactive = NULL WHERE id = ?", (lead_id,))
            for lead_id, channel, reason in result["channel_marks"]:
                db.execute(f"UPDATE leads SET {channel}_inactive = ? WHERE id = ?", (reason, lead_id))
            for item in result["disqualified"]:
                db.execute("UPDATE leads SET disqualified = ? WHERE id = ? AND disqualified IS NULL",
                           (item["reason"], item["id"]))
            db.commit()
            print(f"Written: {len(result['disqualified'])} disqualified, {len(result['channel_marks'])} channel marks.")
        else:
            print("Dry run, nothing written. Apply with --write (the answers are cached, no second charge).")
    finally:
        db.close()
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="apply the result to the database")
    ap.add_argument("--estimate", action="store_true", help="count profiles and estimate the cost, no calls")
    ap.add_argument("--channel", choices=CHANNELS, action="append", help="default: both")
    ap.add_argument("--cap", type=float, default=1.0, help="max USD per channel and run (default 1.0)")
    ap.add_argument("--max-profiles", type=int, default=0, help="ask at most N new profiles per channel")
    ap.add_argument("--db", type=pathlib.Path)
    a = ap.parse_args(argv)
    config = _paths.load_config()
    if not config.get("activity_check", {}).get("enabled", True):
        print("activity_check.enabled is false in outreach.config.json: skipped.")
        return 0
    check(a.db, write=a.write, only=a.channel, cap=a.cap, estimate=a.estimate, max_profiles=a.max_profiles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
