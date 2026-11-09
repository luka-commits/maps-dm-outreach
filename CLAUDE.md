# Maps DM Outreach — instructions for Claude Code

This repo finds local businesses on Google Maps for one niche in one country, collects their
Instagram and Facebook profiles from their websites, and puts them into a local outreach table where
the user sends DMs by hand (Instagram, Facebook, LinkedIn) with split-tested strategies. There is
no email channel. Architecture and contracts:
`docs/ARCHITECTURE.md`. Visual explainer: `docs/system.html`.

## Terminal or VS Code: same steps

The user may run Claude Code in a terminal or in the VS Code extension. Everything below works in
both because you run every command yourself; never ask the user to type into a terminal.

- **Modal login:** run `.venv/bin/modal setup` in the background. It opens the browser, or prints a
  `https://modal.com/token-flow/...` link when it cannot; give that link to the user as a clickable
  link, then wait until `python3 setup/check.py` shows Modal green.
- **The app:** start `cd app && npm run dev` in the background and give the user the link
  http://localhost:4319 to open.
- **Long runs:** a scrape needs about 10 seconds per postcode cell (12 at a time), so anything above
  about 50 cells takes longer than one command may run. Start it in the background, report progress,
  and if it stops, continue with the same command plus `--from <step>`.

## First session: guide the setup

When the user opens this repo for the first time, or says "set up", "get started", "help me install",
walk them through setup one step at a time. Run `python3 setup/check.py` first and after every step;
it prints ✓/✗ with the exact fix. Explain each step in one or two plain sentences, run what you can
run yourself, and stop only where the user must act in a browser or paste a secret.

1. **Python environment.** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
   (Python 3.10+; add `-r requirements-dev.txt` for the tests).
2. **Node and the app.** Node 22.13 or newer (it ships SQLite). `cd app && npm install`.
3. **Modal (runs the Google Maps scraper in the cloud).** The user creates a free account at
   https://modal.com (the Starter plan includes $30 of compute per month, roughly 8,000 postcode
   cells). Then `.venv/bin/modal setup` in the background (see above), which opens the browser to log in
   and stores a token in `~/.modal.toml`. Never ask the user to paste the Modal token into the chat.
4. **Apify (optional, checks if social accounts are active and fetches posts for openers).** The
   user creates an account at https://apify.com, copies the API token from Settings → Integrations,
   and puts it into `.env` as `APIFY_TOKEN=...` themselves (copy `.env.example`). Do not echo the
   token. Without it, the pipeline still runs; the activity check and the opener fetch are skipped.
   `python3 setup/check.py --online` verifies the token with a free request.
5. **Settings.** `python3 setup/check.py --init-config` creates `outreach.config.json`. Ask the user
   for: their first name (sender_name), their timezone, what they offer (offer.service and the
   promise, in their own words), and which two strategies to start with (explain the four from
   `strategies/README.md` in one line each; default `area-question` vs `opener-offer`). Write the
   answers into the file.
6. **Probe run.** Ask for a niche keyword and a country and a small region they know (US, GB, CA,
   AU, IE and DE are ready; any other country first gets its grid, see Daily use → A new country). Run a 20-cell probe so they see the whole chain for well under a dollar:
   `.venv/bin/python run.py --country GB --niche roofer --region "West Yorkshire" --cells 20`.
   Show the funnel it prints. Then start the app in the background (`cd app && npm run dev`) and give the user
   http://localhost:4319.
7. **Done.** Show them how to pull a first batch and how one DM is sent (see Daily use).

Keep a short checklist in the conversation so the user always sees where they are.

## Daily use

- **Find more businesses:** `.venv/bin/python run.py --country <CC> --niche "<keyword>" --region "<county or state>"`.
  Large countries need `--region` (the US has 41,000 postcode cells). `--search "emergency roofer"`
  changes the Google search phrase while keeping the niche. A stopped run continues with
  `--from <step>`; finished cells are never paid twice.
- **A new country:** US, GB, CA, AU, IE and DE ship with the kit. For any other country run
  `.venv/bin/python pipeline/scrape/build_grid.py <CC>` first (free, downloads GeoNames postcodes,
  a few seconds; about 120 countries are covered). It prints the cells, the cost of the whole
  country and the region names to use with `--region`; pick one region for the first run. Above
  about 20,000 cells it suggests `--prefix N` for coarser cells. If GeoNames has no data for the
  country, say so; there is no grid then. Then, for a country whose language is not English:
  use the niche keyword in that language (`couvreur`, not `roofer`), because Google's categories
  come back in it and the niche filter matches on them, and offer to translate the templates in
  `strategies/strategies.json` into that language, keeping every `{placeholder}` unchanged.
- **Cost before running:** the scraper prints an estimate (measured $0.0036 per postcode cell on
  Modal; a county is typically 50 to 300 cells). Tell the user the estimate and get a yes before any
  run above about $2. The activity check costs about $0.0022 per Instagram profile and $0.0039 per
  Facebook page and prints its cost; each profile is paid only once. Free allowances: Modal Starter
  $30/month, Apify Free $5/month. Cost table: README.md → Costs.
- **Outreach:** in the app, "Pull batch" picks today's leads. For leads whose strategy needs an
  opener, use the `dm-opener` skill (`.claude/skills/dm-opener/SKILL.md`). The user sends every
  message by hand and ticks it. Per business, every channel it has on the same day: on Instagram and
  Facebook the user likes a few recent posts, then sends the DM; on LinkedIn the user pastes the
  profile link into the lead and sends a connection request with the message as the note. Never automate sending, log into the user's social accounts, or
  message anyone on their behalf.
- **Which strategy works:** the Analytics page compares reply rates per strategy and channel. Help
  the user read it; suggest changing one variable at a time and waiting for at least 30 sent per
  strategy before calling a winner.

## Rules

- Everything stays local: `data/`, `.env` and `outreach.config.json` are gitignored. Do not commit
  or upload lead data.
- Ask before any paid run above about $2, and before deleting `data/`.
- Tests: `.venv/bin/python -m pytest -q` (pipeline) and `cd app && npm test && npm run typecheck`.
