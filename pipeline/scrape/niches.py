"""niches.py - how a niche is searched for and how it is recognised.

Two ways in:

  * any free keyword: `--niche roofer` works for every keyword. The slug comes from the keyword,
    the Google search phrase IS the keyword (override with `--search "emergency roofer"`), and
    the terms used to recognise the niche in a Google category or business name are derived from
    the keyword (word stems, simple singular/plural). No exclusions.
  * a tested preset (PRESETS below) with hand-measured terms and exclusions.

Why the terms are narrow: a term that also appears in foreign trades ("recovery" alone would match
data recovery) turns the niche filter into an invitation. Preset terms were measured against the
Google categories that came back; derived terms are a best guess, so a first probe run
(`--cells 20`) is the place to look at what was kept and dropped. Override with `--terms`.

This file is also copied into the Modal container, so it only uses the standard library.
"""
from __future__ import annotations

import re
import unicodedata

# `plural` is the word used in message templates ("I help {trade} get found online").
PRESETS: dict[str, dict] = {
    "locksmith": {
        "search": "locksmith",
        "terms": ("locksmith",),
        "plural": "locksmiths",
    },
    "towing": {
        "search": "towing service",
        # In the UK these businesses call themselves "recovery", so "vehicle recovery" and
        # "breakdown recovery" are fine, but the bare word would match data recovery on its own;
        # within a towing search a name containing "recovery" is a tow operator.
        "terms": ("towing", "tow truck", "recovery", "wrecker", "roadside assistance"),
        "plural": "towing companies",
        # Measured on a county probe: ~4% of hits were tow-bar and trailer dealers with the
        # category "Towing equipment provider", not tow operators.
        "exclusions": ("towing equipment", "towbar", "tow bar", "trailer", "caravan"),
    },
    "plumber": {
        "search": "emergency plumber",
        # In the UK "plumbing & heating" is one trade: gas engineers, heating contractors and
        # drainage services serve the same customer with the same problem.
        "terms": ("plumber", "plumbing", "gas engineer", "heating", "drainage"),
        "plural": "plumbers",
        "exclusions": ("plumbing supply", "bathroom showroom", "plumbers merchant"),
    },
    "water-damage": {
        "search": "water damage restoration",
        "terms": ("water damage", "flood restoration", "fire and water"),
        "plural": "restoration companies",
    },
    "electrician": {
        "search": "emergency electrician",
        "terms": ("electrician", "electrical contractor", "electrical services"),
        "plural": "electricians",
    },
    "autohaus": {
        # Germany, searched in German (regions/DE.json -> language) so categories come back
        # German. Brand and used-car dealers both; "händler" without a hyphen so that
        # "Renaulthändler" matches. Other kinds of dealers are kept out by the exclusions.
        "search": "Autohaus",
        "terms": ("autohaus", "autohändler", "gebrauchtwagen", "car dealer", "händler", "schauraum"),
        "plural": "Autohäuser",
        "exclusions": ("reifen", "teile", "zubehör", "vermietung", "motorrad", "wohnmobil",
                       "fahrrad", "anhänger", "landmaschinen", "baumaschinen", "werkzeug"),
    },
    "schluesseldienst": {
        # Germany, searched in German. "schlosser" is left out on purpose: it matches metalwork
        # shops.
        "search": "Schlüsseldienst",
        "terms": ("schlüsseldienst", "schlüssel", "aufsperrdienst", "türöffnung",
                  "schließtechnik", "locksmith"),
        "plural": "Schlüsseldienste",
        "exclusions": ("metallbau", "stahlbau", "autoschlüssel"),
    },
}

# Words in a keyword that carry no trade information.
FILLER = {
    "emergency", "local", "mobile", "best", "cheap", "near", "me", "the", "and", "for", "in", "of",
    "24", "24h", "hour", "hours", "service", "services", "company", "companies", "near",
    "professional", "affordable", "certified",
}


def slugify(text: str) -> str:
    """'Schlüsseldienst' -> 'schluesseldienst', 'Emergency Roofer' -> 'emergency-roofer'."""
    text = str(text or "").strip().lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def plural(word: str) -> str:
    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch", "sh")):
        return word + "es"
    return word + "s"


def _stems(word: str) -> list[str]:
    """roofers -> roofer, roof ; plumber -> plumber, plumb ; the base must keep 4+ letters."""
    one = singular(word)
    out = [one]
    for suffix in ("er", "or", "ing"):
        if one.endswith(suffix) and len(one) - len(suffix) >= 4:
            out.append(one[: -len(suffix)])
    return out


def derive_terms(keyword: str) -> tuple[str, ...]:
    """Niche-match terms from a free keyword: the phrase itself plus each word's stems."""
    phrase = " ".join(re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*|\d+", str(keyword or "").lower()))
    words = [w for w in re.split(r"[\s/&,+]+", phrase) if w]
    terms: list[str] = []
    if len(words) > 1:
        terms.append(singular(phrase) if phrase.endswith("s") else phrase)
    for word in words:
        if word in FILLER or len(word) < 3:
            continue
        for stem in _stems(word):
            if len(stem) >= 3 and stem not in terms:
                terms.append(stem)
    if not terms and phrase:
        terms.append(singular(phrase))
    return tuple(terms)


def resolve(niche: str, search: str | None = None, terms: str | list | tuple | None = None) -> dict:
    """The one description of a niche that every pipeline step uses.

    -> {"slug", "keyword", "search", "terms", "exclusions", "plural", "preset", "search_overridden"}
    """
    keyword = str(niche or "").strip()
    slug = slugify(keyword)
    if not slug:
        raise SystemExit("--niche needs a keyword, for example: --niche roofer")
    preset = PRESETS.get(slug)
    default_search = preset["search"] if preset else keyword
    chosen = (search or "").strip() or default_search
    if terms:
        listed = [t.strip().lower() for t in (terms.split(",") if isinstance(terms, str) else terms)
                  if str(t).strip()]
    else:
        listed = list(preset["terms"]) if preset else list(derive_terms(keyword))
    last = keyword.split()[-1].lower() if keyword.split() else slug
    return {
        "slug": slug,
        "keyword": keyword,
        "search": chosen,
        "terms": tuple(dict.fromkeys(listed)),
        "exclusions": tuple(preset.get("exclusions", ())) if preset else (),
        "plural": preset["plural"] if preset else (keyword if keyword.lower().endswith("s")
                                                    else " ".join(keyword.split()[:-1] + [plural(last)])),
        "preset": bool(preset),
        "search_overridden": chosen.lower() != default_search.lower(),
    }
