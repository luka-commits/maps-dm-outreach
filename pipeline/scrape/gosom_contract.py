"""Normalise gosom/google-maps-scraper output into the row shape the rest of the pipeline reads.

Output row (`to_apify_shape`): placeId, title, categoryName, categories, address, city, state,
countryCode, location {lat,lng}, website, phone, totalScore, reviewsCount, businessStatus, url,
emails[], instagrams[], facebooks[]. The names are the ones Apify's Google Maps actors use, so a
file from either source can be fed into the later steps.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

SCRAPER_VERSION = "1.17.4"


def parse_gosom_output(text: str) -> list[dict[str, Any]]:
    """Accept the scraper's JSON-lines format and a JSON array."""
    stripped = text.strip()
    if not stripped:
        return []
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            decoded = [json.loads(line) for line in stripped.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid gosom JSON output: {error}") from error
    rows = decoded if isinstance(decoded, list) else [decoded]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("gosom output must contain JSON objects")
    return rows


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _clean_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
    return out


def to_apify_shape(row: dict[str, Any], fetched_at: str, *, query: str | None = None) -> dict[str, Any]:
    """Map one gosom entry to the pipeline's row shape."""
    address = row.get("complete_address") if isinstance(row.get("complete_address"), dict) else {}
    place_id = _text(row.get("place_id"))
    cid = _text(row.get("cid"))
    data_id = _text(row.get("data_id"))
    stable_id = place_id or (f"cid:{cid}" if cid else None) or (f"data:{data_id}" if data_id else None)
    longitude = _number(row.get("longitude"))
    if longitude is None:
        longitude = _number(row.get("longtitude"))  # sic: older gosom versions misspell the key
    category = _text(row.get("category"))
    categories = row.get("categories")
    if not isinstance(categories, list):
        categories = [category] if category else []
    return {
        "placeId": stable_id,
        "title": _text(row.get("title")),
        "categoryName": category,
        "categories": [c for c in categories if isinstance(c, str) and c],
        "address": _text(row.get("address")),
        "city": _text(address.get("city")),
        "state": _text(address.get("state")),
        "countryCode": _text(address.get("country")),
        "location": {"lat": _number(row.get("latitude")), "lng": longitude},
        "website": _text(row.get("web_site")) or _text(row.get("website")),
        "phone": _text(row.get("phone")),
        "totalScore": _number(row.get("review_rating")),
        "reviewsCount": _integer(row.get("review_count")),
        "businessStatus": _text(row.get("status")),
        "url": _text(row.get("link")),
        "emails": _clean_strings(row.get("emails")),
        "instagrams": [],
        "facebooks": [],
        "_source": {"provider": "gosom-google-maps-scraper", "version": SCRAPER_VERSION,
                    "fetchedAt": fetched_at, "query": query},
    }


def _domain(value: Any) -> str | None:
    website = _text(value)
    if not website:
        return None
    try:
        host = (urlsplit(website if "://" in website else f"https://{website}").hostname or "").lower()
    except ValueError:
        return None
    return (host[4:] if host.startswith("www.") else host) or None


def _phone(value: Any) -> str | None:
    digits = re.sub(r"\D", "", value) if isinstance(value, str) else ""
    return digits[-10:] if len(digits) >= 10 else digits or None


def identity_key(row: dict[str, Any]) -> str | None:
    """place id, else website domain, else phone, else name + address. None = no identity."""
    place_id = _text(row.get("placeId"))
    if place_id:
        return f"place:{place_id}"
    domain = _domain(row.get("website"))
    if domain:
        return f"domain:{domain}"
    phone = _phone(row.get("phone"))
    if phone:
        return f"phone:{phone}"
    title = (_text(row.get("title")) or "").casefold()
    address = (_text(row.get("address")) or "").casefold()
    return f"name-address:{title}|{address}" if title and address else None


def field_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    total = len(rows)

    def summarize(count: int) -> dict[str, float | int]:
        return {"count": count, "rate": round(count / total, 4) if total else 0.0}

    located = sum(isinstance(r.get("location"), dict) and r["location"].get("lat") is not None
                  and r["location"].get("lng") is not None for r in rows)
    return {
        "website": summarize(sum(bool(r.get("website")) for r in rows)),
        "phone": summarize(sum(bool(r.get("phone")) for r in rows)),
        "location": summarize(located),
    }
