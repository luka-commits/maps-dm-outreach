import { dayIn } from "./date";
import { statusOf, stageOf, activeChannels } from "./state";
import { STAGES, STAGE_LABEL, type Lead, type Status, type Touch } from "./types";

export type ColumnFilterKind = "text" | "multi" | "boolean" | "range" | "date";
export const COLUMNS = [
  { id: "name", label: "Business", width: 190, filter: "text" },
  { id: "town", label: "Town", width: 110, filter: "multi" },
  { id: "neighbour_town", label: "Neighbour town", width: 125, filter: "multi" },
  { id: "owner_name", label: "Owner", width: 150, filter: "text" },
  { id: "instagram", label: "Instagram", width: 140, filter: "boolean" },
  { id: "facebook", label: "Facebook", width: 140, filter: "boolean" },
  { id: "linkedin", label: "LinkedIn", width: 140, filter: "boolean" },
  { id: "website", label: "Website", width: 180, filter: "boolean" },
  { id: "strategy", label: "Strategy", width: 135, filter: "multi" },
  { id: "message", label: "Message", width: 270, filter: "text" },
  { id: "stage", label: "Stage", width: 130, filter: "multi" },
  { id: "last_contact", label: "Last contact", width: 105, filter: "date" },
  { id: "sent_text", label: "Last sent text", width: 260, filter: "text" },
  { id: "region", label: "Region", width: 150, filter: "multi" },
  { id: "category", label: "Category", width: 170, filter: "multi" },
  { id: "niche", label: "Niche", width: 120, filter: "multi" },
  { id: "phone", label: "Phone", width: 140, filter: "boolean" },
  { id: "rating", label: "Rating", width: 100, filter: "range" },
  { id: "reviews", label: "Reviews", width: 100, filter: "range" },
  { id: "notes", label: "Notes", width: 220, filter: "text" },
  { id: "in_batch_since", label: "In batch since", width: 130, filter: "date" },
  { id: "imported_at", label: "Imported", width: 120, filter: "date" },
] as const satisfies readonly { id: string; label: string; width: number; filter: ColumnFilterKind }[];
export type ColumnId = (typeof COLUMNS)[number]["id"];
export const DEFAULT_COLUMNS: ColumnId[] = ["name", "town", "neighbour_town", "instagram", "facebook", "strategy", "message", "stage", "last_contact"];
export const PAGE_SIZE = 50;

export type ColumnFilter =
  | { kind: "boolean"; value: "yes" | "no" | "" }
  | { kind: "multi"; values: string[]; empty?: boolean }
  | { kind: "range"; from?: number; to?: number; empty?: boolean }
  | { kind: "text"; value: string }
  | { kind: "date"; from?: string; to?: string; empty?: boolean };
export type TableFilters = Partial<Record<ColumnId, ColumnFilter>>;
export type Sort = { column: ColumnId; direction: "asc" | "desc" };
export interface TableView {
  search: string; today: boolean; social: boolean; stage: string;
  filters: TableFilters; sort: Sort; columns: ColumnId[];
}
export interface Row {
  lead: Lead; history: Touch[]; status: Status; in_todays_batch: boolean; in_batch_since: string | null; last_contact: string | null;
}
interface BatchRow { date: string; lead_id: string }

export function buildRows(leads: Lead[], touches: Touch[], batches: BatchRow[], date: string): Row[] {
  const histories = new Map<string, Touch[]>();
  for (const t of touches) histories.set(t.lead_id, [...(histories.get(t.lead_id) ?? []), t]);
  const todays = new Set<string>();
  const since = new Map<string, string>();
  for (const b of batches) {
    if (b.date === date) todays.add(b.lead_id);
    if (!since.has(b.lead_id) || b.date < since.get(b.lead_id)!) since.set(b.lead_id, b.date);
  }
  return leads.map((lead) => {
    const history = histories.get(lead.id) ?? [];
    const inBatch = todays.has(lead.id);
    const last = history.filter((t) => t.kind !== "skipped").reduce<string | null>((acc, t) => (acc === null || t.date > acc ? t.date : acc), null);
    return { lead, history, in_todays_batch: inBatch, status: statusOf(lead, history, inBatch, date), in_batch_since: since.get(lead.id) ?? null, last_contact: last };
  });
}

const isEmpty = (v: unknown) => v === null || v === undefined || (typeof v === "string" && v.trim() === "");

export function valueOf(row: Row, column: ColumnId): string | number | null {
  const l = row.lead;
  switch (column) {
    case "stage": return stageOf(row.status);
    case "neighbour_town": return l.neighbour_town_manual?.trim() || l.neighbour_town;
    case "strategy": return l.strategy_name ?? l.strategy;
    case "message": return l.message ?? l.missing ?? null;
    case "last_contact": return row.last_contact;
    case "in_batch_since": return row.in_batch_since;
    case "sent_text": return row.history.filter((t) => t.kind === "sent" && t.text).sort((a, b) => b.created_at.localeCompare(a.created_at))[0]?.text ?? null;
    default: return (l[column as keyof Lead] as string | number | null | undefined) ?? null;
  }
}

export function filterActive(f: ColumnFilter | undefined): boolean {
  if (!f) return false;
  switch (f.kind) {
    case "boolean": return f.value !== "";
    case "text": return f.value.trim() !== "";
    case "multi": return f.values.length > 0 || f.empty === true;
    case "range": return f.from !== undefined || f.to !== undefined || f.empty === true;
    case "date": return f.from !== undefined || f.to !== undefined || f.empty === true;
  }
}

function matches(value: string | number | null, f: ColumnFilter, timeZone: string): boolean {
  if (!filterActive(f)) return true;
  if (f.kind === "boolean") return f.value === "yes" ? !isEmpty(value) : isEmpty(value);
  if (f.kind === "text") return String(value ?? "").toLowerCase().includes(f.value.trim().toLowerCase());
  if (isEmpty(value)) return f.empty === true || (f.kind === "multi" && f.values.includes(""));
  if (f.kind === "multi") return f.values.includes(String(value));
  if (f.kind === "range") {
    return typeof value === "number" && (f.from === undefined || value >= f.from) && (f.to === undefined || value <= f.to) && (f.from !== undefined || f.to !== undefined);
  }
  const text = String(value);
  const moment = new Date(text);
  const day = /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : Number.isFinite(moment.getTime()) ? dayIn(timeZone, moment) : "";
  if (!day) return false;
  return (f.from === undefined || day >= f.from) && (f.to === undefined || day <= f.to) && (f.from !== undefined || f.to !== undefined);
}

/** Leads with at least one social channel (Instagram, Facebook or LinkedIn). */
export const socialChannels = (lead: Lead) => Number(!!lead.instagram?.trim()) + Number(!!lead.facebook?.trim()) + Number(!!lead.linkedin?.trim());

export function filterRows(rows: Row[], view: TableView, timeZone: string, skipColumn?: ColumnId): Row[] {
  const search = view.search.trim().toLowerCase();
  return rows.filter((row) => {
    if (search && !`${row.lead.name} ${row.lead.town ?? ""} ${row.lead.region ?? ""}`.toLowerCase().includes(search)) return false;
    if (view.today && !row.in_todays_batch) return false;
    if (view.social && !socialChannels(row.lead)) return false;
    if (view.stage && stageOf(row.status) !== view.stage) return false;
    return Object.entries(view.filters).every(([id, f]) => id === skipColumn || !f || matches(valueOf(row, id as ColumnId), f, timeZone));
  });
}

/** Empty values stay last in both directions; with socialFirst, leads with more social channels come first. */
export function sortRows(rows: Row[], sort: Sort, socialFirst = false): Row[] {
  return [...rows].sort((a, b) => {
    const channels = socialFirst ? socialChannels(b.lead) - socialChannels(a.lead) : 0;
    if (channels) return channels;
    const x = valueOf(a, sort.column), y = valueOf(b, sort.column);
    if (isEmpty(x) || isEmpty(y)) return isEmpty(x) && isEmpty(y) ? 0 : isEmpty(x) ? 1 : -1;
    const order = [...STAGES] as string[];
    const cmp = sort.column === "stage" ? order.indexOf(String(x)) - order.indexOf(String(y))
      : typeof x === "number" && typeof y === "number" ? x - y
      : String(x).localeCompare(String(y), "en", { numeric: true, sensitivity: "base" });
    return sort.direction === "desc" ? -cmp : cmp;
  });
}

/** Options with counts; the UI recomputes the counts under the other active filters. */
export function optionsFor(rows: Row[], column: ColumnId): { value: string; count: number }[] {
  const kind = COLUMNS.find((c) => c.id === column)!.filter;
  const counts = new Map<string, number>();
  if (kind === "boolean") { counts.set("yes", 0); counts.set("no", 0); }
  if (column === "stage") for (const s of STAGES) counts.set(s, 0);
  for (const row of rows) {
    const v = valueOf(row, column);
    const key = kind === "boolean" ? (isEmpty(v) ? "no" : "yes") : isEmpty(v) ? "" : String(v);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const options = [...counts].map(([value, count]) => ({ value, count }));
  if (kind === "boolean" || column === "stage") return options;
  return options.sort((a, b) => a.value === "" ? 1 : b.value === "" ? -1 : a.value.localeCompare(b.value, "en", { numeric: true, sensitivity: "base" }));
}

export function pageOf(rows: Row[], page: number): Row[] {
  const last = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const n = Math.max(1, Math.min(last, Number.isFinite(page) ? Math.floor(page) : 1));
  return rows.slice((n - 1) * PAGE_SIZE, n * PAGE_SIZE);
}

const isObject = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const isColumn = (v: unknown): v is ColumnId => COLUMNS.some((c) => c.id === v);
const isDay = (v: unknown): v is string => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T12:00:00Z`);
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0, 10) === v;
};

/** Saved views must not smuggle in unknown columns or malformed filters. */
export function normalizeView(raw: unknown): TableView {
  const data = isObject(raw) ? raw : {};
  const filters: TableFilters = {};
  if (isObject(data.filters)) {
    for (const [id, entry] of Object.entries(data.filters)) {
      if (!isColumn(id) || !isObject(entry) || entry.kind !== COLUMNS.find((c) => c.id === id)!.filter) continue;
      const empty = entry.empty === true;
      let clean: ColumnFilter | undefined;
      if (entry.kind === "boolean") clean = { kind: "boolean", value: entry.value === "yes" || entry.value === "no" ? entry.value : "" };
      if (entry.kind === "text") clean = { kind: "text", value: typeof entry.value === "string" ? entry.value : "" };
      if (entry.kind === "multi") clean = { kind: "multi", empty, values: Array.isArray(entry.values) ? [...new Set(entry.values.filter((v): v is string => typeof v === "string"))] : [] };
      if (entry.kind === "range") clean = { kind: "range", empty,
        ...(typeof entry.from === "number" && Number.isFinite(entry.from) ? { from: entry.from } : {}),
        ...(typeof entry.to === "number" && Number.isFinite(entry.to) ? { to: entry.to } : {}) };
      if (entry.kind === "date") clean = { kind: "date", empty,
        ...(isDay(entry.from) ? { from: entry.from } : {}), ...(isDay(entry.to) ? { to: entry.to } : {}) };
      if (clean && filterActive(clean)) filters[id] = clean;
    }
  }
  const columns = Array.isArray(data.columns) ? [...new Set(data.columns.filter(isColumn))] : [...DEFAULT_COLUMNS];
  const sort = isObject(data.sort) ? data.sort : {};
  return {
    search: typeof data.search === "string" ? data.search : "",
    today: data.today === true,
    social: data.social === true,
    stage: typeof data.stage === "string" && ["", ...STAGES].includes(data.stage) ? data.stage : "",
    filters,
    sort: { column: isColumn(sort.column) ? sort.column : "name", direction: sort.direction === "desc" ? "desc" : "asc" },
    columns: columns.length ? columns : ["name"],
  };
}
export { STAGE_LABEL, activeChannels };
