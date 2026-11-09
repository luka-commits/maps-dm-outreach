import { test } from "node:test";
import assert from "node:assert/strict";
import { addLead, DAY, useTempDb } from "./helpers";

useTempDb({ active_strategies: ["area-question", "opener-offer"] });
import * as db from "../lib/db";
const ig = (n: string) => `https://www.instagram.com/${n}/`;

test("schema is created, leads read back as plain objects, sorted by region, town, name", async () => {
  await addLead({ id: "s1", name: "Zed Roofing", town: "Millbrook", facebook: "https://www.facebook.com/z.example/" });
  await addLead({ id: "s2", name: "Alpha Roofing", town: "Millbrook", facebook: "https://www.facebook.com/a.example/" });
  await addLead({ id: "s0", name: "Mid Roofing", town: "Harrowfield", facebook: "https://www.facebook.com/m.example/" });
  const leads = db.allLeads();
  assert.deepEqual(leads.map((l) => l.id), ["s0", "s2", "s1"]);
  for (const l of leads) assert.equal(Object.getPrototypeOf(l), Object.prototype);
  assert.equal(db.leadById("nope"), undefined);
  assert.equal(db.leadCount(), 3);
});

test("strategy assignment: balanced among active strategies, opener strategies only for leads with Instagram", async () => {
  const ids: string[] = [];
  for (let i = 0; i < 6; i++) ids.push(await addLead({ id: `ig${i}`, instagram: ig(`ig${i}`), town: "Assignville" }));
  for (let i = 0; i < 4; i++) ids.push(await addLead({ id: `em${i}`, facebook: `https://www.facebook.com/e${i}.example/`, town: "Assignville" }));
  const leads = db.allLeads();
  const strategyOf = (id: string) => leads.find((l) => l.id === id)!.strategy;
  const withIg = ids.slice(0, 6).map(strategyOf);
  assert.equal(withIg.filter((s) => s === "opener-offer").length, 3);
  assert.equal(withIg.filter((s) => s === "area-question").length, 3);
  for (const id of ids.slice(6)) assert.equal(strategyOf(id), "area-question");
  // Stable: a second read assigns nothing new.
  assert.deepEqual(db.allLeads().map((l) => l.strategy), leads.map((l) => l.strategy));
});

test("a lead whose strategy is switched in the drawer keeps the new one, any defined strategy works, unknown ones are refused", async () => {
  const id = await addLead({ id: "sw", facebook: "https://www.facebook.com/sw.example/", opener: "nice van" });
  db.updateLead(id, { strategy: "trade-offer" });
  assert.equal(db.leadById(id)!.strategy, "trade-offer");
  assert.equal(db.leadById(id)!.strategy_name, "Post comment + upfront audit offer");
  assert.ok(db.leadById(id)!.message!.includes("i help roofers"));
  assert.throws(() => db.updateLead(id, { strategy: "nope" }), /Unknown strategy/);
  assert.throws(() => db.updateLead(id, { strategy: null }), /Unknown strategy/);
});

test("missing required fields show up as the message instead of text", async () => {
  const id = await addLead({ id: "miss", facebook: "https://www.facebook.com/m.example/", neighbour_town: null });
  db.updateLead(id, { strategy: "area-question" });
  assert.equal(db.leadById(id)!.message, null);
  assert.equal(db.leadById(id)!.missing, "Neighbour town missing");
  db.updateLead(id, { neighbour_town_manual: "  Ashby " });
  assert.equal(db.leadById(id)!.message, "Hi, do you also cover Ashby?");
  db.updateLead(id, { strategy: "opener-offer" });
  assert.equal(db.leadById(id)!.missing, "Opener missing");
  db.updateLead(id, { opener: "  great reviews  " });
  assert.equal(db.leadById(id)!.opener, "great reviews");
  db.updateLead(id, { opener: "   " });
  assert.equal(db.leadById(id)!.opener, null);
});

test("hand fields: notes keep their text, LinkedIn is normalised and validated, unknown fields are refused", async () => {
  const id = await addLead({ id: "hand", facebook: "https://www.facebook.com/h.example/" });
  db.updateLead(id, { notes: "Call back  Friday\nask about quote" });
  assert.equal(db.leadById(id)!.notes, "Call back  Friday\nask about quote");
  db.updateLead(id, { linkedin: "linkedin.com/in/dan-w" });
  assert.equal(db.leadById(id)!.linkedin, "https://www.linkedin.com/in/dan-w/");
  assert.throws(() => db.updateLead(id, { linkedin: "https://example.test/in/dan" }), /LinkedIn/);
  db.updateLead(id, { linkedin: "" });
  assert.equal(db.leadById(id)!.linkedin, null);
  assert.throws(() => db.updateLead(id, {}), /Nothing to change/);
  assert.throws(() => db.updateLead("missing", { notes: "x" }), /not found/);
  assert.throws(() => db.updateLead(id, { notes: 5 as unknown as string }), /text/);
});

test("send tick snapshots the strategy and the rendered text, the same call on the same day undoes it", async () => {
  const id = await addLead({ id: "tick", facebook: "https://www.facebook.com/t.example/", neighbour_town: "Harrowfield" });
  db.updateLead(id, { strategy: "area-question" });
  assert.equal(db.writeTouch(id, "facebook", "sent", null, DAY), "saved");
  const [sent] = db.touchesFor(id);
  assert.equal(sent.strategy, "area-question");
  assert.equal(sent.text, "Hi, do you also cover Harrowfield?");
  // Switching afterwards does not rewrite history.
  db.updateLead(id, { strategy: "trade-offer" });
  assert.equal(db.touchesFor(id)[0].strategy, "area-question");
  assert.equal(db.writeTouch(id, "facebook", "sent", null, DAY), "removed");
  assert.equal(db.touchesFor(id).length, 0);
  assert.equal(db.writeTouch(id, "facebook", "skipped", null, DAY), "saved");
  assert.equal(db.writeTouch(id, "facebook", "sent", null, DAY), "saved");
  assert.deepEqual(db.touchesFor(id).map((t) => t.kind).sort(), ["sent", "skipped"]);
  assert.equal(db.writeTouch(id, "facebook", "skipped", null, DAY), "removed");
  assert.throws(() => db.writeTouch(id, "instagram", "sent", null, DAY), /no active channel/);
  assert.throws(() => db.writeTouch("missing", "facebook", "sent", null, DAY), /not found/);
});

test("an inactive channel cannot be ticked", async () => {
  const id = await addLead({ id: "dead", instagram: ig("dead"), facebook: "https://www.facebook.com/d.example/", instagram_inactive: "last post 2023-08-17" });
  assert.throws(() => db.writeTouch(id, "instagram", "sent", null, DAY), /no active channel/);
});

test("batch pull: only New leads, never already sent, today's batch is not pulled twice, branches sharing a profile or mailbox get one DM", async () => {
  const pre = db.leadCount();
  await addLead({ id: "b-main", name: "Branch Main", town: "Batchton", instagram: ig("shared"), facebook: "https://www.facebook.com/main.example/" });
  await addLead({ id: "b-second", name: "Branch Second", town: "Batchton", instagram: ig("shared/"), facebook: "https://www.facebook.com/second.example/" });
  await addLead({ id: "b-mail", name: "Branch Zmail", town: "Batchton", facebook: "https://www.facebook.com/MAIN.example/" });
  await addLead({ id: "b-solo", name: "Solo", town: "Batchton", facebook: "https://www.facebook.com/solo.example/" });
  await addLead({ id: "b-sent", name: "Sent Before", town: "Batchton", facebook: "https://www.facebook.com/old.example/" });
  await addLead({ id: "b-replied", name: "Replied", town: "Batchton", facebook: "https://www.facebook.com/replied.example/" });
  await addLead({ id: "b-dq", name: "Disqualified", town: "Batchton", facebook: "https://www.facebook.com/dq.example/", disqualified: "2026-11-01" });
  await addLead({ id: "b-none", name: "No Channel", town: "Batchton" });
  await addLead({ id: "b-contacted", name: "Contacted", town: "Batchton", facebook: "https://www.facebook.com/c.example/", contacted_on: "2026-11-01" });
  db.writeTouch("b-sent", "facebook", "sent", null, "2026-11-02");
  db.writeTouch("b-replied", "facebook", "reply", null, "2026-11-02");
  assert.ok(db.leadCount() > pre);
  const date = "2026-11-10";
  // Pull only inside Batchton by choosing a large count, then check membership.
  const pulled = db.pullBatch(1000, date);
  const batch = (db.getDb().prepare("SELECT lead_id FROM batches WHERE date = ?").all(date) as { lead_id: string }[]).map((r) => r.lead_id);
  assert.equal(batch.length, pulled);
  assert.ok(batch.includes("b-main"));
  assert.ok(!batch.includes("b-second"), "shares an Instagram profile with b-main");
  assert.ok(!batch.includes("b-mail"), "shares a mailbox with b-main (case-insensitive)");
  assert.ok(batch.includes("b-solo"));
  for (const blocked of ["b-sent", "b-replied", "b-dq", "b-none", "b-contacted"]) assert.ok(!batch.includes(blocked), blocked);
  assert.equal(db.pullBatch(1000, date), 0, "pulling again adds nobody");
  assert.deepEqual(db.todaysBatch(date).map((l) => l.id).filter((id) => id.startsWith("b-")), batch.filter((id) => id.startsWith("b-")));
  assert.throws(() => db.pullBatch(0, date), /positive whole/);
  assert.throws(() => db.pullBatch(1.5, date), /positive whole/);
});

test("pull respects the requested count and the order", async () => {
  const date = "2026-11-11";
  const n = db.pullBatch(2, date);
  assert.equal(n, 2);
  const positions = db.getDb().prepare("SELECT position FROM batches WHERE date = ? ORDER BY position").all(date) as { position: number }[];
  assert.deepEqual(positions.map((p) => p.position), [1, 2]);
  assert.equal(db.pullBatch(1, date), 1);
  assert.equal((db.getDb().prepare("SELECT MAX(position) AS m FROM batches WHERE date = ?").get(date) as { m: number }).m, 3);
});
