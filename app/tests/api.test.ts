import { test } from "node:test";
import assert from "node:assert/strict";
import { addLead, useTempDb } from "./helpers";
import * as db from "../lib/db";
import { GET as leadGet, PATCH as leadPatch } from "../app/api/leads/[id]/route";
import { POST as touchPost } from "../app/api/touches/route";
import { GET as batchGet, POST as batchPost } from "../app/api/batch/route";
import { POST as bulkPost } from "../app/api/bulk/route";
import { POST as stagePost } from "../app/api/stage/route";
import { POST as viewPost, DELETE as viewDelete } from "../app/api/views/route";

useTempDb({ active_strategies: ["area-question", "opener-offer"] });
const req = (body: unknown, method = "POST") => new Request("http://127.0.0.1:4319/api/test", { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const badJson = () => new Request("http://127.0.0.1:4319/api/test", { method: "POST", body: "{" });
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });

test("PATCH /api/leads/<id> with only an opener works, as a skill would call it", async () => {
  await addLead({ id: "api-1", name: "Api Roofing", instagram: "https://www.instagram.com/api1/", facebook: "https://www.facebook.com/api1.example/", neighbour_town: "Harrowfield" });
  db.updateLead("api-1", { strategy: "opener-offer" });
  assert.equal(db.leadById("api-1")!.missing, "Opener missing");
  const r = await leadPatch(req({ opener: "  love the new van wrap  " }, "PATCH"), ctx("api-1"));
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true });
  assert.equal(db.leadById("api-1")!.opener, "love the new van wrap");
  assert.ok(db.leadById("api-1")!.message!.startsWith("Hey, love the new van wrap"));
});

test("PATCH accepts exactly opener, notes, neighbour_town_manual, linkedin and strategy", async () => {
  for (const body of [{ notes: "n" }, { neighbour_town_manual: "Ashby" }, { linkedin: "linkedin.com/in/x-y" }, { strategy: "trade-offer" }]) {
    assert.equal((await leadPatch(req(body, "PATCH"), ctx("api-1"))).status, 200, JSON.stringify(body));
  }
  for (const body of [null, [], {}, { name: "Renamed" }, { facebook: "https://www.facebook.com/x.example/" }, { notes: 1 }, { opener: false }, { opener: [] }, { strategy: "nope" }, { linkedin: "https://example.test/in/x" }])
    assert.equal((await leadPatch(req(body, "PATCH"), ctx("api-1"))).status, 400, JSON.stringify(body));
  assert.equal((await leadPatch(badJson(), ctx("api-1"))).status, 400);
  assert.equal((await leadPatch(req({ notes: "x" }, "PATCH"), ctx("missing"))).status, 400);
  assert.equal(db.leadById("api-1")!.name, "Api Roofing");
});

test("GET /api/leads/<id> returns the lead with its rendered message and touches; unknown id is 404", async () => {
  const r = await leadGet(new Request("http://127.0.0.1:4319/api/leads/api-1"), ctx("api-1"));
  const body = await r.json();
  assert.equal(body.lead.id, "api-1");
  assert.equal(typeof body.lead.message, "string");
  assert.deepEqual(body.touches, []);
  assert.equal((await leadGet(new Request("http://127.0.0.1:4319/x"), ctx("zzz"))).status, 404);
});

test("POST /api/touches validates input and toggles", async () => {
  const good = { lead_id: "api-1", channel: "facebook", kind: "sent" };
  for (const body of [null, [], {}, { ...good, kind: "bogus" }, { ...good, channel: "whatsapp" }, { ...good, channel: "email" }, { ...good, lead_id: "missing" }, { ...good, lead_id: "" }, { ...good, text: 42 }])
    assert.equal((await touchPost(req(body))).status, 400, JSON.stringify(body));
  assert.equal((await touchPost(badJson())).status, 400);
  assert.deepEqual(await (await touchPost(req(good))).json(), { ok: true, action: "saved" });
  assert.deepEqual(await (await touchPost(req(good))).json(), { ok: true, action: "removed" });
  const reply = await touchPost(req({ ...good, kind: "reply", text: "Yes please" }));
  assert.equal(reply.status, 200);
  assert.equal(db.touchesFor("api-1")[0].text, "Yes please");
});

test("POST /api/batch pulls, GET /api/batch lists who needs an opener", async () => {
  await addLead({ id: "api-2", name: "Needs Opener", instagram: "https://www.instagram.com/api2/", facebook: "https://www.facebook.com/api2.example/" });
  db.updateLead("api-2", { strategy: "opener-offer" });
  for (const body of [null, {}, { count: 0 }, { count: 1.5 }, { count: "5" }]) assert.equal((await batchPost(req(body))).status, 400, JSON.stringify(body));
  const pulled = await (await batchPost(req({ count: 50 }))).json();
  assert.equal(pulled.ok, true);
  assert.ok(pulled.pulled >= 1);
  const list = await (await batchGet()).json();
  assert.match(list.date, /^\d{4}-\d{2}-\d{2}$/);
  const mine = list.leads.find((l: { id: string }) => l.id === "api-2");
  assert.equal(mine.needs_opener, true);
  db.updateLead("api-2", { opener: "nice work on the Elm Road roof" });
  assert.equal((await (await batchGet()).json()).leads.find((l: { id: string }) => l.id === "api-2").needs_opener, false);
});

test("POST /api/bulk and /api/stage validate and act", async () => {
  await addLead({ id: "api-3", facebook: "https://www.facebook.com/api3.example/" });
  for (const body of [null, {}, { lead_ids: [], channel: "facebook" }, { lead_ids: ["api-3"], channel: "x" }, { lead_ids: [1], channel: "facebook" }])
    assert.equal((await bulkPost(req(body))).status, 400, JSON.stringify(body));
  assert.deepEqual(await (await bulkPost(req({ lead_ids: ["api-3"], channel: "facebook" }))).json(), { ok: true, marked: 1, no_channel: 0 });
  for (const body of [null, {}, { lead_ids: ["api-3"], stage: "bogus" }, { restore: [] }, { restore: [{ nonsense: true }] }])
    assert.equal((await stagePost(req(body))).status, 400, JSON.stringify(body));
  const set = await (await stagePost(req({ lead_ids: ["api-3"], stage: "replied" }))).json();
  assert.deepEqual(set.undo, []);
  const down = await (await stagePost(req({ lead_ids: ["api-3"], stage: "new" }))).json();
  assert.equal(down.undo.length, 1);
  assert.deepEqual(await (await stagePost(req({ restore: down.undo }))).json(), { ok: true, restored: 1 });
});

test("POST/DELETE /api/views", async () => {
  for (const body of [null, {}, { name: "x" }, { name: "", view: {} }, { name: "x", view: [] }]) assert.equal((await viewPost(req(body))).status, 400, JSON.stringify(body));
  assert.equal((await viewPost(req({ name: "Mine", view: { search: "roof" } }))).status, 200);
  assert.equal(db.savedViews().length, 1);
  assert.equal((await viewDelete(req({ name: "" }, "DELETE"))).status, 400);
  assert.equal((await viewDelete(req({ name: "Mine" }, "DELETE"))).status, 200);
  assert.equal(db.savedViews().length, 0);
});
