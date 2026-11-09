"""Website domains: who shares a host, who is a chain, who has no real site."""
from __future__ import annotations

import collections
import re
from urllib.parse import urlparse

# 10 or more rows on one own domain = a chain. Measured on ~7,000 locksmith places: 91% of domains
# have exactly one location and three domains carry a third of all rows; any threshold between 10
# and 25 hits the same brands, and 10 is the safe one because it never catches a tradesperson with
# three vans. Missing a chain costs one DM, throwing away a growing local firm costs a customer.
CHAIN_THRESHOLD = 10

# Hosts that many businesses share: the path identifies the business there, not the host.
SHARED_HOST = ("facebook.com", "instagram.com", "linktr.ee", "wa.me", "t.me", "yelp.", "nextdoor.",
               "checkatrade.com", "yell.com", "trustpilot.", "linkedin.com", "twitter.com", "x.com",
               "sites.google.com")

# Website-builder subdomains: the business has its own subdomain but no own domain of its own.
BUILDER_HOST = ("wixsite.com", "business.site", "godaddysites.com", "weebly.com", "squarespace.com",
                "jimdosite.com", "webnode.")


def domain_of(place: dict) -> str:
    website = (place.get("website") or "").strip()
    if not website:
        return ""
    if "://" not in website:
        website = "https://" + website
    try:
        host = (urlparse(website).hostname or "").lower()
    except ValueError:
        return ""
    return re.sub(r"^(www|m)\.", "", host)


def is_shared_host(host: str) -> bool:
    return any(s in host for s in SHARED_HOST)


def is_builder(host: str) -> bool:
    return any(s in host for s in BUILDER_HOST)


def chain_domains(rows: list[dict], threshold: int = CHAIN_THRESHOLD) -> set[str]:
    """Own domains that `threshold` or more rows share (platforms and site builders excluded)."""
    counts: collections.Counter = collections.Counter()
    for row in rows:
        host = domain_of(row)
        if host and not is_shared_host(host) and not is_builder(host):
            counts[host] += 1
    return {host for host, n in counts.items() if n >= threshold}
