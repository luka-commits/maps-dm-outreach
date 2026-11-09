# Maps DM Outreach

Type a niche and a country. Get a table of local businesses with their Instagram and Facebook,
ready for hand-sent DMs with split-tested strategies.

```
python run.py --country GB --niche roofer --region "West Yorkshire"
```

Google Maps is searched postcode by postcode (a county-wide search finds about a tenth of the
businesses), each business's website is read for its Instagram and Facebook links and the owner's
first name, dead accounts are filtered out, and everything lands in a local outreach table at
http://localhost:4319. You send each DM yourself; the table tells you who is next, copies the
message, counts your daily limits and compares which strategy gets replies.

Visual explainer with costs and the four DM strategies: open [`docs/system.html`](docs/system.html)
in your browser.

## Get started

Open this folder in Claude Code and say **"set up"**. It walks you through everything
([`CLAUDE.md`](CLAUDE.md)) and checks each step with `python3 setup/check.py`.

By hand:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd app && npm install && cd ..
.venv/bin/modal setup                      # free Modal account, runs the scraper
cp .env.example .env                       # optional: APIFY_TOKEN=... for the activity check
python3 setup/check.py --init-config       # creates outreach.config.json, then edit it
python3 setup/check.py --online            # everything green?
python3 run.py --country GB --niche roofer --region "West Yorkshire" --cells 20   # probe, about $0.10
cd app && npm run dev                      # http://localhost:4319
```

Needs Python 3.10+, Node 22.13+, a free [Modal](https://modal.com) account and optionally a free
[Apify](https://apify.com) account. Countries: US, GB, CA, AU, IE, DE. Any niche keyword works;
`locksmith`, `towing`, `plumber`, `water-damage`, `electrician`, `autohaus` and `schluesseldienst`
are tuned presets.

## Costs

Measured on a real run (GB, roofer, 20 postcode cells → 268 businesses → 44 leads, 29 of them
active on social): **$0.26 in total**, under one cent per active lead.

| What | Price | Free allowance |
|---|---|---|
| Google Maps scrape on Modal | $0.0036 per postcode cell | Modal Starter includes $30/month (about 8,000 cells) |
| Activity check on Apify | $0.0022 per Instagram profile, $0.0039 per Facebook page, each paid once | Apify Free includes $5/month |
| Instagram posts for openers | about $0.003 per profile | same Apify credit |
| Website reading, import, app | free, runs on your machine | |

A full county is typically 50 to 300 cells ($0.20 to $1.10). The scraper prints its estimate before it
starts; large countries need `--region` (the whole US is 41,000 cells, about $150). Prices are the
providers' rates on 9 November 2026; check their pricing pages.

## Commands

| Task | Command |
|---|---|
| Find businesses | `python3 run.py --country <CC> --niche "<keyword>" [--region "<county/state>"] [--cells N] [--search "<google phrase>"]` |
| Continue a stopped run | same command with `--from <scrape\|fetch\|collect\|enrich\|import\|activity>` |
| Skip the paid activity check | `--no-activity` |
| Outreach table | `cd app && npm run dev` |
| Openers for today's batch | ask Claude Code to "write the openers" (skill `dm-opener`) |
| Check setup | `python3 setup/check.py [--online]` |
| Tests | `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest` · `cd app && npm test` |

## What it does not do

It never sends a message, logs into your social accounts or automates DMs; every message goes out
by hand from your own account. There is no email channel. Lead data stays on your machine in
`data/` (gitignored).

DM strategies and the rules behind them: [`strategies/README.md`](strategies/README.md).
Architecture and data contracts: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
