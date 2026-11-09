import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { after } from "node:test";
import type { Lead } from "../lib/types";

/** Points the app at a throwaway database and config; call once at the top of a test file. */
export function useTempDb(config: Record<string, unknown> = {}) {
  const dir = mkdtempSync(resolve(tmpdir(), "outreach-test-"));
  process.env.OUTREACH_DB = resolve(dir, "test.db");
  const configFile = resolve(dir, "config.json");
  writeFileSync(configFile, JSON.stringify({ timezone: "Europe/London", ...config }));
  process.env.OUTREACH_CONFIG = configFile;
  after(async () => { (await import("../lib/db")).closeDb(); rmSync(dir, { recursive: true, force: true }); });
  return dir;
}

let counter = 0;
/** Inserts an invented lead; unspecified fields are blank. */
export async function addLead(fields: Partial<Lead> & { id?: string } = {}): Promise<string> {
  const { getDb } = await import("../lib/db");
  counter++;
  const row: Record<string, unknown> = {
    id: `lead-${counter}`, name: `Test Business ${counter}`, town: "Millbrook", region: "Northshire", country: "GB", niche: "roofer",
    imported_at: "2026-11-01T09:00:00Z", ...fields,
  };
  const keys = Object.keys(row);
  getDb().prepare(`INSERT INTO leads(${keys.join(",")}) VALUES (${keys.map(() => "?").join(",")})`).run(...(keys.map((k) => row[k]) as never[]));
  return row.id as string;
}
export const DAY = "2026-11-05";
