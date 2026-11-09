# Architecture and contracts

Maps DM Outreach turns "a niche in a country" into a local table of businesses with their social
channels, ready for hand-sent DMs. Everything runs on the user's machine except the Google Maps
scrape, which runs on Modal.

```
python run.py --country GB --niche roofer --region "West Yorkshire"

scrape   pipeline/scrape/modal_scrape.py   Google Maps per postcode cell, on Modal, results in a Modal volume
fetch    modal volume get                  cell files to data/runs/<run>/
collect  pipeline/scrape/collect.py        one raw.json, deduplicated by place id
enrich   pipeline/enrich/enrich.py         website fetch: Instagram, Facebook, owner name
import   pipeline/import_leads.py          filters, neighbour town, region -> data/leads.db
activity pipeline/social/activity.py       optional, Apify: marks channels with no post in N months
```

Then `cd app && npm run dev` opens the outreach table at http://localhost:4319.

## Files and ownership

| Path | What | Committed |
|---|---|---|
| `outreach.config.json` | user settings, created from `outreach.config.example.json` during setup | no |
| `.env` | `APIFY_TOKEN` (optional) | no |
| `data/leads.db` | the SQLite database, schema in `app/lib/schema.sql` | no |
| `data/runs/<run>/` | raw cells, `raw.json`, `enriched_raw.json`, measurements | no |
| `data/social_cache/` | Apify answers, each profile paid once | no |
| `data/openers/<date>/` | Instagram posts and images fetched for the dm-opener skill | no |
| `strategies/strategies.json` | DM strategies and templates | yes |
| `pipeline/scrape/regions/<CC>_postcodes.json` | postcode grids: `{"liste": [{"code","ort","region","land_region","lat","lng"}]}` | yes |

Run names: `<CC>-<niche-slug>[-<region-slug>]`, for example `GB-roofer-west-yorkshire`.

## Database contract

`app/lib/schema.sql` is the single schema. Python executes it with `executescript`, Node with
`db.exec`, both idempotently. Re-import updates scraped fields by place id and never touches the
hand-kept fields: `linkedin`, `neighbour_town_manual`, `opener`, `notes`, `contacted_on`,
`disqualified` (unless set by the activity check), `strategy`. An empty channel in a new import never
deletes an existing one.

`enriched_raw.json` rows (gosom shape after `gosom_contract.to_apify_shape`): `placeId`, `title`,
`categoryName`, `categories`, `address`, `city`, `location {lat,lng}`, `phone`, `website`,
`totalScore`, `reviewsCount`, `instagrams[]`, `facebooks[]`, optional owner fields,
plus `_region`/`_ort` from the cell.

## Scope: DMs only

The kit is for social DMs: Instagram, Facebook and LinkedIn. There is no email channel, no email
column and no email sending. A lead is imported only with at least one Instagram or Facebook profile.

## Config contract

`outreach.config.json` keys: `sender_name`, `timezone` (IANA), `offer.service`, `offer.promise`,
`active_strategies` (ids from strategies.json), `daily_limits` per channel (`null` = no limit),
`import.min_reviews`, `import.require_website`, `activity_check.enabled`,
`activity_check.inactive_after_months`, `app_port`. Missing file or keys fall back to the example.

## Strategy assignment

When the table loads, each open lead without a strategy gets one of the active strategies, so its
message can be shown right away. Balance is counted separately for leads with and without an active
Instagram. Strategies with `needs_opener` only go to leads that have an active Instagram; other leads
get a strategy without opener. Stage entries (replied, asset sent, meeting, not interested) are
logged on the channel of the last send, so per-channel analytics stay honest. If none of the active strategies fits, the lead gets
`area-question`. The strategy is stored on the lead and snapshotted on every `sent` touch, so the
analytics page compares strategies by what was actually sent.
