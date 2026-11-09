import { test } from "node:test";
import assert from "node:assert/strict";
import { pickStrategy, type Counts } from "../lib/assign";
import type { Strategy } from "../lib/strategies";

const s = (id: string, needs_opener: boolean): Strategy => ({ id, name: id, summary: "", needs_opener, requires: [], template: "x" });
const active = [s("area-question", false), s("opener-offer", true)];

test("leads with Instagram alternate between the active strategies, leads without only get non-opener strategies", () => {
  const counts: Counts = new Map();
  const withIg = Array.from({ length: 6 }, (_, i) => pickStrategy({ id: `a${i}`, has_instagram: true }, active, counts, "area-question"));
  assert.deepEqual(withIg, ["area-question", "opener-offer", "area-question", "opener-offer", "area-question", "opener-offer"]);
  const without = Array.from({ length: 4 }, (_, i) => pickStrategy({ id: `b${i}`, has_instagram: false }, active, counts, "area-question"));
  assert.deepEqual(without, Array(4).fill("area-question"));
});

test("groups stay balanced independently, so the Instagram split is not skewed by leads without Instagram", () => {
  const counts: Counts = new Map();
  for (let i = 0; i < 10; i++) pickStrategy({ id: `n${i}`, has_instagram: false }, active, counts, "area-question");
  const picks = Array.from({ length: 10 }, (_, i) => pickStrategy({ id: `i${i}`, has_instagram: true }, active, counts, "area-question"));
  assert.equal(picks.filter((p) => p === "opener-offer").length, 5);
});

test("with three active strategies the least used wins, ties go in config order", () => {
  const three = [s("a", false), s("b", false), s("c", false)];
  const counts: Counts = new Map();
  const picks = Array.from({ length: 7 }, (_, i) => pickStrategy({ id: String(i), has_instagram: false }, three, counts, "a"));
  assert.deepEqual(picks, ["a", "b", "c", "a", "b", "c", "a"]);
});

test("when no active strategy fits, the lead gets the fallback", () => {
  const onlyOpener = [s("opener-offer", true)];
  assert.equal(pickStrategy({ id: "x", has_instagram: false }, onlyOpener, new Map(), "area-question"), "area-question");
  assert.equal(pickStrategy({ id: "y", has_instagram: true }, onlyOpener, new Map(), "area-question"), "opener-offer");
});
