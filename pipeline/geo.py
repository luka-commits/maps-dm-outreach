"""Country filter from coordinates. A business's own country-code domain overrides the box."""
from __future__ import annotations

import math
from urllib.parse import urlparse

# (min_lat, max_lat, min_lng, max_lng), deliberately generous.
BOXES = {
    "GB": (49.8, 60.9, -8.7, 1.8),
    "IE": (51.3, 55.5, -10.7, -5.9),
    "US": (18.9, 71.5, -179.3, -66.9),
    "CA": (41.6, 83.2, -141.1, -52.5),
    "AU": (-43.7, -10.6, 112.9, 153.7),
    "DE": (47.2, 55.1, 5.8, 15.1),
}
CCTLD = {"GB": (".uk",), "IE": (".ie",), "US": (".us",), "CA": (".ca",), "AU": (".au",), "DE": (".de",)}
# Google Maps returns these placeholder points instead of a real location.
PLACEHOLDERS = {(47.73855, 12.5088275), (0.0, 0.0)}


def box_of(country) -> tuple | None:
    """The hand-set box, or for a country added with build_grid.py the one stored with its grid."""
    cc = str(country).upper()
    if cc in BOXES:
        return BOXES[cc]
    from pipeline.scrape import grid
    box = grid.info(cc).get("box")
    return tuple(box) if box and len(box) == 4 else None


def cctld_of(country) -> tuple:
    cc = str(country).upper()
    return CCTLD.get(cc, ("." + cc.lower(),))


def in_country(lat, lng, country) -> bool | None:
    """True / False, or None when the point is unusable or the country has no box."""
    box = box_of(country)
    if box is None or lat is None or lng is None:
        return None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if (round(lat, 5), round(lng, 5)) in {(round(a, 5), round(b, 5)) for a, b in PLACEHOLDERS}:
        return None
    return box[0] <= lat <= box[1] and box[2] <= lng <= box[3]


def foreign_country(lat, lng, website, country) -> bool:
    """Outside the country box AND the website does not end in the country's own domain."""
    if in_country(lat, lng, country) is not False:
        return False
    website = str(website or "").strip()
    try:
        host = (urlparse(website if "://" in website else "//" + website).hostname or "").lower()
    except ValueError:
        host = ""
    return not host.endswith(cctld_of(country))
