import { DatabaseSync } from "node:sqlite";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { dayIn } from "./date";
import { loadConfig } from "./config";
import { locate } from "./paths";
import { activeStrategies, FALLBACK_STRATEGY, loadStrategies } from "./strategies";
import { competitorsFor, renderMessage } from "./message";
import { activeChannels, doneToday, statusOf } from "./state";
import { countKey, pickStrategy, type Counts } from "./assign";
import { linkedinProfile } from "./linkedin";
import { CHANNELS, KINDS, STAGES, type Channel, type Kind, type Lead, type Stage, type Touch, type Undo } from "./types";
import { normalizeView } from "./table";

const registry = globalThis as typeof globalThis & { outreachConnections?: Map<string, DatabaseSync> };

export function dbPath(): string {
  return resolve(process.env.OUTREACH_DB || resolve(locate().repoRoot, "data/leads.db"));
}
export function today(moment = new Date()): string {
  return dayIn(loadConfig().timezone, moment);
}

export function getDb(): DatabaseSync {
  const path = dbPath();
  registry.outreachConnections ??= new Map();
  let db = registry.outreachConnections.get(path);
  if (!db) {
    mkdirSync(dirname(path), { recursive: true });
    db = new DatabaseSync(path);
    db.exec("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;");
    db.exec(readFileSync(resolve(locate().appDir, "lib/schema.sql"), "utf8"));
    registry.outreachConnections.set(path, db);
  }
  return db;
}
export function closeDb(): void {
  const path = dbPath();
  registry.outreachConnections?.get(path)?.close();
  registry.outreachConnections?.delete(path);
}

function atomic<T>(work: () => T): T {
  const db = getDb();
  if (db.isTransaction) return work();
  db.exec("BEGIN IMMEDIATE");
  try { const result = work(); db.exec("COMMIT"); return result; }
  catch (error) { db.exec("ROLLBACK"); throw error; }
}
const plain = <T>(rows: unknown[]): T[] => rows.map((row) => ({ ...(row as object) })) as T[];

// ---- strategy assignment ---------------------------------------------------------------------------------------
function assignLeads(rows: Lead[]): void {
  if (!rows.length) return;
  const config = loadConfig();
  const set = loadStrategies();
  const active = activeStrategies(config.active_strategies, set);
  const fallback = set.byId.has(FALLBACK_STRATEGY) ? FALLBACK_STRATEGY : active[0]?.id;
  if (!fallback) return;
  const counts: Counts = new Map();
  for (const l of plain<Lead>(getDb().prepare("SELECT * FROM leads WHERE strategy IS NOT NULL").all()))
    counts.set(countKey(activeChannels(l).includes("instagram"), l.strategy!), (counts.get(countKey(activeChannels(l).includes("instagram"), l.strategy!)) ?? 0) + 1);
  const update = getDb().prepare("UPDATE leads SET strategy = ? WHERE id = ? AND strategy IS NULL");
  for (const lead of rows) update.run(pickStrategy({ id: lead.id, has_instagram: activeChannels(lead).includes("instagram") }, active, counts, fallback), lead.id);
}
/** Gives every open lead without a strategy one, balanced by count. Runs on read so the table can show the message. */
function assignOpen(): void {
  const db = getDb();
  const open = plain<Lead>(db.prepare("SELECT * FROM leads WHERE strategy IS NULL AND disqualified IS NULL ORDER BY region COLLATE NOCASE, town COLLATE NOCASE, name COLLATE NOCASE, id").all());
  if (open.length) atomic(() => assignLeads(open));
}

// ---- reads -----------------------------------------------------------------------------------------------------
export function allLeads(): Lead[] {
  assignOpen();
  const rows = plain<Lead>(getDb().prepare("SELECT * FROM leads ORDER BY region COLLATE NOCASE, town COLLATE NOCASE, name COLLATE NOCASE, id").all());
  const config = loadConfig();
  const { byId } = loadStrategies();
  const competitors = competitorsFor(rows);
  return rows.map((lead) => {
    const strategy = lead.strategy ? byId.get(lead.strategy) : undefined;
    const rendered = strategy ? renderMessage(lead, strategy, config, competitors.get(lead.id) ?? null)
      // Disqualified leads never get a strategy; say why instead of a bare "No strategy".
      : { text: null, missing: lead.disqualified ? `Disqualified · ${lead.disqualified}` : lead.strategy ? "Unknown strategy" : "No strategy" };
    return { ...lead, strategy_name: strategy?.name ?? lead.strategy, message: rendered.text, missing: rendered.missing };
  });
}
export function leadById(id: string): Lead | undefined {
  return allLeads().find((l) => l.id === id);
}
export function allTouches(): Touch[] {
  return plain<Touch>(getDb().prepare("SELECT * FROM touches ORDER BY created_at DESC, id DESC").all());
}
export function touchesFor(leadId: string): Touch[] {
  return plain<Touch>(getDb().prepare("SELECT * FROM touches WHERE lead_id = ? ORDER BY created_at DESC, id DESC").all(leadId));
}
export interface BatchEntry { date: string; lead_id: string; position: number }
export function allBatches(): BatchEntry[] {
  return plain<BatchEntry>(getDb().prepare("SELECT date, lead_id, position FROM batches ORDER BY date DESC, position").all());
}
export function todaysBatch(date = today()): Lead[] {
  const byId = new Map(allLeads().map((l) => [l.id, l]));
  return (getDb().prepare("SELECT lead_id FROM batches WHERE date = ? ORDER BY position").all(date) as { lead_id: string }[])
    .flatMap((row) => { const lead = byId.get(row.lead_id); return lead ? [lead] : []; });
}
export function leadCount(): number {
  return (getDb().prepare("SELECT COUNT(*) AS n FROM leads").get() as { n: number }).n;
}

// ---- batch -----------------------------------------------------------------------------------------------------
/** Profiles and the mailbox of one lead, lowercased, as keys for de-duplication. */
function contacts(lead: Lead): string[] {
  return [lead.instagram, lead.facebook, lead.linkedin]
    .map((c) => c?.trim().toLowerCase().replace(/\/+$/, "")).filter((c): c is string => !!c);
}
function groupTouches(touches: Touch[]): Map<string, Touch[]> {
  const map = new Map<string, Touch[]>();
  for (const t of touches) map.set(t.lead_id, [...(map.get(t.lead_id) ?? []), t]);
  return map;
}

export function pullBatch(count: number, date = today()): number {
  if (!Number.isSafeInteger(count) || count < 1) throw new Error("Please enter a positive whole number.");
  return atomic(() => {
    const leads = allLeads();
    const touches = groupTouches(allTouches());
    const inBatch = new Set((getDb().prepare("SELECT lead_id FROM batches WHERE date = ?").all(date) as { lead_id: string }[]).map((r) => r.lead_id));
    const sent = new Set(allTouches().filter((t) => t.kind === "sent").map((t) => t.lead_id));
    // Branches often share one profile or mailbox: whoever is already batched or contacted blocks those contacts for every other row.
    const used = new Set(leads.filter((l) => inBatch.has(l.id) || sent.has(l.id)).flatMap(contacts));
    const picked: Lead[] = [];
    for (const lead of leads) {
      if (picked.length >= count) break;
      if (inBatch.has(lead.id) || sent.has(lead.id)) continue;
      if (statusOf(lead, touches.get(lead.id) ?? [], false, date) !== "new") continue;
      const own = contacts(lead);
      if (own.some((c) => used.has(c))) continue;
      own.forEach((c) => used.add(c));
      picked.push(lead);
    }
    const last = (getDb().prepare("SELECT COALESCE(MAX(position), 0) AS p FROM batches WHERE date = ?").get(date) as { p: number }).p;
    const insert = getDb().prepare("INSERT INTO batches(date, lead_id, position) VALUES (?, ?, ?)");
    picked.forEach((lead, index) => insert.run(date, lead.id, last + index + 1));
    return picked.length;
  });
}

// ---- touches ---------------------------------------------------------------------------------------------------
function ensureStrategy(lead: Lead): string | null {
  if (lead.strategy) return lead.strategy;
  assignLeads([lead]);
  return (getDb().prepare("SELECT strategy FROM leads WHERE id = ?").get(lead.id) as { strategy: string | null }).strategy;
}

/** sent and skipped toggle: the same call on the same day removes the entry again. */
export function writeTouch(leadId: string, channel: Channel, kind: Kind, text: string | null = null, date = today()): "saved" | "removed" {
  return atomic(() => {
    const lead = leadById(leadId);
    if (!lead) throw new Error("Lead not found.");
    if (!activeChannels(lead).includes(channel)) throw new Error("This lead has no active channel of that kind.");
    const db = getDb();
    if (kind === "sent" || kind === "skipped") {
      const existing = db.prepare("SELECT id FROM touches WHERE lead_id = ? AND channel = ? AND kind = ? AND date = ?").get(leadId, channel, kind, date);
      if (existing) {
        db.prepare("DELETE FROM touches WHERE lead_id = ? AND channel = ? AND kind = ? AND date = ?").run(leadId, channel, kind, date);
        return "removed";
      }
    }
    const strategy = kind === "sent" ? ensureStrategy(lead) : null;
    const body = kind === "sent" ? lead.message ?? text : text;
    db.prepare("INSERT INTO touches(lead_id, channel, kind, date, text, created_at, strategy) VALUES (?, ?, ?, ?, ?, ?, ?)")
      .run(leadId, channel, kind, date, body, new Date().toISOString(), strategy);
    return "saved";
  });
}

export interface LeadPatch {
  opener?: string | null; notes?: string | null; neighbour_town_manual?: string | null; linkedin?: string | null; strategy?: string | null;
}
const PATCHABLE = ["opener", "notes", "neighbour_town_manual", "linkedin", "strategy"] as const;

export function updateLead(id: string, patch: LeadPatch): void {
  const lead = leadById(id);
  if (!lead) throw new Error("Lead not found.");
  const values: Record<string, string | null> = {};
  for (const field of PATCHABLE) {
    if (!Object.hasOwn(patch, field)) continue;
    const raw = patch[field];
    if (raw !== null && raw !== undefined && typeof raw !== "string") throw new Error(`${field} must be text.`);
    let value = typeof raw === "string" ? (field === "notes" ? raw : raw.trim()) : null;
    if (field !== "notes" && value === "") value = null;
    if (field === "linkedin" && value !== null) {
      value = linkedinProfile(value);
      if (!value) throw new Error("Please enter a LinkedIn profile like https://www.linkedin.com/in/name/ or /company/name/.");
    }
    if (field === "strategy") {
      if (value === null || !loadStrategies().byId.has(value)) throw new Error("Unknown strategy.");
    }
    values[field] = value;
  }
  const fields = Object.keys(values);
  if (!fields.length) throw new Error("Nothing to change.");
  atomic(() => { getDb().prepare(`UPDATE leads SET ${fields.map((f) => `${f} = ?`).join(", ")} WHERE id = ?`).run(...fields.map((f) => values[f]), id); });
}

// ---- views -----------------------------------------------------------------------------------------------------
export interface SavedView { name: string; json: string }
export function savedViews(): SavedView[] {
  return plain<SavedView>(getDb().prepare("SELECT name, json FROM views ORDER BY name COLLATE NOCASE").all());
}
function viewName(name: unknown): string {
  if (typeof name !== "string" || !name.trim() || name.trim().length > 80) throw new Error("Please enter a view name of 1 to 80 characters.");
  return name.trim();
}
export function saveView(name: unknown, view: unknown): void {
  const clean = viewName(name);
  if (!view || typeof view !== "object" || Array.isArray(view)) throw new Error("The view must be an object.");
  const json = JSON.stringify(normalizeView(view));
  if (json.length > 100_000) throw new Error("The view is too large.");
  getDb().prepare("INSERT INTO views(name, json) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET json = excluded.json").run(clean, json);
}
export function deleteView(name: unknown): void {
  getDb().prepare("DELETE FROM views WHERE name = ?").run(viewName(name));
}

// ---- stages ----------------------------------------------------------------------------------------------------
const STAGE_KIND: Record<"replied" | "asset_sent" | "meeting" | "not_interested", Kind> = {
  replied: "reply", asset_sent: "asset_sent", meeting: "meeting", not_interested: "not_interested",
};
const STAGE_KINDS: Kind[] = ["reply", "asset_sent", "meeting", "not_interested"];

function leadIds(ids: unknown): string[] {
  if (!Array.isArray(ids) || !ids.length || ids.length > 10_000 || ids.some((id) => typeof id !== "string" || !id))
    throw new Error("Please select at least one valid lead.");
  return [...new Set(ids as string[])];
}

/** Stage entries need a channel: the one used last for sending, else the first active one. */
function stageChannel(lead: Lead): Channel | undefined {
  const active = activeChannels(lead);
  const lastSent = touchesFor(lead.id).find((t) => t.kind === "sent" && active.includes(t.channel));
  return lastSent?.channel ?? active[0];
}

export function setStage(ids: unknown, stage: unknown, date = today()): { undo: Undo[] } {
  const list = leadIds(ids);
  if (!STAGES.includes(stage as Stage)) throw new Error("Please choose a valid stage.");
  return atomic(() => {
    const undo: Undo[] = [];
    const db = getDb();
    for (const id of list) {
      const lead = leadById(id);
      if (!lead) throw new Error("Lead not found.");
      if (stage === "disqualified") { db.prepare("UPDATE leads SET disqualified = ? WHERE id = ?").run(date, id); continue; }
      // Disqualified belongs to the lead, not a channel; New lifts it first.
      if (lead.disqualified) {
        db.prepare("UPDATE leads SET disqualified = NULL WHERE id = ?").run(id);
        if (stage === "new") continue;
      }
      if (stage === "new") {
        const last = db.prepare(`SELECT * FROM touches WHERE lead_id = ? AND kind IN (${STAGE_KINDS.map(() => "?").join(",")}) ORDER BY id DESC LIMIT 1`)
          .get(id, ...STAGE_KINDS) as unknown as Touch | undefined;
        if (last) { undo.push({ ...last }); db.prepare("DELETE FROM touches WHERE id = ?").run(last.id); continue; }
        // No stage entry left: New withdraws the Contacted date. Send ticks stay.
        if (lead.contacted_on) {
          undo.push({ lead_id: id, contacted_on: lead.contacted_on });
          db.prepare("UPDATE leads SET contacted_on = NULL WHERE id = ?").run(id);
        }
        continue;
      }
      // Contacted is only a stage date; counting happens through the channel ticks.
      if (stage === "contacted") { db.prepare("UPDATE leads SET contacted_on = COALESCE(contacted_on, ?) WHERE id = ?").run(date, id); continue; }
      const channel = stageChannel(lead);
      if (!channel) throw new Error("This lead has no active channel.");
      db.prepare("INSERT INTO touches(lead_id, channel, kind, date, text, created_at) VALUES (?, ?, ?, ?, NULL, ?)")
        .run(id, channel, STAGE_KIND[stage as keyof typeof STAGE_KIND], date, new Date().toISOString());
    }
    return { undo };
  });
}

const isDay = (v: unknown): v is string => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T12:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
};
function validUndo(value: unknown): value is Undo {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  if (Object.hasOwn(value, "contacted_on")) {
    const c = value as { lead_id: unknown; contacted_on: unknown };
    return typeof c.lead_id === "string" && !!c.lead_id && isDay(c.contacted_on);
  }
  const t = value as Touch;
  return Number.isSafeInteger(t.id) && t.id > 0 && typeof t.lead_id === "string" && !!t.lead_id && CHANNELS.includes(t.channel) &&
    STAGE_KINDS.includes(t.kind) && isDay(t.date) && (t.text === null || typeof t.text === "string") &&
    typeof t.created_at === "string" && !Number.isNaN(Date.parse(t.created_at)) && (t.strategy === null || t.strategy === undefined || typeof t.strategy === "string");
}

export function restoreStages(entries: unknown): number {
  if (!Array.isArray(entries) || !entries.length || entries.length > 10_000 || !entries.every(validUndo)) throw new Error("The entries to restore are invalid.");
  return atomic(() => {
    let restored = 0;
    const db = getDb();
    for (const entry of entries as Undo[]) {
      if (!leadById(entry.lead_id)) throw new Error("Lead not found.");
      if ("contacted_on" in entry) {
        restored += Number(db.prepare("UPDATE leads SET contacted_on = ? WHERE id = ? AND contacted_on IS NULL").run(entry.contacted_on, entry.lead_id).changes);
        continue;
      }
      const again = db.prepare("SELECT id FROM touches WHERE lead_id = ? AND channel = ? AND kind = ? AND date = ? AND text IS ? AND created_at = ?")
        .get(entry.lead_id, entry.channel, entry.kind, entry.date, entry.text, entry.created_at);
      if (again) continue;
      // SQLite may have reused the deleted maximum id; never overwrite the newer record.
      const taken = db.prepare("SELECT id FROM touches WHERE id = ?").get(entry.id);
      if (taken) db.prepare("INSERT INTO touches(lead_id, channel, kind, date, text, created_at, strategy) VALUES (?, ?, ?, ?, ?, ?, ?)")
        .run(entry.lead_id, entry.channel, entry.kind, entry.date, entry.text, entry.created_at, entry.strategy ?? null);
      else db.prepare("INSERT INTO touches(id, lead_id, channel, kind, date, text, created_at, strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        .run(entry.id, entry.lead_id, entry.channel, entry.kind, entry.date, entry.text, entry.created_at, entry.strategy ?? null);
      restored++;
    }
    return restored;
  });
}

/** Bulk "mark sent on a channel". Leads without that active channel are counted and skipped. */
export function bulkMarkSent(ids: unknown, channel: unknown, date = today()): { marked: number; no_channel: number } {
  const list = leadIds(ids);
  if (!CHANNELS.includes(channel as Channel)) throw new Error("Please choose a valid channel.");
  const ch = channel as Channel;
  return atomic(() => {
    let marked = 0, noChannel = 0;
    for (const id of list) {
      const lead = leadById(id);
      if (!lead) throw new Error("Lead not found.");
      if (!activeChannels(lead).includes(ch)) { noChannel++; continue; }
      const exists = getDb().prepare("SELECT id FROM touches WHERE lead_id = ? AND channel = ? AND kind = 'sent' AND date = ?").get(id, ch, date);
      if (exists) continue;
      const strategy = ensureStrategy(lead);
      getDb().prepare("INSERT INTO touches(lead_id, channel, kind, date, text, created_at, strategy) VALUES (?, ?, 'sent', ?, ?, ?, ?)")
        .run(id, ch, date, lead.message ?? null, new Date().toISOString(), strategy);
      marked++;
    }
    return { marked, no_channel: noChannel };
  });
}

export { KINDS, doneToday };
