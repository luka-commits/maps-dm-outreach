-- One local SQLite file (data/leads.db) shared by the importer (Python) and the app (Node).
-- Scraped fields are refreshed on re-import; hand-kept fields are never overwritten by an import.
CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY,                 -- Google place id
  name TEXT NOT NULL,
  category TEXT,                       -- Google category, e.g. "Roofing contractor"
  address TEXT, postcode TEXT, town TEXT,
  region TEXT,                         -- county / state from the postcode grid
  country TEXT,                        -- ISO code, e.g. GB
  lat REAL, lng REAL,
  phone TEXT, website TEXT, rating REAL, reviews INTEGER,
  instagram TEXT, facebook TEXT,
  linkedin TEXT,                       -- hand-kept: entered in the lead drawer
  neighbour_town TEXT,                 -- nearest other town >= 2 km away, computed on import
  neighbour_town_manual TEXT,          -- hand-kept override, wins over neighbour_town
  owner_name TEXT,                     -- from the website (imprint / about page) when found
  opener TEXT,                         -- hand-kept: one personal line about a recent post
  notes TEXT,                          -- hand-kept
  niche TEXT,                          -- niche slug of the run, e.g. roofer
  run TEXT,                            -- run name, e.g. GB-roofer-west-yorkshire
  imported_at TEXT NOT NULL,           -- ISO timestamp of first import
  contacted_on TEXT,                   -- date the stage "Contacted" was set by hand
  disqualified TEXT,                   -- reason or date; set by the user or the activity check
  instagram_inactive TEXT,             -- reason a channel is dead, e.g. "last post 2023-08-17"
  facebook_inactive TEXT,
  strategy TEXT                        -- DM strategy id assigned for the split test
);
CREATE TABLE IF NOT EXISTS touches (
  id INTEGER PRIMARY KEY,
  lead_id TEXT NOT NULL REFERENCES leads(id),
  channel TEXT NOT NULL CHECK (channel IN ('instagram', 'facebook', 'linkedin')),
  kind TEXT NOT NULL CHECK (kind IN ('sent', 'skipped', 'reply', 'asset_sent', 'meeting', 'not_interested')),
  date TEXT NOT NULL,                  -- YYYY-MM-DD in the configured timezone
  text TEXT,
  created_at TEXT NOT NULL,
  strategy TEXT                        -- strategy snapshot at send time
);
CREATE INDEX IF NOT EXISTS touches_lead ON touches(lead_id, date);
CREATE TABLE IF NOT EXISTS batches (
  date TEXT NOT NULL,
  lead_id TEXT NOT NULL REFERENCES leads(id),
  position INTEGER NOT NULL,
  PRIMARY KEY (date, lead_id)
);
CREATE TABLE IF NOT EXISTS views (
  name TEXT PRIMARY KEY,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_strategy ON leads(strategy);
CREATE INDEX IF NOT EXISTS touches_strategy ON touches(strategy, kind);
