#!/usr/bin/env python3
"""instagram_posts.py - profile, recent posts and images of today's batch, for writing openers.

  python pipeline/social/instagram_posts.py --list          # who needs an opener, no calls
  python pipeline/social/instagram_posts.py                 # fetch for today's batch
  python pipeline/social/instagram_posts.py --ids ID1,ID2   # fetch for specific lead ids

Today's batch = rows of `batches` for today (configured timezone) whose lead has an Instagram
profile, a strategy with `needs_opener: true` (strategies/strategies.json) and an empty opener.

One call of apify/instagram-profile-scraper returns the profile AND the latest posts, billed per
profile (about $0.003), not per post. Output in data/openers/<YYYY-MM-DD>/:

  profiles.json   [{id, name, town, handle, usable, reason, followers, posts_count, bio, category,
                    verified, last_post, posts: [{n, date, type, caption, likes, url, image}]}]
  profiles.raw.json   Apify's unchanged answer (a rerun reuses it instead of paying again)
  images/<handle>__NN.jpg   up to 6 images per account, downloaded immediately: Instagram CDN
                            links are signed and expire within hours

`usable: false` carries a `reason` (private, too few posts, too few or too many followers, last post
too old, account name does not match the business). The dm-opener skill skips those leads.
Needs APIFY_TOKEN in .env or the environment; without it the step says so and exits 0.
Never log into Instagram with your own account for this: your DMs go out from that account.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline import _paths  # noqa: E402
from pipeline.social import apify  # noqa: E402

MIN_POSTS = 5               # fewer is an account that was set up and never used
MIN_FOLLOWERS = 50
MAX_FOLLOWERS = 50_000      # above this it is a portal or a chain that slipped in via a footer link
MAX_POST_AGE_DAYS = 180     # an opener must not comment on a year-old post as if just seen
IMAGES_PER_ACCOUNT = 6      # enough to have a choice, not enough to build a business portrait
FILLER = {"ltd", "limited", "the", "and", "uk", "co", "services", "service", "solutions", "group",
          "plc", "company", "your", "local", "inc", "llc"}


def belongs_to_business(business: str, handle: str) -> bool:
    """Does the account carry the business's name? A footer often links a directory or partner
    next to the own account, and no follower filter catches that. Each distinctive word of the
    name is tested as a substring of the squeezed handle ("doorandwindowmedic")."""
    squeezed = re.sub(r"[^a-z0-9]", "", handle.lower())
    words = [w for w in re.split(r"[^a-z0-9]+", (business or "").lower()) if len(w) > 3 and w not in FILLER]
    return any(w in squeezed for w in words)


def last_post(profile: dict) -> str | None:
    stamps = [p.get("timestamp") for p in (profile.get("latestPosts") or []) if p.get("timestamp")]
    return max(stamps) if stamps else None


def verdict(profile: dict, business: str = "", now: datetime | None = None) -> str | None:
    """First reason this account is not usable for an opener, None if it is."""
    now = now or datetime.now(timezone.utc)
    if profile.get("error") or not profile.get("username"):
        return "no profile"
    if business and not belongs_to_business(business, profile["username"]):
        return "account name does not match the business"
    if profile.get("private"):
        return "private"
    if (profile.get("postsCount") or 0) < MIN_POSTS:
        return f"fewer than {MIN_POSTS} posts"
    followers = profile.get("followersCount") or 0
    if followers < MIN_FOLLOWERS:
        return f"fewer than {MIN_FOLLOWERS} followers"
    if followers > MAX_FOLLOWERS:
        return f"more than {MAX_FOLLOWERS} followers (portal or chain)"
    latest = last_post(profile)
    if not latest:
        return "no dated post"
    if latest < (now - timedelta(days=MAX_POST_AGE_DAYS)).isoformat():
        return f"last post {latest[:10]}"
    return None


def handle_of(url: str | None) -> str | None:
    m = re.match(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9._]+)", url or "")
    return m.group(1).lower() if m else None


def today_iso(config: dict) -> str:
    try:
        return datetime.now(ZoneInfo(config.get("timezone") or "UTC")).date().isoformat()
    except Exception:  # noqa: BLE001 - unknown timezone name: fall back to UTC
        return datetime.now(timezone.utc).date().isoformat()


def needs_opener_ids() -> set[str]:
    data = json.loads(_paths.STRATEGIES.read_text(encoding="utf-8"))
    return {s["id"] for s in data.get("strategies", []) if s.get("needs_opener")}


def leads_needing_opener(db: sqlite3.Connection, date_iso: str, ids: list[str] | None = None) -> list[dict]:
    """Batch leads (or the given ids) with an Instagram profile and an empty opener whose strategy needs one."""
    strategies = needs_opener_ids()
    if ids:
        marks = ",".join("?" for _ in ids)
        rows = db.execute(f"SELECT * FROM leads WHERE id IN ({marks})", ids).fetchall()
    else:
        rows = db.execute("SELECT l.* FROM batches b JOIN leads l ON l.id = b.lead_id "
                          "WHERE b.date = ? ORDER BY b.position", (date_iso,)).fetchall()
    out = []
    for r in rows:
        if r["instagram"] and not (r["opener"] or "").strip() and (ids or r["strategy"] in strategies):
            out.append(dict(r))
    return out


def _display_path(path: pathlib.Path) -> str:
    """Relative to the repo root when inside it (portable), else as given."""
    try:
        return str(path.relative_to(_paths.ROOT))
    except ValueError:
        return str(path)


def download(url: str, target: pathlib.Path, client: httpx.Client) -> bool:
    if target.is_file():
        return True
    if not url:
        return False
    try:
        resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        target.write_bytes(resp.content)
        return True
    except Exception:  # noqa: BLE001 - a missing image is not worth stopping for
        return False


def fetch(leads: list[dict], out_dir: pathlib.Path, token: str, *, cap: float = 2.0,
          run_actor=apify.run_actor, client: httpx.Client | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    images = out_dir / "images"
    images.mkdir(exist_ok=True)
    raw_file = out_dir / "profiles.raw.json"
    by_handle = {handle_of(l["instagram"]): l for l in leads if handle_of(l["instagram"])}
    cost = 0.0
    raw: list[dict] = json.loads(raw_file.read_text(encoding="utf-8")) if raw_file.is_file() else []
    have = {(p.get("username") or "").lower() for p in raw}
    missing = sorted(set(by_handle) - have)
    if missing:
        items, _ok, cost = run_actor(token, apify.INSTAGRAM_ACTOR, {"usernames": missing}, cap)
        raw += items
        raw_file.write_text(json.dumps(raw, indent=1, ensure_ascii=False), encoding="utf-8")
    profiles = {(p.get("username") or "").lower(): p for p in raw}
    http = client or httpx.Client(timeout=60, follow_redirects=True)
    out = []
    try:
        for handle, lead in by_handle.items():
            p = profiles.get(handle)
            if not p:
                out.append({"id": lead["id"], "name": lead["name"], "town": lead.get("town"),
                            "handle": handle, "usable": False, "reason": "not found", "posts": []})
                continue
            reason = verdict(p, lead["name"])
            posts = []
            for n, post in enumerate((p.get("latestPosts") or [])[:IMAGES_PER_ACCOUNT]):
                target = images / f"{handle}__{n:02d}.jpg"
                ok = download(post.get("displayUrl") or "", target, http)
                posts.append({"n": n, "date": post.get("timestamp"), "type": post.get("type"),
                              "caption": post.get("caption") or "", "likes": post.get("likesCount"),
                              "url": post.get("url"),
                              "image": (_display_path(target) if ok else None)})
            out.append({"id": lead["id"], "name": lead["name"], "town": lead.get("town"),
                        "handle": handle, "usable": reason is None, "reason": reason,
                        "followers": p.get("followersCount"), "posts_count": p.get("postsCount"),
                        "bio": p.get("biography"), "category": p.get("businessCategoryName"),
                        "verified": p.get("verified"), "last_post": last_post(p), "posts": posts})
    finally:
        if client is None:
            http.close()
    (out_dir / "profiles.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"profiles": len(out), "usable": sum(1 for x in out if x["usable"]),
            "fetched": len(missing), "cost_usd": cost,
            "estimated_usd": len(missing) * apify.PRICE_INSTAGRAM_PROFILE}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="only list who needs an opener")
    ap.add_argument("--ids", help="comma-separated lead ids instead of today's batch")
    ap.add_argument("--date", help="batch date YYYY-MM-DD (default: today in the configured timezone)")
    ap.add_argument("--cap", type=float, default=2.0, help="max USD for the Apify run (default 2.0)")
    ap.add_argument("--db", type=pathlib.Path)
    a = ap.parse_args(argv)
    config = _paths.load_config()
    day = a.date or today_iso(config)
    db_file = a.db or _paths.db_path()
    if not pathlib.Path(db_file).is_file():
        print(f"No database at {db_file} yet. Run run.py first.")
        return 0
    db = sqlite3.connect(db_file)
    db.row_factory = sqlite3.Row
    try:
        ids = [i.strip() for i in a.ids.split(",") if i.strip()] if a.ids else None
        leads = leads_needing_opener(db, day, ids)
    finally:
        db.close()
    print(f"{len(leads)} leads need an opener ({'ids given' if ids else 'batch of ' + day}).")
    for lead in leads:
        print(f"  {lead['id']}  {lead['name']}  {lead['instagram']}")
    if a.list or not leads:
        return 0
    token = _paths.apify_token()
    if not token:
        print("No APIFY_TOKEN (.env or environment): cannot fetch Instagram posts. "
              "Add the token, or write the openers from the profiles by hand.")
        return 0
    try:
        result = fetch(leads, _paths.DATA / "openers" / day, token, cap=a.cap)
    except apify.ApifyLimit as limit:
        print(f"Apify refused the run ({limit}): free credit used up? Nothing fetched.")
        return 0
    print(f"{result['profiles']} profiles, {result['usable']} usable. "
          f"Cost ${result['cost_usd']:.4f} for {result['fetched']} fetched profiles "
          f"(estimate ${result['estimated_usd']:.4f}).")
    print(f"-> {_paths.DATA / 'openers' / day / 'profiles.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
