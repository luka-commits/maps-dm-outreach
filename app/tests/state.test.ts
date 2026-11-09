import { test } from "node:test";
import assert from "node:assert/strict";
import { activeChannels, doneToday, stageOf, statusOf } from "../lib/state";
import { dayIn, shortDay } from "../lib/date";
import { linkedinProfile } from "../lib/linkedin";
import type { Kind, Lead, Touch } from "../lib/types";

const lead = (over: Partial<Lead> = {}): Lead => ({
  id: "t1", name: "Demo Roofing", category: null, address: null, postcode: null, town: "Millbrook", region: "Northshire", country: "GB",
  lat: null, lng: null, phone: null, website: null, rating: null, reviews: null,
  instagram: "https://www.instagram.com/demo_example/", facebook: "https://www.facebook.com/hello.example/", linkedin: null, neighbour_town: "Harrowfield",
  neighbour_town_manual: null, owner_name: null, opener: null, notes: null, niche: "roofer", run: null, imported_at: "2026-11-01T09:00:00Z",
  contacted_on: null, disqualified: null, instagram_inactive: null, facebook_inactive: null, strategy: null, ...over,
});
const day = "2026-11-05";
let id = 0;
const touch = (kind: Kind, channel: Touch["channel"] = "facebook", date = day): Touch => ({
  id: ++id, lead_id: "t1", channel, kind, date, text: null, created_at: `${date}T09:00:00Z`, strategy: null,
});

for (const [index, [kind, expected]] of ([["not_interested", "not_interested"], ["meeting", "meeting"], ["asset_sent", "asset_sent"], ["reply", "replied"]] as const).entries()) {
  test(`status ${expected} outranks every lower status`, () => {
    const chain = (["not_interested", "meeting", "asset_sent", "reply"] as const).slice(index).map((k) => touch(k));
    assert.equal(statusOf(lead(), chain, true, day), expected);
    assert.equal(statusOf(lead(), [touch(kind)], false, day), expected);
  });
}

test("Contacted is a hand-set date; a send tick never changes the stage", () => {
  assert.equal(statusOf(lead(), [touch("sent")], false, day), "new");
  assert.equal(statusOf(lead({ contacted_on: day }), [], false, day), "contacted");
  assert.equal(statusOf(lead({ contacted_on: day }), [touch("reply")], false, day), "replied");
});

test("disqualified wins over everything", () => {
  assert.equal(statusOf(lead({ disqualified: day }), [touch("meeting")], true, day), "disqualified");
});

test("today, no_channel and new follow the batch and the channels", () => {
  assert.equal(statusOf(lead(), [], true, day), "today");
  assert.equal(statusOf(lead({ facebook: null, instagram: null }), [], false, day), "no_channel");
  assert.equal(statusOf(lead(), [], false, day), "new");
  assert.equal(statusOf(lead(), [touch("skipped", "facebook"), touch("skipped", "instagram")], true, day), "new");
  assert.equal(statusOf(lead(), [{ ...touch("not_interested"), lead_id: "someone-else" }], false, day), "new");
  assert.equal(stageOf("today"), "new");
  assert.equal(stageOf("no_channel"), "new");
});

test("done today needs every active channel ticked or skipped on that date", () => {
  assert.equal(doneToday(lead(), [touch("sent")], day), false);
  assert.equal(doneToday(lead(), [touch("sent"), touch("skipped", "instagram")], day), true);
  assert.equal(doneToday(lead(), [touch("sent"), touch("sent", "instagram", "2026-11-04")], day), false);
  assert.equal(doneToday(lead(), [touch("sent"), touch("reply", "instagram")], day), false);
  assert.equal(doneToday(lead({ facebook: null }), [touch("skipped", "instagram")], day), true);
  assert.equal(doneToday(lead({ facebook: null, instagram: null }), [], day), true);
});

test("inactive channels count as missing", () => {
  assert.deepEqual(activeChannels(lead({ facebook: "  " })), ["instagram"]);
  assert.deepEqual(activeChannels(lead({ instagram_inactive: "last post 2023-03-31" })), ["facebook"]);
  assert.equal(statusOf(lead({ facebook: null, instagram_inactive: "no posts" }), [], false, day), "no_channel");
  assert.equal(doneToday(lead({ instagram_inactive: "no posts" }), [touch("sent", "facebook")], day), true);
});

test("the day follows the configured timezone, also around midnight and daylight saving", () => {
  assert.equal(dayIn("Europe/London", new Date("2026-07-01T23:30:00Z")), "2026-07-02");
  assert.equal(dayIn("Europe/London", new Date("2026-11-05T23:30:00Z")), "2026-11-05");
  assert.equal(dayIn("Australia/Sydney", new Date("2026-11-05T14:00:00Z")), "2026-11-06");
  assert.equal(dayIn("America/New_York", new Date("2026-11-05T03:00:00Z")), "2026-11-04");
  assert.equal(shortDay("2026-11-05"), "5 Nov");
  assert.equal(shortDay(null), "—");
});

test("LinkedIn input is normalised and foreign links are rejected", () => {
  assert.equal(linkedinProfile("linkedin.com/in/jane-doe"), "https://www.linkedin.com/in/jane-doe/");
  assert.equal(linkedinProfile("https://uk.linkedin.com/company/acme-roofing/"), "https://www.linkedin.com/company/acme-roofing/");
  assert.equal(linkedinProfile("https://www.linkedin.com/posts/jane_123"), null);
  assert.equal(linkedinProfile("https://www.linkedin.com/in/jane/details"), null);
  assert.equal(linkedinProfile("https://evil.example.test/in/jane"), null);
  assert.equal(linkedinProfile(""), null);
});
