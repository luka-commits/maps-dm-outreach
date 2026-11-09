import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { locate } from "./paths";

export interface Strategy {
  id: string; name: string; summary: string; needs_opener: boolean;
  requires: string[]; template: string; follow_up?: string;
}
export interface StrategySet { list: Strategy[]; byId: Map<string, Strategy> }

export const FALLBACK_STRATEGY = "area-question";
let cache: { file: string; mtime: number; set: StrategySet } | undefined;

export function strategiesFile(): string {
  return process.env.OUTREACH_STRATEGIES || resolve(locate().repoRoot, "strategies/strategies.json");
}

export function loadStrategies(): StrategySet {
  const file = strategiesFile();
  const mtime = statSync(file).mtimeMs;
  if (cache && cache.file === file && cache.mtime === mtime) return cache.set;
  const raw = JSON.parse(readFileSync(file, "utf8"));
  const list: Strategy[] = (Array.isArray(raw.strategies) ? raw.strategies : [])
    .filter((s: any) => s && typeof s.id === "string" && typeof s.template === "string")
    .map((s: any) => ({
      id: s.id, name: String(s.name ?? s.id), summary: String(s.summary ?? ""), needs_opener: s.needs_opener === true,
      requires: Array.isArray(s.requires) ? s.requires.map(String) : [], template: s.template,
      follow_up: typeof s.follow_up === "string" ? s.follow_up : undefined,
    }));
  const set = { list, byId: new Map(list.map((s) => [s.id, s])) };
  cache = { file, mtime, set };
  return set;
}

/** Active strategies in config order; unknown ids are ignored. Falls back to the fallback strategy alone. */
export function activeStrategies(ids: string[], set = loadStrategies()): Strategy[] {
  const active = ids.map((id) => set.byId.get(id)).filter((s): s is Strategy => !!s);
  if (active.length) return active;
  const fallback = set.byId.get(FALLBACK_STRATEGY);
  return fallback ? [fallback] : set.list.slice(0, 1);
}
