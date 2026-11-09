import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { locate } from "./paths";
import { CHANNELS, type Channel } from "./types";

export interface Config {
  sender_name: string;
  timezone: string;
  offer: { service: string; promise: string };
  active_strategies: string[];
  daily_limits: Record<Channel, number | null>;
  app_port: number;
}

const FALLBACK: Config = {
  sender_name: "Alex", timezone: "Europe/London",
  offer: { service: "Google Business Profile optimisation", promise: "ten new jobs in 60 days, free for you" },
  active_strategies: ["area-question", "opener-offer"],
  daily_limits: { instagram: 30, facebook: 15, linkedin: 20 },
  app_port: 4319,
};

function readJson(file: string): Record<string, any> | null {
  try { return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null; } catch { return null; }
}
const validZone = (zone: unknown): zone is string => {
  if (typeof zone !== "string" || !zone) return false;
  try { new Intl.DateTimeFormat("en", { timeZone: zone }); return true; } catch { return false; }
};

/** User settings over the shipped example over built-in defaults. Re-read on every call; the files are tiny. */
export function loadConfig(): Config {
  const root = locate().repoRoot;
  const example = readJson(resolve(root, "outreach.config.example.json")) ?? {};
  const user = readJson(process.env.OUTREACH_CONFIG || resolve(root, "outreach.config.json")) ?? {};
  const pick = (key: string) => user[key] ?? example[key];
  const limits: Record<Channel, number | null> = { ...FALLBACK.daily_limits };
  for (const c of CHANNELS) {
    const value = user.daily_limits?.[c] !== undefined ? user.daily_limits[c] : example.daily_limits?.[c];
    if (value === null) limits[c] = null;
    else if (typeof value === "number" && value > 0) limits[c] = value;
  }
  const port = Number(pick("app_port"));
  const strategies = pick("active_strategies");
  return {
    sender_name: typeof pick("sender_name") === "string" && pick("sender_name") ? pick("sender_name") : FALLBACK.sender_name,
    timezone: validZone(pick("timezone")) ? pick("timezone") : validZone(example.timezone) ? example.timezone : FALLBACK.timezone,
    offer: {
      service: user.offer?.service ?? example.offer?.service ?? FALLBACK.offer.service,
      promise: user.offer?.promise ?? example.offer?.promise ?? FALLBACK.offer.promise,
    },
    active_strategies: Array.isArray(strategies) && strategies.length ? strategies.filter((s: unknown) => typeof s === "string") : FALLBACK.active_strategies,
    daily_limits: limits,
    app_port: Number.isInteger(port) && port > 0 && port < 65536 ? port : FALLBACK.app_port,
  };
}
