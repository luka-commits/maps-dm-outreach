import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanName, competitorsFor, firstName, neighbourFor, pluralTrade, renderMessage, shortTown } from "../lib/message";
import type { Strategy } from "../lib/strategies";

const file = JSON.parse(readFileSync(resolve(process.cwd(), "../strategies/strategies.json"), "utf8"));
const strategies: Strategy[] = file.strategies;
const byId = (id: string) => strategies.find((s) => s.id === id)!;
const config = { sender_name: "Alex", offer: { service: "Google profile optimisation", promise: "ten new jobs in 60 days, free for you" } };
const lead = (over = {}) => ({ town: "Millbrook", neighbour_town: "Harrowfield", neighbour_town_manual: null, owner_name: "Dan Whitaker", opener: "love the slate job on Mill Lane", niche: "roofer", ...over });

test("area-question names the neighbour town and needs one", () => {
  assert.equal(renderMessage(lead(), byId("area-question"), config, null).text, "Hi, do you also cover Harrowfield?");
  assert.equal(renderMessage(lead({ neighbour_town_manual: "Ashby" }), byId("area-question"), config, null).text, "Hi, do you also cover Ashby?");
  assert.deepEqual(renderMessage(lead({ neighbour_town: null }), byId("area-question"), config, null), { text: null, missing: "Neighbour town missing" });
  assert.deepEqual(renderMessage(lead({ neighbour_town: "  " }), byId("area-question"), config, null), { text: null, missing: "Neighbour town missing" });
});

test("opener-offer renders greeting, towns, competitor clause and offer", () => {
  const full = renderMessage(lead(), byId("opener-offer"), config, "Ironbridge Roof Repairs").text!;
  assert.equal(full, "Hey Dan, love the slate job on Mill Lane\n\nI checked your visibility in Millbrook and Harrowfield and optimised your Google profile so you can get past Ironbridge Roof Repairs. You only need to copy it. My promise: ten new jobs in 60 days, free for you. Can I send you the profile?");
  const plain = renderMessage(lead({ owner_name: null }), byId("opener-offer"), config, null).text!;
  assert.ok(plain.startsWith("Hey, love the slate"));
  assert.ok(plain.includes("so you rank higher on Google"));
  assert.deepEqual(renderMessage(lead({ opener: "" }), byId("opener-offer"), config, null), { text: null, missing: "Opener missing" });
  assert.deepEqual(renderMessage(lead({ opener: null, town: null }), byId("opener-offer"), config, null), { text: null, missing: "Opener missing" });
  assert.deepEqual(renderMessage(lead({ town: "" }), byId("opener-offer"), config, null), { text: null, missing: "Town missing" });
});

test("towns collapses to the town when there is no distinct neighbour", () => {
  const same = renderMessage(lead({ neighbour_town: "millbrook" }), byId("opener-offer"), config, null).text!;
  assert.ok(same.includes("visibility in Millbrook and optimised"));
  const none = renderMessage(lead({ neighbour_town: null }), byId("opener-offer"), config, null).text!;
  assert.ok(none.includes("visibility in Millbrook and optimised"));
});

test("post-question and trade-offer use the opener, greeting and plural trade", () => {
  assert.equal(renderMessage(lead(), byId("post-question"), config, null).text, "love the slate job on Mill Lane had a look at your google listing while i was there, want the two things i'd change?");
  assert.deepEqual(renderMessage(lead({ opener: null }), byId("post-question"), config, null), { text: null, missing: "Opener missing" });
  assert.equal(renderMessage(lead(), byId("trade-offer"), config, null).text, "Hey Dan, love the slate job on Mill Lane i help roofers get found online. cool if i send you your google profile, website and seo fixes upfront?");
});

test("every shipped strategy renders without leftover placeholders for a complete lead", () => {
  for (const s of strategies) {
    const r = renderMessage(lead(), s, config, "Rival Roofing");
    assert.ok(r.text, `${s.id} should render`);
    assert.equal(/\{\w+\}/.test(r.text!), false, `${s.id} left a placeholder`);
  }
});

test("sender name and offer come from the config", () => {
  const custom: Strategy = { id: "x", name: "x", summary: "", needs_opener: false, requires: [], template: "{sender_name}: {offer_service} / {offer_promise}" };
  assert.equal(renderMessage(lead(), custom, config, null).text, "Alex: Google profile optimisation / ten new jobs in 60 days, free for you");
});

test("first name skips titles and rejects odd tokens", () => {
  assert.equal(firstName("Dan Whitaker"), "Dan");
  assert.equal(firstName("Mr Ben Archer"), "Ben");
  assert.equal(firstName("Dr. Amara Obi"), "Amara");
  assert.equal(firstName(null), "");
  assert.equal(firstName("Mr"), "");
  assert.equal(firstName("1234"), "");
});

test("a neighbour in the same city is shortened to the district, a prefix word is not a city", () => {
  assert.equal(shortTown("Leeds Headingley", "Leeds"), "Headingley");
  assert.equal(shortTown("Leeds Headingley", "Leeds Roundhay"), "Headingley");
  assert.equal(shortTown("Leeds Headingley", "Bradford"), "Leeds Headingley");
  assert.equal(shortTown("West Bromwich", "West Midlands"), "West Bromwich");
  assert.equal(shortTown("St Albans", "St Neots"), "St Albans");
  assert.equal(neighbourFor({ town: "Leeds", neighbour_town: "Leeds Headingley", neighbour_town_manual: null }), "Headingley");
  assert.equal(neighbourFor({ town: "Leeds", neighbour_town: "Leeds Headingley", neighbour_town_manual: " Otley " }), "Otley");
});

test("trade is the niche keyword in plural", () => {
  assert.equal(pluralTrade("roofer"), "roofers");
  assert.equal(pluralTrade("plumber"), "plumbers");
  assert.equal(pluralTrade("hair-salon"), "hair salons");
  assert.equal(pluralTrade("bakery"), "bakeries");
  assert.equal(pluralTrade("locksmith"), "locksmiths");
  assert.equal(pluralTrade("electricians"), "electricians");
  assert.equal(pluralTrade("beautician"), "beauticians");
  assert.equal(pluralTrade("florist"), "florists");
  assert.equal(pluralTrade("coach"), "coaches");
  assert.equal(pluralTrade(null), "local businesses");
});

test("competitor names lose legal suffixes, taglines and bracketed bits and get shortened", () => {
  assert.equal(cleanName("Greenfield Roofing LLC | Free quotes"), "Greenfield Roofing");
  assert.equal(cleanName("Ironbridge Roof Repairs Ltd"), "Ironbridge Roof Repairs");
  assert.equal(cleanName("Summit Roof & Gutter Inc"), "Summit Roof & Gutter");
  assert.equal(cleanName("Pennine Roofers (Harrowfield)"), "Pennine Roofers");
  assert.equal(cleanName("Acme Roofing GmbH"), "Acme Roofing");
  assert.equal(cleanName("Acme Roofing Pty Ltd"), "Acme Roofing");
  assert.equal(cleanName("Millbrook Slate and Tile Roofing Specialists and Restoration Services", "Millbrook"), "Slate and Tile Roofing");
  const long = cleanName("The Very Long Named Roofing Company of the North Country");
  assert.ok(long.length <= 30, long);
});

test("competitor = most reviews (10 or more) in the town, else the region, same niche, never the lead itself", () => {
  const rows = [
    { id: "a", name: "Alpha Roofing Ltd", town: "Millbrook", region: "Northshire", reviews: 50, niche: "roofer" },
    { id: "b", name: "Bravo Roofing", town: "Millbrook", region: "Northshire", reviews: 200, niche: "roofer" },
    { id: "c", name: "Charlie Roofing", town: "Harrowfield", region: "Northshire", reviews: 120, niche: "roofer" },
    { id: "d", name: "Delta Roofing", town: "Harrowfield", region: "Northshire", reviews: 9, niche: "roofer" },
    { id: "e", name: "Echo Plumbing", town: "Millbrook", region: "Northshire", reviews: 900, niche: "plumber" },
    { id: "f", name: "Foxtrot Roofing", town: "Elmsworth", region: "Northshire", reviews: 30, niche: "roofer" },
    { id: "g", name: "Alpha Roofing", town: "Millbrook", region: "Northshire", reviews: 40, niche: "roofer" },
  ];
  const map = competitorsFor(rows);
  assert.equal(map.get("a"), "Bravo Roofing");
  assert.equal(map.get("b"), "Alpha Roofing");          // not itself; the next best in town
  assert.equal(map.get("c"), "Bravo Roofing");          // Harrowfield has no one else with 10+ -> region
  assert.equal(map.get("d"), "Charlie Roofing");        // 9 reviews itself, still gets a competitor
  assert.equal(map.get("e"), null);                     // different niche: nobody to compare with
  assert.equal(map.get("f"), "Bravo Roofing");          // no one in its town -> region winner
  assert.equal(map.get("g"), "Bravo Roofing");
  const branch = competitorsFor([
    { id: "x", name: "Delta Roofing Ltd", town: "Millbrook", region: "Northshire", reviews: 80, niche: "roofer" },
    { id: "y", name: "Delta Roofing", town: "Millbrook", region: "Northshire", reviews: 70, niche: "roofer" },
  ]);
  assert.equal(branch.get("x"), null);                  // a branch of itself is no competitor
  assert.equal(branch.get("y"), null);
});
