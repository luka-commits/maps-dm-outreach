#!/usr/bin/env python3
"""import_leads.py - enriched_raw.json into the local SQLite database, without touching hand-kept fields.

  python pipeline/import_leads.py data/runs/GB-roofer-west-yorkshire/enriched_raw.json --country GB

What an import does, per row:

  * drops what is not a lead: outside the country, permanently closed, not in the niche, a chain,
    below `import.min_reviews`, no website while `import.require_website` is on, and rows that have
    neither an Instagram nor a Facebook profile (nothing to send a DM to)
  * normalises the profile URLs (junk paths like /policy, /share, /p/<post> are not profiles)
  * town = the nearest town of the country's postcode grid; neighbour town = the nearest OTHER
    town at least 2 km away; region = county / state of the search cell
  * new place id: insert. Known place id: refresh the scraped fields only.

Hand-kept fields are never written on a re-import: linkedin, neighbour_town_manual, opener, notes,
contacted_on, disqualified, strategy, and the activity check's `<channel>_inactive`. An empty
channel in a new import never deletes an existing one. `imported_at`, `niche` and `run` keep the
values of the first import: a lead belongs to the run that found it first.

Database: env OUTREACH_DB, else <repo>/data/leads.db. The schema is app/lib/schema.sql.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import pathlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from pipeline import _paths  # noqa: E402
from pipeline.enrich.domains import CHAIN_THRESHOLD, chain_domains, domain_of  # noqa: E402
from pipeline.enrich.filter_niche import (allows_retail, is_generic_category,  # noqa: E402
                                          is_retail_category)
from pipeline.geo import foreign_country  # noqa: E402
from pipeline.scrape import niches  # noqa: E402
from pipeline.scrape.grid import load_grid  # noqa: E402

# Well-known chains; the domain rule (10+ rows on one own domain) catches the rest.
CHAIN_WORDS = ("timpson", "minit", "halfords", "kwik fit", "kwik-fit", "screwfix", "toolstation",
               "b&q", "home depot", "jiffy lube", "pep boys")

# Accounts of website builders, directories, review portals, platforms and trade bodies. They show
# up in website footers ("built with Wix", "find us on Checkatrade") and are never the business.
PLATFORM_HANDLES = {
    "wix", "wixcom", "squarespace", "godaddy", "wordpress", "wordpressdotcom", "wordpresscom",
    "shopify", "weebly", "jimdo", "webflow", "hostinger", "ionos", "strato", "duda", "elementor",
    "canva", "mailchimp", "vistaprint", "yell", "yelp", "checkatrade", "mybuilder", "ratedpeople",
    "trustatrader", "trustpilot", "bark", "houzz", "homeadvisor", "angi", "angieslist",
    "thumbtack", "nextdoor", "fixr", "freeindex", "thomsonlocal", "tripadvisor", "gumtree",
    "trustedtrader", "trustmark", "nfrc", "facebook", "instagram", "meta", "google", "googlemaps",
    "googlebusiness", "youtube", "twitter", "x", "tiktok", "linkedin", "pinterest", "whatsapp",
    "snapchat", "threads", "tiktokshop", "bing", "apple",
}
PLATFORM_MIN_DOMAINS = 3     # one handle on rows with this many different websites is a platform

INSTAGRAM_RESERVED = {"p", "reel", "reels", "stories", "explore", "accounts", "direct", "share", "tv"}
FACEBOOK_FOOTER = {"policy", "policy.php", "policies", "privacy", "legal", "help", "about", "ads",
                   "docs", "business", "terms"}
FACEBOOK_JUNK_PATH = {"share", "share.php", "sharer", "sharer.php", "l.php", "login.php", "home.php",
                      "posts", "photos", "photo", "photo.php", "videos", "watch", "reel", "reels",
                      "story.php", "permalink.php", "groups", "events", "dialog", "login", "plugins"}

POSTCODE_PATTERNS = {
    "GB": r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
    "IE": r"\b(?:[ACDEFHKNPRTVWXY]\d{2}|D6W)\s?[0-9ACDEFHKNPRTVWXY]{4}\b",
    "US": r"\b\d{5}(?:-\d{4})?\b",
    "CA": r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b",
    "AU": r"\b\d{4}\b",
    "DE": r"\b\d{5}\b",
}


def clean(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def profile(value, channel):
    """A normalised profile URL, or None for anything that is not a profile page."""
    value = clean(value)
    if not value:
        return None
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    try:
        url = urlsplit(value)
        if url.scheme.lower() not in ("http", "https") or url.username or url.password:
            return None
        host = (url.hostname or "").lower()
        path = [unquote(p) for p in url.path.split("/") if p]
        if channel == "instagram":
            if host not in ("instagram.com", "www.instagram.com", "m.instagram.com") or len(path) != 1:
                return None
            name = path[0]
            if name.lower() in INSTAGRAM_RESERVED or not re.fullmatch(r"[A-Za-z0-9._]{1,30}", name):
                return None
            if name.lower().strip("._") in PLATFORM_HANDLES:
                return None
            return f"https://www.instagram.com/{name.lower()}/"
        if host not in ("facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com") or not path:
            return None
        # Cookie-banner footer links (/policy/, /policy.php./) are not pages.
        if path[0].casefold().rstrip(".") in FACEBOOK_FOOTER:
            return None
        if path[0].lower().strip("._-") in PLATFORM_HANDLES:
            return None
        if path[0].lower() == "profile.php":
            ident = parse_qs(url.query).get("id", [""])[0]
            return f"https://www.facebook.com/profile.php?id={ident}" if ident.isdigit() else None
        if any(p.lower() in FACEBOOK_JUNK_PATH for p in path):
            return None
        if len(path) == 1 and re.fullmatch(r"[A-Za-z0-9.\-_]+", path[0]):
            return f"https://www.facebook.com/{path[0]}/"
        if len(path) == 3 and path[0].lower() in ("people", "pages") and path[2].isdigit():
            return f"https://www.facebook.com/{'/'.join(path)}/"
    except ValueError:
        return None
    return None


def first_valid(values, check):
    if not isinstance(values, list):
        return None
    return next((r for v in values if (r := check(v))), None)


def platform_profiles(rows) -> set[str]:
    """Profile URLs that turn up on rows with PLATFORM_MIN_DOMAINS or more different websites: a
    builder, agency or directory linked from many footers, not any one business's own account."""
    domains: dict[str, set[str]] = {}
    for row in rows:
        host = domain_of(row)
        if not host:
            continue
        for channel, key in (("instagram", "instagrams"), ("facebook", "facebooks")):
            for value in row.get(key) or []:
                url = profile(value, channel)
                if url:
                    domains.setdefault(url, set()).add(host)
    return {url for url, hosts in domains.items() if len(hosts) >= PLATFORM_MIN_DOMAINS}


def own_profile(values, channel, blocked):
    """First valid profile of a row's links that is not a platform account."""
    for value in values if isinstance(values, list) else []:
        url = profile(value, channel)
        if url and url not in blocked:
            return url
    return None


def number(value):
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except (ValueError, TypeError):
        return None


def distance_km(lat, lng, lat2, lng2):
    a, b = math.radians(lat), math.radians(lat2)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(lng2 - lng) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


class TownIndex:
    """Towns of a postcode grid, searchable by distance. Sorted by latitude so a lookup only looks
    at a band around the point (the US grid has 41,000 entries)."""

    BAND = 0.6  # degrees of latitude, ~65 km

    def __init__(self, grid: list[dict]):
        towns = []
        for e in grid:
            name, lat, lng = clean(e.get("ort")), number(e.get("lat")), number(e.get("lng"))
            if name and lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
                towns.append((lat, lng, name))
        towns.sort()
        self.towns = towns
        self.lats = [t[0] for t in towns]

    def _band(self, lat, width):
        lo, hi = bisect.bisect_left(self.lats, lat - width), bisect.bisect_right(self.lats, lat + width)
        return self.towns[lo:hi]

    def own(self, lat, lng):
        """Name of the nearest town of the grid."""
        for width in (self.BAND, 5.0, 200.0):
            best = min(((distance_km(lat, lng, t[0], t[1]), t[2]) for t in self._band(lat, width)), default=None)
            if best:
                return best[1]
        return None

    def neighbour(self, town, lat, lng):
        """Nearest town with another name, at least 2 km away."""
        own = (town or "").casefold()
        for width in (self.BAND, 5.0, 200.0):
            found = []
            for t_lat, t_lng, name in self._band(lat, width):
                low = name.casefold()
                # Not the town itself, nor a part of it ("Leeds" for "Leeds City") or a district of it
                # ("Castleford Central" for "Castleford").
                if low == own or own.startswith(low + " ") or low.startswith(own + " "):
                    continue
                km = distance_km(lat, lng, t_lat, t_lng)
                if km >= 2:
                    found.append((km, name))
            if found:
                return min(found)[1]
        return None


def postcode_of(address, country):
    pattern = POSTCODE_PATTERNS.get(country.upper())
    if not pattern or not address:
        return None
    matches = re.findall(pattern, address.upper() if country.upper() in ("GB", "IE", "CA") else address)
    return matches[-1].strip() if matches else None


COUNTRY_NAMES = {"united kingdom", "uk", "united states", "usa", "us", "canada", "australia",
                 "ireland", "germany", "deutschland", "england", "scotland", "wales", "northern ireland"}


def plausible_city(value):
    """Google's `city` when it looks like a place name: letters, no digits, not a country."""
    city = clean(value)
    if not city or len(city) > 40 or re.search(r"\d", city) or city.casefold() in COUNTRY_NAMES:
        return None
    return city if re.search(r"[^\W\d_]", city) else None


def locality_from_address(address):
    """The place name in front of the postcode: "53 Front St, Castleford WF10 4FQ, UK" -> Castleford.
    Used when Google gave no `city`. US-style "Springfield, TX 78701" reads the segment before."""
    segments = [s.strip() for s in (address or "").split(",") if s.strip()]
    while segments and segments[-1].casefold() in COUNTRY_NAMES:
        segments.pop()
    if not segments or not any(re.search(r"\d", w) for w in segments[-1].split()):
        return None                                  # no postcode segment: nothing to anchor on
    words = [w for w in segments[-1].split() if not re.search(r"\d", w)]
    if len(words) > 1 and words[-1].isupper() and len(words[-1]) <= 3:
        words = words[:-1]                           # trailing state / province code
    if words and not (len(words) == 1 and words[0].isupper() and len(words[0]) <= 3):
        return " ".join(words)
    if len(segments) > 1 and not re.search(r"\d", segments[-2]):
        return segments[-2]
    return None


def niche_match(row, terms, exclusions=()):
    """Is this place in the niche?

    * the primary category or name must not hit an exclusion
    * retail / wholesale / manufacturing categories ("Roofing supply store") are not the trade,
      unless the keyword itself names such a thing (--terms "mattress store")
    * any category (also secondary ones) containing a niche term is a match
    * the NAME alone only counts when the primary category is missing or generic ("Roofing
      contractor" is a match anyway; "Joiner" named "Smart Roofing & Joinery" is a joiner)."""
    cats = [clean(c) or "" for c in [row.get("categoryName"), *(row.get("categories") or [])]]
    title = (clean(row.get("title")) or "").casefold()
    primary = (cats[0] if cats else "").casefold()
    if any(x in primary or x in title for x in exclusions):
        return False
    if is_retail_category(primary) and not allows_retail(terms):
        return False
    if any(t.lower() in c.casefold() for t in terms for c in cats if c):
        return True
    return (not primary or is_generic_category(primary)) and any(t.lower() in title for t in terms)


def exclusion_reason(row, spec, config, country, chains):
    if foreign_country((row.get("location") or {}).get("lat"), (row.get("location") or {}).get("lng"),
                       row.get("website"), country):
        return "outside country"
    if "permanently" in (clean(row.get("businessStatus")) or "").lower().replace("_", " "):
        return "closed"
    if not niche_match(row, spec["terms"], spec.get("exclusions", ())):
        return "not niche"
    title = (clean(row.get("title")) or "").casefold()
    chain_words = [*CHAIN_WORDS, *(w.lower() for w in config.get("import", {}).get("chain_words", []))]
    if any(w in title for w in chain_words) or (domain_of(row) and domain_of(row) in chains):
        return "chain"
    reviews = number(row.get("reviewsCount"))
    imp = config.get("import", {})
    if (imp.get("require_website", True) and not clean(row.get("website"))) or (
            reviews is not None and reviews < imp.get("min_reviews", 5)):
        return "too small"
    return None


def lead_fields(row, run, spec, country, index, blocked=frozenset()):
    ident = row.get("placeId") or row.get("place_id") or row.get("cid")
    name = clean(row.get("title"))
    if not ident or not name:
        raise ValueError("Every row needs placeId/place_id/cid and title.")
    address = clean(row.get("address"))
    loc = row.get("location") if isinstance(row.get("location"), dict) else {}
    lat, lng = number(loc.get("lat")), number(loc.get("lng"))
    located = lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180
    # Google's own place name first (it is what the owner would say), then the locality in the
    # address, and only then the nearest postcode centroid, which can name a hamlet next door.
    town = (plausible_city(row.get("city")) or locality_from_address(address)
            or (index.own(lat, lng) if located else None) or clean(row.get("_ort")))
    reviews = number(row.get("reviewsCount"))
    return {
        "id": str(ident), "name": name, "category": clean(row.get("categoryName")),
        "address": address, "postcode": postcode_of(address, country) or clean(row.get("_cell")),
        "town": town, "region": clean(row.get("_region")) or clean(row.get("state")),
        "country": country.upper(), "lat": lat, "lng": lng, "phone": clean(row.get("phone")),
        "website": clean(row.get("website")), "rating": number(row.get("totalScore")),
        "reviews": int(reviews) if reviews is not None else None,
        "instagram": own_profile(row.get("instagrams"), "instagram", blocked),
        "facebook": own_profile(row.get("facebooks"), "facebook", blocked),
        "neighbour_town": index.neighbour(town, lat, lng) if located else None,
        "owner_name": clean(row.get("ownerName")),
        "niche": spec["slug"], "run": run,
    }


# Refreshed on re-import. Everything else in `leads` is hand-kept or owned by another step.
REFRESH = ("name", "category", "address", "postcode", "town", "region", "country", "lat", "lng",
           "phone", "website", "rating", "reviews", "instagram", "facebook",
           "neighbour_town", "owner_name")
# A new import must never blank these.
KEEP_IF_EMPTY = ("instagram", "facebook")   # owner_name is derived, so it is refreshed (and may clear)


def import_rows(rows, run, spec, country, db_file=None, config=None):
    config = config if config is not None else _paths.load_config()
    index = TownIndex(load_grid(country))
    chains = chain_domains(rows)
    blocked = platform_profiles(rows)
    summary = {"read": len(rows), "imported": 0, "new": 0, "updated": 0, "with_instagram": 0, "with_facebook": 0,
               "with_dm_channel": 0, "outside country": 0, "closed": 0, "not niche": 0, "chain": 0,
               "too small": 0, "no channel": 0}
    summary["removed"] = 0
    leads, rejected = [], []
    for row in rows:
        ident = row.get("placeId") or row.get("place_id") or row.get("cid")
        reason = exclusion_reason(row, spec, config, country, chains)
        if reason:
            summary[reason] += 1
            rejected.append((str(ident), reason))
            continue
        lead = lead_fields(row, run, spec, country, index, blocked)
        if not (lead["instagram"] or lead["facebook"]):
            summary["no channel"] += 1
            rejected.append((str(ident), "no channel"))
            continue
        leads.append(lead)
    summary["imported"] = len(leads)

    target = pathlib.Path(db_file or _paths.db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(_paths.SCHEMA.read_text(encoding="utf-8"))
        for lead in leads:
            existing = db.execute("SELECT * FROM leads WHERE id = ?", (lead["id"],)).fetchone()
            if existing is None:
                new = {**lead, "imported_at": datetime.now(timezone.utc).isoformat()}
                db.execute(f"INSERT INTO leads ({', '.join(new)}) VALUES ({', '.join('?' for _ in new)})",
                           list(new.values()))
                summary["new"] += 1
            else:
                values = {f: lead[f] for f in REFRESH}
                for f in KEEP_IF_EMPTY:
                    # An older import may have stored a platform account (a website builder's
                    # footer link): that one is not kept.
                    old = profile(existing[f], f) if existing[f] else None
                    if values[f] is None and old and old not in blocked:
                        values[f] = existing[f]
                changed = {f: v for f, v in values.items() if existing[f] != v}
                sets = dict(changed)
                # A changed profile URL makes the old "this channel is dead" verdict stale.
                for channel in ("instagram", "facebook"):
                    if channel in changed:
                        sets[f"{channel}_inactive"] = None
                if sets:
                    db.execute(f"UPDATE leads SET {', '.join(f'{f} = ?' for f in sets)} WHERE id = ?",
                               [*sets.values(), lead["id"]])
                    summary["updated"] += 1
            summary["with_instagram"] += int(bool(lead["instagram"]))
            summary["with_facebook"] += int(bool(lead["facebook"]))
            summary["with_dm_channel"] += 1
        # Rows of THIS file that an earlier import accepted but today's rules reject (a supply store,
        # a platform handle that was its only channel) are removed again, but only while nothing was
        # done with them: no touches, no batch, nothing typed in by hand.
        for ident, reason in rejected:
            if reason == "no channel":
                # Transient failures (a website that was down) must not delete a lead that has a
                # real channel from an earlier import: only platform-only leftovers go.
                old = db.execute("SELECT instagram, facebook FROM leads WHERE id = ?", (ident,)).fetchone()
                if old and any(profile(old[c], c) and profile(old[c], c) not in blocked
                               for c in ("instagram", "facebook") if old[c]):
                    continue
            cur = db.execute(
                "DELETE FROM leads WHERE id = ? AND contacted_on IS NULL AND disqualified IS NULL "
                "AND COALESCE(linkedin, '') = '' AND COALESCE(opener, '') = '' AND COALESCE(notes, '') = '' "
                "AND COALESCE(neighbour_town_manual, '') = '' "
                "AND id NOT IN (SELECT lead_id FROM touches) AND id NOT IN (SELECT lead_id FROM batches)",
                (ident,))
            summary["removed"] += cur.rowcount
        db.commit()
    finally:
        db.close()
    return summary


def import_file(path, country, niche=None, run=None, db_file=None, config=None):
    path = pathlib.Path(path).resolve()
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("The import file must contain a JSON list of objects.")
    spec_file = path.parent / "niche.json"
    if niche:
        spec = niches.resolve(niche)
    elif spec_file.is_file():
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    else:
        raise ValueError("--niche is required (no niche.json next to the file).")
    return import_rows(rows, run or path.parent.name, spec, country.upper(), db_file, config)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=pathlib.Path)
    ap.add_argument("--country", required=True)
    ap.add_argument("--niche", help="keyword or preset; default: niche.json next to the file")
    ap.add_argument("--run", help="run name; default: the folder name")
    ap.add_argument("--db", type=pathlib.Path)
    a = ap.parse_args(argv)
    try:
        result = import_file(a.file, a.country, a.niche, a.run, a.db)
    except (ValueError, OSError, sqlite3.Error, KeyError) as error:
        ap.exit(1, f"Import failed: {error}\n")
    print(" | ".join(f"{k}: {v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
