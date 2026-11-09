import { test } from "node:test";
import assert from "node:assert/strict";
import { addLead, DAY, useTempDb } from "./helpers";
import { statusOf } from "../lib/state";

useTempDb();
import * as db from "../lib/db";
const statusFor = (id: string) => statusOf(db.leadById(id)!, db.touchesFor(id), false, DAY);

test("stages write the stage entry on the channel last used for sending, else the first active one", async () => {
  const id = await addLead({ id: "st1", instagram: "https://www.instagram.com/st1/", facebook: "https://www.facebook.com/st1.example/" });
  db.setStage([id], "replied", DAY);
  assert.equal(db.touchesFor(id)[0].channel, "instagram");
  const other = await addLead({ id: "st2", instagram: "https://www.instagram.com/st2/", facebook: "https://www.facebook.com/st2.example/" });
  db.writeTouch(other, "facebook", "sent", null, DAY);
  db.setStage([other], "meeting", DAY);
  assert.equal(db.touchesFor(other)[0].channel, "facebook");
  assert.equal(db.touchesFor(other)[0].kind, "meeting");
  assert.equal(statusFor(other), "meeting");
});

test("Contacted sets a date only and keeps the first date; ticks never change the stage", async () => {
  const id = await addLead({ id: "ct", facebook: "https://www.facebook.com/ct.example/" });
  db.writeTouch(id, "facebook", "sent", null, DAY);
  assert.equal(statusFor(id), "new");
  db.setStage([id], "contacted", DAY);
  db.setStage([id], "contacted", "2026-11-09");
  assert.equal(db.leadById(id)!.contacted_on, DAY);
  assert.equal(db.touchesFor(id).filter((t) => t.kind !== "sent").length, 0);
  assert.equal(statusFor(id), "contacted");
});

test("New removes the last stage entry, else the Contacted date; send ticks stay; Undo restores", async () => {
  const id = await addLead({ id: "nw", instagram: "https://www.instagram.com/nw/", facebook: "https://www.facebook.com/nw.example/" });
  db.writeTouch(id, "instagram", "sent", null, DAY);
  db.writeTouch(id, "facebook", "skipped", null, DAY);
  db.setStage([id], "contacted", DAY);
  db.setStage([id], "replied", DAY);
  db.setStage([id], "asset_sent", DAY);
  const before = db.touchesFor(id);
  const { undo } = db.setStage([id], "new", DAY);
  assert.equal(undo.length, 1);
  assert.deepEqual(undo[0], before.find((t) => t.kind === "asset_sent"));
  assert.equal(statusFor(id), "replied");
  // SQLite may reuse the freed id: a new entry must not be overwritten by the restore.
  db.setStage([id], "meeting", DAY);
  assert.equal(db.restoreStages(undo), 1);
  assert.equal(db.restoreStages(undo), 0, "restoring twice is idempotent");
  const after = db.touchesFor(id);
  assert.equal(after.filter((t) => t.kind === "asset_sent").length, 1);
  assert.equal(after.filter((t) => t.kind === "meeting").length, 1);
  assert.equal(statusFor(id), "meeting");
  // Peel everything down to the Contacted date.
  db.setStage([id], "new", DAY); db.setStage([id], "new", DAY); db.setStage([id], "new", DAY);
  assert.equal(statusFor(id), "contacted");
  const last = db.setStage([id], "new", DAY);
  assert.deepEqual(last.undo, [{ lead_id: id, contacted_on: DAY }]);
  assert.equal(db.leadById(id)!.contacted_on, null);
  assert.equal(db.touchesFor(id).filter((t) => t.kind === "sent").length, 1, "send ticks stay");
  assert.equal(db.restoreStages(last.undo), 1);
  assert.equal(db.leadById(id)!.contacted_on, DAY);
  assert.equal(db.setStage([id], "new", DAY).undo.length, 1);
  assert.equal(db.setStage([id], "new", DAY).undo.length, 0, "nothing left to withdraw");
});

test("Disqualified belongs to the lead; New lifts it first", async () => {
  const id = await addLead({ id: "dq", facebook: "https://www.facebook.com/dq.example/" });
  db.setStage([id], "replied", DAY);
  db.setStage([id], "disqualified", DAY);
  assert.equal(statusFor(id), "disqualified");
  db.setStage([id], "new", DAY);
  assert.equal(db.leadById(id)!.disqualified, null);
  assert.equal(statusFor(id), "replied", "the entry survives; only the disqualification was lifted");
  db.setStage([id], "disqualified", DAY);
  db.setStage([id], "contacted", DAY);
  assert.equal(db.leadById(id)!.disqualified, null);
});

test("bulk stage change is atomic and refuses invalid input", async () => {
  const a = await addLead({ id: "bk-a", facebook: "https://www.facebook.com/bka.example/" });
  const noChannel = await addLead({ id: "bk-n" });
  assert.throws(() => db.setStage([a, noChannel], "replied", DAY), /no active channel/);
  assert.equal(db.touchesFor(a).length, 0, "rolled back as a whole");
  assert.throws(() => db.setStage([], "replied", DAY), /at least one/);
  assert.throws(() => db.setStage([a], "bogus", DAY), /valid stage/);
  assert.throws(() => db.setStage(["missing"], "contacted", DAY), /not found/);
});

test("restore refuses malformed entries", async () => {
  const id = await addLead({ id: "rs", facebook: "https://www.facebook.com/rs.example/" });
  db.setStage([id], "replied", DAY);
  const { undo } = db.setStage([id], "new", DAY);
  const entry = undo[0] as { kind: string };
  assert.throws(() => db.restoreStages([{ ...entry, kind: "sent" }]), /invalid/);
  assert.throws(() => db.restoreStages([{ ...entry, date: "2026-02-31" }]), /invalid/);
  assert.throws(() => db.restoreStages([]), /invalid/);
  assert.throws(() => db.restoreStages("x"), /invalid/);
});

test("bulk mark sent is idempotent, counts leads without the channel, stage stays unchanged", async () => {
  const a = await addLead({ id: "bm-a", instagram: "https://www.instagram.com/bma/", facebook: "https://www.facebook.com/bma.example/" });
  const b = await addLead({ id: "bm-b", facebook: "https://www.facebook.com/bmb.example/" });
  const dead = await addLead({ id: "bm-d", instagram: "https://www.instagram.com/bmd/", instagram_inactive: "no posts" });
  assert.deepEqual(db.bulkMarkSent([a, b, dead], "instagram", DAY), { marked: 1, no_channel: 2 });
  assert.deepEqual(db.bulkMarkSent([a, b, dead], "instagram", DAY), { marked: 0, no_channel: 2 });
  assert.equal(db.touchesFor(a).length, 1);
  assert.equal(db.touchesFor(a)[0].strategy !== null, true);
  assert.equal(statusFor(a), "new");
  assert.throws(() => db.bulkMarkSent([a], "whatsapp", DAY), /valid channel/);
  assert.throws(() => db.bulkMarkSent([a, "missing"], "facebook", DAY), /not found/);
  assert.equal(db.touchesFor(a).filter((t) => t.channel === "facebook").length, 0, "failed bulk rolled back");
});

test("saved views are stored normalised, listed by name, replaced on the same name and deletable", async () => {
  db.saveView("Millbrook with Facebook", { search: "mill", columns: ["name", "bogus", "facebook"], filters: { facebook: { kind: "boolean", value: "yes" }, bogus: { kind: "text", value: "x" } } });
  db.saveView("Another", { stage: "replied" });
  assert.deepEqual(db.savedViews().map((v) => v.name), ["Another", "Millbrook with Facebook"]);
  const stored = JSON.parse(db.savedViews()[1].json);
  assert.deepEqual(stored.columns, ["name", "facebook"]);
  assert.deepEqual(Object.keys(stored.filters), ["facebook"]);
  assert.equal(stored.search, "mill");
  db.saveView("Another", { stage: "meeting" });
  assert.equal(JSON.parse(db.savedViews()[0].json).stage, "meeting");
  assert.equal(db.savedViews().length, 2);
  assert.throws(() => db.saveView("", {}), /view name/);
  assert.throws(() => db.saveView("x".repeat(81), {}), /view name/);
  assert.throws(() => db.saveView("ok", [] as unknown as object), /object/);
  db.deleteView("Another");
  assert.deepEqual(db.savedViews().map((v) => v.name), ["Millbrook with Facebook"]);
});
