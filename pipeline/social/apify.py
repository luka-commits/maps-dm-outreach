"""A minimal Apify client: run an actor with a spending cap and read its dataset."""
from __future__ import annotations

import time

import httpx

API = "https://api.apify.com/v2"
# Approximate prices when this was written; the real cost of every run is read back from Apify.
PRICE_INSTAGRAM_PROFILE = 0.0026
PRICE_FACEBOOK_PAGE = 0.005
INSTAGRAM_ACTOR = "apify~instagram-profile-scraper"
FACEBOOK_ACTOR = "apify~facebook-posts-scraper"


class ApifyLimit(Exception):
    """Apify refused to start a run: monthly free credit used up, or the plan does not allow it."""


def run_actor(token: str, actor: str, actor_input: dict, max_usd: float, *,
              client: httpx.Client | None = None, poll_seconds: float = 10.0) -> tuple[list[dict], bool, float]:
    """-> (items, finished_ok, cost_usd). Raises ApifyLimit when the run cannot start."""
    http = client or httpx.Client(timeout=120)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = http.post(f"{API}/acts/{actor}/runs", params={"maxTotalChargeUsd": max_usd},
                         json=actor_input, headers=headers)
        if resp.status_code in (402, 403):
            raise ApifyLimit(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        run = resp.json()["data"]
        while run["status"] in ("READY", "RUNNING"):
            time.sleep(poll_seconds)
            r = http.get(f"{API}/actor-runs/{run['id']}", headers=headers)
            r.raise_for_status()
            run = r.json()["data"]
        items = http.get(f"{API}/datasets/{run['defaultDatasetId']}/items", params={"clean": "true"},
                         headers=headers)
        items.raise_for_status()
        return items.json(), run["status"] == "SUCCEEDED", float(run.get("usageTotalUsd") or 0)
    finally:
        if client is None:
            http.close()
