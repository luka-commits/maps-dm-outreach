"""filter_niche.py - is this Google Maps place in the niche? Decided on Maps metadata only.

Matching is on the PRIMARY category (`categoryName`) and the name, not on the whole category list:
a hardware store with "Locksmith" as a secondary category is a hardware store.

  keep    the name contains a niche term, or the primary category is the niche and no foreign trade
          contradicts it
  verify  the primary category is the niche but another trade is also present and the name does not
          confirm it, OR the category is empty, OR the name looks like a different kind of business
  drop    a non-target place (government, school, ...), a niche exclusion, or simply not the niche

Both `keep` and `verify` are worth fetching a website for; only `drop` is skipped.
"""
from __future__ import annotations

import re

# Places that are never a customer.
NON_TARGET = ["government", "town hall", "courthouse", "school", "museum", "police", "hospital",
              "university", "embassy", "behörde", "rathaus", "stadtverwaltung", "schule",
              "polizei", "krankenhaus", "universität", "botschaft"]

# Other physical trades: a business whose REAL trade is one of these is not the niche even when it
# also tags the niche as a (secondary) category. Entries that overlap the niche's own terms are
# ignored at runtime (searching "roofer" must not treat "roofing" as foreign).
OTHER_TRADE = ["window", "garage door", "glazing", "conservatory", "truck accessor", "van fit",
               "tyre", "fencing", "roofing", "kitchen", "bathroom", "blinds", "hardware store",
               "diy store", "supermarket", "plumb", "scaffold", "wrapping", "car wash",
               "car dealer", "dealership", "furniture", "removal", "builders merchant",
               "estate agent", "letting agent", "cleaning service", "carpet",
               "composite door", "ironmonger", "car tuning", "vehicle tuning"]

# Name words that betray a different business even when it carries the niche category. Metadata
# alone cannot separate these from a generic-named real one, so they go to `verify`.
NAME_DISQUALIFY = ["invest", "logistic", "realty", "realtor", "estate", "property", "recruit",
                   "solicitor", "accountant", "mortgage", "insurance", "tech repair", "phone repair",
                   "computer repair", "it support", "travel", "consult", "capital", "holdings",
                   "marketing", "media", "design studio",
                   "laundry", "launderette", "restaurant", "barber", "salon", "butcher", "bakery",
                   "florist", "pharmacy", "dentist", "optician", "tattoo", "takeaway", "kebab",
                   "pizza", "cafe", "composite door", "ironmonger", "training", "tuning"]


def primary_category(place: dict) -> str:
    return (place.get("categoryName") or (place.get("categories") or [""])[0] or "").strip()


def _without_overlap(markers: list[str], terms: list[str]) -> list[str]:
    return [m for m in markers if not any(t in m or m in t for t in terms)]


def classify(place: dict, terms, exclusions=()) -> str:
    terms = [t.lower() for t in terms if t]
    cat = primary_category(place).lower()
    name = (place.get("title") or "").lower()
    cats = [c.lower() for c in (place.get("categories") or [])] or [cat]
    if any(t in " ".join([cat] + cats) for t in NON_TARGET):
        return "drop"
    # Only name and PRIMARY category are checked against exclusions: a tow operator with
    # "Trailer rental" as a third category is still a tow operator.
    if any(x in cat or x in name for x in exclusions):
        return "drop"
    if is_retail_category(cat) and not allows_retail(terms):
        return "drop"
    name_sig = any(t in name for t in terms)
    name_bad = any(d in name for d in _without_overlap(NAME_DISQUALIFY, terms))
    cat_sig = any(t in cat for t in terms)
    other_trade = any(d in c for c in cats for d in _without_overlap(OTHER_TRADE, terms))
    # name_sig first: "Addis Locksmiths & Property Maintenance" must not fall into limbo because
    # of "property" when "Locksmiths" is right there in the name.
    if name_sig:
        return "keep"
    if name_bad:
        return "verify"
    if cat_sig:
        return "verify" if other_trade else "keep"
    if not cat:
        return "verify"
    return "drop"


# Retail, wholesale and manufacturing of the trade are not the trade: "Roofing supply store" sells
# to roofers. Allowed only when the niche terms themselves name such a thing.
RETAIL_CATEGORY = re.compile(
    r"\b(supply|supplies|supplier|suppliers|store|stores|wholesale|wholesaler|wholesalers|"
    r"manufacturer|manufacturers|manufacturing|distributor|distributors|"
    r"großhandel|grosshandel|hersteller|fachhandel)\b", re.I)

# Categories too general to say which trade a business is in, so its name may decide.
GENERIC_CATEGORY = re.compile(
    r"\b(contractor|contractors|service|services|company|business|builder|builders|handyman|"
    r"construction|tradesman)\b", re.I)


def is_retail_category(category: str) -> bool:
    return bool(RETAIL_CATEGORY.search(category or ""))


def allows_retail(terms) -> bool:
    return any(RETAIL_CATEGORY.search(str(t)) for t in terms)


def is_generic_category(category: str) -> bool:
    return bool(GENERIC_CATEGORY.search(category or ""))
