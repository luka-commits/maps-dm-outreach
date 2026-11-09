"""owner.py - the owner's first name, taken from what is already on the page.

A cold message that starts with "Hey Dave," beats "Hey,". The name is in three places we already
have, ordered by how sure they are:

    email address   "steve@acmeroofing.co.uk"            -> Steve      sure
    business name   "Brian Smith Heating & Plumbing"     -> Brian      sure
    website text    "Hi, I'm Dave and I've been a ..."   -> Dave       probable

The rule that beats all others: **when in doubt, no name.** A wrong greeting costs more than none.
So a candidate is only taken if it is in the first-name list (firstnames.json); nothing is guessed.
A first draft without that list took "acelocksman" and "askus" for first names.
"""
from __future__ import annotations

import json
import pathlib
import re

NAMES_FILE = pathlib.Path(__file__).resolve().parent / "firstnames.json"

# Words in front of an @ that are never a first name.
GENERIC = {
    "info", "contact", "hello", "hi", "admin", "office", "enquiries", "enquiry", "sales", "mail",
    "email", "e-mail", "support", "team", "bookings", "booking", "accounts", "account", "service",
    "services", "help", "hallo", "kontakt", "post", "mailbox", "reception", "customerservice", "cs",
    "hire", "jobs", "new", "askus", "ask", "quote", "quotes", "general", "main", "reply", "noreply",
    "no-reply", "web", "website", "shop", "orders", "order", "finance", "invoice", "invoices", "hq",
    "uk", "london", "manager", "director", "owner", "boss", "the", "your", "me", "us", "we",
}

# Names that exist but are almost always the brand when they start a business name (measured:
# "Sparkle Cleaning", "Molly Maid", "Genesis ...").
BRAND = {
    "sparkle", "molly", "genesis", "cinderella", "astrix", "goldy", "glad", "fan", "abra", "brain",
    "buddy", "dusty", "jojo", "angel", "precious", "diamond", "crystal", "amber", "ruby", "jade",
    "summer", "autumn", "winter", "storm", "rain", "sky", "hunter", "chase", "major", "duke",
    "prince", "king", "queen", "royal", "champion", "lucky", "sunny", "happy", "joy", "hope",
    "faith", "grace", "honor", "justice", "liberty", "america", "sterling", "marshall", "hammer",
    "steel", "iron", "swift", "rocket", "arrow", "eagle", "falcon", "phoenix", "titan", "atlas",
    "apollo", "mercury", "neptune", "jupiter",
}

# Business-name openers that do not make the start a first name.
TRADE_WORD = re.compile(
    r"^(fast|quick|rapid|express|local|city|county|national|premier|prime|elite|pro|expert|master|"
    r"top|best|first|new|old|great|royal|crown|swift|smart|sure|safe|secure|total|complete|perfect|"
    r"flawless|clean|fresh|bright|blue|red|green|black|white|gold|silver|north|south|east|west|"
    r"central|home|house|door|lock|key|gas|heat|water|drain|pipe|emergency|allday|hour|day|night|"
    r"star|ace|apex|alpha|omega|abc|aaa)$", re.I)


def _load_names() -> set[str]:
    if not NAMES_FILE.is_file():
        return set()
    try:
        return {str(n).strip().lower() for n in json.loads(NAMES_FILE.read_text(encoding="utf-8"))
                if str(n).strip()}
    except (OSError, json.JSONDecodeError):
        return set()


FIRST_NAMES = _load_names()


def _candidate(word: str, towns: set[str], town: str = "") -> str | None:
    w = re.sub(r"[^a-zA-ZäöüÄÖÜß'\-]", "", word or "").strip("'-")
    k = w.lower()
    if len(w) < 3 or k in GENERIC or k in BRAND or TRADE_WORD.match(w):
        return None
    # Towns that are also first names are the most common false alarm ("Marietta Top Locksmith").
    if k in towns or k == str(town or "").strip().lower():
        return None
    return w if k in FIRST_NAMES else None


def _is_trade_word(token: str, trade_terms=()) -> bool:
    squeezed = re.sub(r"[^a-z]", "", token.lower())
    if squeezed in {"ltd", "limited", "and", "co", "services", "service", "the", "llc", "inc"}:
        return True
    fragments = list(TRADE_FRAGMENTS) + [re.sub(r"[^a-z]", "", str(t).lower()) for t in trade_terms]
    return any(len(f) >= 4 and f in squeezed for f in fragments)


def from_business_name(name: str, towns: set[str], town: str = "", trade_terms=()) -> str | None:
    head = re.split(r"[|,\-–(]", str(name or ""))[0].strip()
    parts = head.split()
    if not parts:
        return None
    # "Clark Roofing" is a surname plus a trade, "Brian Smith Roofing" is a person's first name
    # plus a surname. One lone word before the trade is only a name when it is possessive
    # ("Dave's Roofing"); otherwise it could just as well be the surname, so: no name.
    leading = []
    for token in parts:
        if _is_trade_word(token, trade_terms):
            break
        leading.append(token)
    if len(leading) < 2 and not re.search(r"['’]s$", parts[0]):
        return None
    # Strip the genitive only; rstrip("'s") would turn "James" into "Jame".
    first = re.sub(r"['’]s?$", "", parts[0])
    # "MAB Locksmiths" is not a person named Mab: short all-caps words are initials.
    if len(first) < 4 or (first.isupper() and len(first) <= 4):
        return None
    return _candidate(first, towns, town)


def _known_rest(rest: str, towns: set[str]) -> bool:
    """Is what follows the name a word of its own (surname, trade word, town), not a cut-off word?"""
    r = rest.lower().lstrip("s")
    if not r:
        return True
    if r in FIRST_NAMES or r in towns:
        return True
    return bool(re.fullmatch(
        r"(lock|key|plumb|heat|gas|drain|clean|tow|electric|build|roof|service|s|locks?|keys?|"
        r"plumbing|heating|cleaning|towing|smith|roofing|electrical|builders?|joinery|paint)+",
        r, re.I))


# Fragments that mark an email local part as a business label, not a person (>= 4 letters so that
# a first name is never swallowed by accident; when in doubt the answer is "no name").
TRADE_FRAGMENTS = ("roof", "plumb", "heating", "drain", "clean", "towing", "electric", "build",
                   "joinery", "construct", "service", "contract", "maintenance", "repair",
                   "locksmith", "glazing", "scaffold", "paving", "landscap", "decorat", "carpent",
                   "limited", "group", "solutions")
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"}
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


def is_brand_local(local: str, business_name: str = "", trade_terms=()) -> bool:
    """clarkroofing@ for "Clark Roofing": the address is the brand, whoever reads it."""
    squeezed = re.sub(r"[^a-z]", "", local.lower())
    if not squeezed:
        return True
    fragments = list(TRADE_FRAGMENTS) + [re.sub(r"[^a-z]", "", str(t).lower()) for t in trade_terms]
    if any(len(f) >= 4 and f in squeezed for f in fragments):
        return True
    name_slug = re.sub(r"[^a-z]", "", re.sub(r"\b(ltd|limited|and)\b", "", business_name.lower()))
    return bool(name_slug) and squeezed == name_slug


def from_email(email: str, towns: set[str], town: str = "", business_name: str = "",
               trade_terms=()) -> str | None:
    local = re.sub(r"\d+$", "", str(email or "").split("@")[0])
    if is_brand_local(local, business_name, trade_terms):
        return None
    for part in re.split(r"[._\-]", local):
        found = _candidate(part, towns, town)
        if found:
            return found
    # Longest match wins: "juliomachado" starts with "juli" and "julio".
    matches = sorted((n for n in FIRST_NAMES if len(n) >= 4 and local.lower().startswith(n)),
                     key=len, reverse=True)
    for first in matches:
        rest = local[len(first):]
        if rest.isalpha() and _known_rest(rest, towns) and _candidate(first, towns, town):
            return first
    return None


def from_emails(emails, towns: set[str], town: str = "", business_name: str = "",
                trade_terms=()) -> str | None:
    """Every address is looked at, not just the first (info@ comes first and says nothing). Two
    different names among them is ambiguous, so: no name from the emails."""
    if isinstance(emails, str):
        emails = [emails]
    names = {n.lower(): n for e in emails or []
             if (n := from_email(e, towns, town, business_name, trade_terms))}
    return next(iter(names.values())) if len(names) == 1 else None


I_AM = re.compile(r"\b(?i:i['’]?m|i am|my name is|ich bin|ich heisse|ich heiße)\s+([A-ZÄÖÜ][a-zäöüß'\-]{2,15})\b")
OWNER = re.compile(
    r"\b(?:owner|founder|director|proprietor|inhaber|gr[üu]nder|gesch[äa]ftsf[üu]hrer)\b[^.]{0,30}?"
    r"\b([A-ZÄÖÜ][a-zäöüß'\-]{2,15})\b", re.I)


def valid_website_name(name: str | None, towns: set[str] | None = None) -> bool:
    """A name found in free text: months and weekdays are dates ("Director, May 2019"), not people."""
    k = str(name or "").strip().lower()
    return bool(k) and k not in MONTHS and k not in WEEKDAYS and _candidate(k, towns or set()) is not None


def from_website_text(text: str, towns: set[str]) -> str | None:
    for pattern in (I_AM, OWNER):
        for match in pattern.finditer(str(text or "")[:20000]):
            name = _candidate(match.group(1), towns)
            if name and valid_website_name(name, towns):
                return name
    return None


def find(*, business_name: str = "", email="", emails=None, website_text: str = "",
         website_name: str | None = None, towns: set[str] | None = None, town: str = "",
         trade_terms=()) -> dict | None:
    """-> {"first_name": "Steve", "source": "email"} or None.

    Order of certainty: any of the emails, then the business name, then website text. The email
    beats the business name: "Brian Smith Heating" with the address neil.smith@... is the father's
    business and Neil's inbox. `website_name` is a candidate already extracted from the site."""
    towns = towns or set()
    site = from_website_text(website_text, towns) or (
        website_name if valid_website_name(website_name, towns) else None)
    for source, value in (
            ("email", from_emails(emails if emails is not None else email, towns, town,
                                  business_name, trade_terms)),
            ("business name", from_business_name(business_name, towns, town, trade_terms)),
            ("website", site)):
        if value:
            return {"first_name": value.capitalize(), "source": source}
    return None
