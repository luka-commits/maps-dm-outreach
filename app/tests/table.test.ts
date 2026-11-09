import { test } from "node:test";
import assert from "node:assert/strict";
import { buildRows, filterRows, normalizeView, optionsFor, pageOf, sortRows, valueOf, PAGE_SIZE } from "../lib/table";
import { analytics } from "../lib/analytics";
import type { Kind, Lead, Touch } from "../lib/types";
import type { Strategy } from "../lib/strategies";

const base = (id: string, over: Partial<Lead> = {}): Lead => ({
  id, name: `Business ${id}`, category: null, address: null, postcode: null, town: "Millbrook", region: "Northshire", country: "GB", lat: null, lng: null,
  phone: null, website: null, rating: null, reviews: null, instagram: null, facebook: null, linkedin: null,
  neighbour_town: null, neighbour_town_manual: null, owner_name: null, opener: null, notes: null, niche: "roofer", run: null,
  imported_at: "2026-11-01T09:00:00Z", contacted_on: null, disqualified: null, instagram_inactive: null, facebook_inactive: null, strategy: "area-question", ...over,
});
let n = 0;
const t = (lead_id: string, kind: Kind, channel: Touch["channel"], date: string, strategy: string | null = null): Touch =>
  ({ id: ++n, lead_id, channel, kind, date, text: null, created_at: `${date}T09:00:00Z`, strategy });
const day = "2026-11-05";
const view = (over: object = {}) => normalizeView(over);
const tz = "Europe/London";

test("rows know status, today's batch, last contact and first batch day", () => {
  const leads = [base("a"), base("b", { instagram: "https://www.instagram.com/b/" })];
  const rows = buildRows(leads, [t("a", "sent", "facebook", "2026-11-03"), t("a", "skipped", "facebook", "2026-11-04")], [{ date: day, lead_id: "b" }, { date: "2026-11-01", lead_id: "b" }], day);
  assert.equal(rows[0].last_contact, "2026-11-03", "skipped does not count as contact");
  assert.equal(rows[1].in_todays_batch, true);
  assert.equal(rows[1].in_batch_since, "2026-11-01");
  assert.equal(rows[1].status, "today");
});

test("search, stage, today and column filters combine", () => {
  const leads = [base("a", { name: "Alpha", town: "Millbrook", rating: 4.8, reviews: 100, instagram: "https://www.instagram.com/a/" }),
    base("b", { name: "Bravo", town: "Harrowfield", rating: 4.1, reviews: 8 }), base("c", { name: "Charlie", town: "Harrowfield", rating: null, reviews: null })];
  const rows = buildRows(leads, [t("c", "reply", "facebook", day)], [{ date: day, lead_id: "a" }], day);
  const ids = (v: object) => filterRows(rows, view(v), tz).map((r) => r.lead.id);
  assert.deepEqual(ids({}), ["a", "b", "c"]);
  assert.deepEqual(ids({ search: "harrow" }), ["b", "c"]);
  assert.deepEqual(ids({ today: true }), ["a"]);
  assert.deepEqual(ids({ stage: "replied" }), ["c"]);
  assert.deepEqual(ids({ social: true }), ["a"]);
  assert.deepEqual(ids({ filters: { instagram: { kind: "boolean", value: "yes" } } }), ["a"]);
  assert.deepEqual(ids({ filters: { instagram: { kind: "boolean", value: "no" } } }), ["b", "c"]);
  assert.deepEqual(ids({ filters: { town: { kind: "multi", values: ["Harrowfield"] } } }), ["b", "c"]);
  assert.deepEqual(ids({ filters: { name: { kind: "text", value: "ALP" } } }), ["a"]);
  assert.deepEqual(ids({ filters: { rating: { kind: "range", from: 4.5 } } }), ["a"]);
  assert.deepEqual(ids({ filters: { rating: { kind: "range", to: 4.5, empty: true } } }), ["b", "c"]);
  assert.deepEqual(ids({ filters: { last_contact: { kind: "date", from: "2026-11-05", to: "2026-11-05" } } }), ["c"]);
  assert.deepEqual(ids({ filters: { last_contact: { kind: "date", empty: true } } }), ["a", "b"]);
});

test("sorting keeps blanks last in both directions, stages sort by pipeline order, social first overrides", () => {
  const leads = [base("a", { rating: 4.1 }), base("b", { rating: null }), base("c", { rating: 4.9, instagram: "https://www.instagram.com/c/" })];
  const rows = buildRows(leads, [], [], day);
  const order = (s: object, social = false) => sortRows(rows, s as never, social).map((r) => r.lead.id);
  assert.deepEqual(order({ column: "rating", direction: "asc" }), ["a", "c", "b"]);
  assert.deepEqual(order({ column: "rating", direction: "desc" }), ["c", "a", "b"]);
  assert.deepEqual(order({ column: "name", direction: "asc" }, true), ["c", "a", "b"]);
  const staged = buildRows([base("x"), base("y")], [t("y", "meeting", "facebook", day)], [], day);
  assert.deepEqual(sortRows(staged, { column: "stage", direction: "desc" }).map((r) => r.lead.id), ["y", "x"]);
});

test("option counts include blanks last and all boolean choices", () => {
  const rows = buildRows([base("a", { town: "Zed" }), base("b", { town: null }), base("c", { town: "Alpha" })], [], [], day);
  assert.deepEqual(optionsFor(rows, "town").map((o) => o.value), ["Alpha", "Zed", ""]);
  assert.deepEqual(optionsFor(rows, "instagram"), [{ value: "yes", count: 0 }, { value: "no", count: 3 }]);
  assert.equal(optionsFor(rows, "stage")[0].value, "new");
});

test("pagination is 50 per page and clamps the page", () => {
  const rows = buildRows(Array.from({ length: 120 }, (_, i) => base(`p${i}`)), [], [], day);
  assert.equal(PAGE_SIZE, 50);
  assert.equal(pageOf(rows, 1).length, 50);
  assert.equal(pageOf(rows, 3).length, 20);
  assert.equal(pageOf(rows, 99).length, 20);
  assert.equal(pageOf(rows, -4).length, 50);
  assert.equal(pageOf(rows, Number.NaN).length, 50);
});

test("neighbour town, strategy and message columns show what the user sees", () => {
  const rows = buildRows([base("a", { neighbour_town: "Leeds Headingley", neighbour_town_manual: "Otley", strategy_name: "Area question", message: "Hi", missing: null }),
    base("b", { message: null, missing: "Opener missing" })], [], [], day);
  assert.equal(valueOf(rows[0], "neighbour_town"), "Otley");
  assert.equal(valueOf(rows[0], "strategy"), "Area question");
  assert.equal(valueOf(rows[1], "message"), "Opener missing");
});

test("normalizeView drops unknown columns, bad filters and bad dates", () => {
  const v = normalizeView({ columns: ["name", "nope", "name", "facebook"], stage: "bogus", sort: { column: "nope", direction: "desc" },
    filters: { rating: { kind: "text", value: "x" }, facebook: { kind: "boolean", value: "maybe" }, last_contact: { kind: "date", from: "2026-02-31", to: "2026-03-01" } } });
  assert.deepEqual(v.columns, ["name", "facebook"]);
  assert.equal(v.stage, "");
  assert.deepEqual(v.sort, { column: "name", direction: "desc" });
  assert.deepEqual(Object.keys(v.filters), ["last_contact"]);
  assert.deepEqual(v.filters.last_contact, { kind: "date", empty: false, to: "2026-03-01" });
  assert.equal(normalizeView(null).columns.length > 3, true);
  assert.deepEqual(normalizeView({ columns: [] }).columns, ["name"]);
});

const strategies: Strategy[] = [
  { id: "area-question", name: "Area question", summary: "", needs_opener: false, requires: [], template: "" },
  { id: "opener-offer", name: "Opener offer", summary: "", needs_opener: true, requires: [], template: "" },
];

test("analytics: cohorts follow the strategy snapshot on sent touches, per channel and total", () => {
  const touches = [
    t("a", "sent", "instagram", "2026-11-01", "area-question"), t("a", "reply", "instagram", "2026-11-02"), t("a", "meeting", "instagram", "2026-11-03"),
    t("b", "sent", "instagram", "2026-11-01", "area-question"), t("b", "not_interested", "instagram", "2026-11-02"),
    t("c", "sent", "facebook", "2026-11-01", "area-question"), t("c", "sent", "instagram", "2026-11-01", "area-question"), t("c", "asset_sent", "facebook", "2026-11-04"),
    t("d", "sent", "instagram", "2026-11-01", "opener-offer"),
    t("e", "sent", "facebook", "2026-11-01", "legacy-strategy"),
  ];
  const rows = analytics(strategies, touches);
  const get = (s: string, c: string) => rows.find((r) => r.strategy === s && r.channel === c)!;
  assert.deepEqual([get("area-question", "instagram").sent, get("area-question", "instagram").replied, get("area-question", "instagram").meetings, get("area-question", "instagram").not_interested], [3, 1, 1, 1]);
  assert.equal(get("area-question", "facebook").sent, 1);
  assert.equal(get("area-question", "facebook").asset_sent, 1);
  assert.equal(get("area-question", "instagram").asset_sent, 0, "the asset went out on Facebook, not Instagram");
  assert.equal(get("area-question", "total").sent, 3);
  assert.equal(get("area-question", "total").asset_sent, 1);
  assert.equal(Math.round(get("area-question", "total").reply_rate), 33);
  assert.equal(get("opener-offer", "total").sent, 1);
  assert.equal(get("opener-offer", "total").reply_rate, 0);
  assert.equal(get("legacy-strategy", "facebook").sent, 1, "snapshots of strategies no longer defined still show up");
  assert.equal(get("legacy-strategy", "total").name, "legacy-strategy");
});

test("analytics with nothing sent has all-zero rows", () => {
  assert.ok(analytics(strategies, []).every((r) => r.sent === 0 && r.reply_rate === 0));
});
