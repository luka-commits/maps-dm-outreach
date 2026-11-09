"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type MouseEvent } from "react";
import { Bookmark, Check, ChevronLeft, ChevronRight, Filter, Search, X } from "lucide-react";
import {
  COLUMNS, PAGE_SIZE, filterActive, filterRows, normalizeView, pageOf, socialChannels, sortRows, valueOf,
  type ColumnFilter, type ColumnId, type Row, type TableView,
} from "@/lib/table";
import { CHANNELS, CHANNEL_LABEL, STAGES, STAGE_LABEL, type Channel, type Stage, type Undo } from "@/lib/types";
import { doneToday, stageOf } from "@/lib/state";
import { shortDay } from "@/lib/date";
import { useWrite } from "./useWrite";
import { NotesField } from "./NotesField";
import { ChannelCell } from "./ChannelCell";
import { MessageCell } from "./MessageCell";
import { FilterField, HeaderCell } from "./FilterField";
import { ColumnPicker } from "./ColumnPicker";
import { ViewsPanel } from "./ViewsPanel";

const COLUMN_STORE = "outreach.columns.v1";
const COUNT_STORE = "outreach.batchCount";
type Popover = { kind: "columns" | "filter" | "views"; id?: ColumnId; left: number; top: number };

function SelectBox({ checked, mixed = false, label, toggle }: { checked: boolean; mixed?: boolean; label: string; toggle: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = mixed; }, [mixed]);
  return <input ref={ref} type="checkbox" checked={checked} aria-label={label} onChange={toggle} />;
}

export function LeadTable({ rows, date, timezone, limits, views, todayDefault }: {
  rows: Row[]; date: string; timezone: string; limits: Record<Channel, number | null>;
  views: { name: string; json: string }[]; todayDefault: boolean;
}) {
  const router = useRouter();
  const [view, setView] = useState<TableView>(() => normalizeView({ today: todayDefault }));
  const [count, setCount] = useState(20);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [popover, setPopover] = useState<Popover | null>(null);
  const [dragged, setDragged] = useState<ColumnId | null>(null);
  const [bulkChannel, setBulkChannel] = useState<Channel>("instagram");
  const [bulkStage, setBulkStage] = useState<Stage>("contacted");
  const [message, setMessage] = useState("");
  const [undo, setUndo] = useState<Undo[]>([]);
  const { write, busy, error } = useWrite();

  useEffect(() => {
    try {
      const raw = localStorage.getItem(COLUMN_STORE);
      if (raw) setView((v) => ({ ...v, columns: normalizeView({ columns: JSON.parse(raw) }).columns }));
      const n = Number(localStorage.getItem(COUNT_STORE));
      if (Number.isSafeInteger(n) && n > 0) setCount(n);
    } catch { /* Without storage the defaults stay usable. */ }
  }, []);
  useEffect(() => { setView((v) => ({ ...v, today: todayDefault })); setPage(1); setSelected(new Set()); }, [todayDefault, date]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPopover(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const result = useMemo(() => sortRows(filterRows(rows, view, timezone), view.sort, view.social), [rows, view, timezone]);
  const pages = Math.max(1, Math.ceil(result.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const visible = pageOf(result, current);
  const visibleIds = visible.map((r) => r.lead.id);
  const allSelected = !!visible.length && visibleIds.every((id) => selected.has(id));
  const someSelected = visibleIds.some((id) => selected.has(id));
  const batch = rows.filter((r) => r.in_todays_batch);
  const sentToday = CHANNELS.map((channel) => ({ channel, n: rows.reduce((sum, r) =>
    sum + r.history.filter((t) => t.channel === channel && t.kind === "sent" && t.date === date).length, 0), limit: limits[channel] }));
  const done = batch.filter((r) => doneToday(r.lead, r.history, date)).length;
  const stageBase = filterRows(rows, { ...view, stage: "", filters: { ...view.filters, stage: undefined } }, timezone);
  const socialCount = filterRows(rows, { ...view, social: false, stage: "", filters: { ...view.filters, stage: undefined } }, timezone).filter((r) => socialChannels(r.lead)).length;
  const activeFilters = COLUMNS.filter((c) => filterActive(view.filters[c.id]));
  const columns = view.columns.map((id) => COLUMNS.find((c) => c.id === id)!);
  const tableWidth = 48 + columns.reduce((sum, c) => sum + c.width, 0);

  useEffect(() => {
    const allowed = new Set(result.map((r) => r.lead.id));
    setSelected((old) => [...old].every((id) => allowed.has(id)) ? old : new Set([...old].filter((id) => allowed.has(id))));
  }, [result]);

  const change = (patch: Partial<TableView>) => { setView((v) => ({ ...v, ...patch })); setPage(1); setSelected(new Set()); };
  function setColumns(next: ColumnId[]) {
    const value = next.length ? next : ["name" as const];
    setView((v) => ({ ...v, columns: value }));
    try { localStorage.setItem(COLUMN_STORE, JSON.stringify(value)); } catch { setMessage("The column choice could not be saved in this browser."); }
  }
  function setFilter(id: ColumnId, value?: ColumnFilter) {
    const filters = { ...view.filters };
    if (value) filters[id] = value; else delete filters[id];
    change({ filters });
  }
  function openPopover(e: MouseEvent<HTMLElement>, kind: Popover["kind"]) {
    if (popover?.kind === kind && !popover.id) { setPopover(null); return; }
    const rect = e.currentTarget.getBoundingClientRect();
    const width = kind === "columns" ? 420 : kind === "views" ? 360 : 300;
    setPopover({ kind, left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 20)), top: Math.min(rect.bottom + 5, window.innerHeight - 150) });
  }
  const select = (ids: string[], on: boolean) => setSelected((old) => { const next = new Set(old); ids.forEach((id) => on ? next.add(id) : next.delete(id)); return next; });
  function setToday(on: boolean) { change({ today: on }); router.replace(on ? "/?view=today" : "/", { scroll: false }); }
  function resetAll() {
    change({ search: "", today: false, social: false, stage: "", filters: {}, sort: { column: "name", direction: "asc" } });
    setPopover(null); router.replace("/", { scroll: false });
  }
  async function stage(ids: string[], next: string) {
    const r = await write("/api/stage", { lead_ids: ids, stage: next });
    if (!r) return;
    if (next === "new") {
      setUndo(r.undo);
      setMessage(r.undo.length ? `${r.undo.length} latest stage ${r.undo.length === 1 ? "entry" : "entries"} withdrawn. Send ticks are kept.` : "Nothing to withdraw. Send ticks are kept.");
    } else setMessage(`${ids.length} stage ${ids.length === 1 ? "entry" : "entries"} saved. A higher stage that already exists wins.`);
  }
  const leadHref = (id: string) => `/?${new URLSearchParams({ ...(view.today ? { view: "today" } : {}), lead: id })}`;
  const rememberOrder = () => { try { sessionStorage.setItem("outreach.order", JSON.stringify(visibleIds)); } catch { /* arrows fall back to all leads */ } };

  function cell(row: Row, id: ColumnId) {
    const l = row.lead;
    if (id === "name") return <Link className="lead-link" href={leadHref(l.id)} prefetch={false} scroll={false} title={l.name} onClick={rememberOrder}>{l.name}</Link>;
    if (CHANNELS.includes(id as Channel)) return <ChannelCell row={row} channel={id as Channel} date={date} />;
    if (id === "stage") return <select className={`stage-select ${stageOf(row.status)}`} aria-label={`Stage: ${l.name}`} value={stageOf(row.status)} disabled={busy}
      onChange={(e) => stage([l.id], e.target.value)}>{STAGES.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}</select>;
    if (id === "message") return <MessageCell row={row} />;
    if (id === "notes") return <div className="notes-cell"><NotesField key={l.id} id={l.id} text={l.notes} /></div>;
    if (id === "phone") return l.phone ? <a href={`tel:${l.phone.replace(/\s+/g, "")}`} className="clip num" title={l.phone}>{l.phone}</a> : <span className="muted">—</span>;
    if (id === "website") return l.website ? <a href={/^https?:\/\//i.test(l.website) ? l.website : `https://${l.website}`} target="_blank" rel="noreferrer" className="clip" title={l.website}>
      {l.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}</a> : <span className="muted">—</span>;
    if (id === "last_contact" || id === "in_batch_since" || id === "imported_at") {
      const v = valueOf(row, id) as string | null;
      return <span className="num" title={v ?? undefined}>{shortDay(v)}</span>;
    }
    const v = valueOf(row, id);
    return v === null || v === "" ? <span className="muted">—</span> : <span className="clip" title={String(v)}>{typeof v === "number" ? v.toLocaleString("en") : v}</span>;
  }

  return <section className="tool" aria-label="Leads">
    <div className="toolbar">
      <div className="search"><Search size={15} /><input type="search" aria-label="Search leads" placeholder="Search businesses and towns" value={view.search} onChange={(e) => change({ search: e.target.value })} /></div>
      <span className="count">{result.length} leads · page {current} of {pages}</span>
      <div className="mini-pager"><button type="button" aria-label="Previous page" disabled={current === 1} onClick={() => setPage(current - 1)}><ChevronLeft size={12} /></button>
        <button type="button" aria-label="Next page" disabled={current >= pages} onClick={() => setPage(current + 1)}><ChevronRight size={12} /></button></div>
      <button type="button" aria-pressed={view.today} onClick={() => setToday(!view.today)}>Today · {batch.length}</button>
      <div className="counters" role="status" aria-label="Sent today"><span className="muted">Sent today</span>{sentToday.map((s) =>
        <span key={s.channel} className={s.limit && s.n >= s.limit ? "full" : undefined} title={s.limit ? `Daily limit ${s.limit}` : "No limit"}>
          {CHANNEL_LABEL[s.channel]} <b>{s.n}{s.limit ? `/${s.limit}` : ""}</b></span>)}</div>
      <form className="batch-form" onSubmit={async (e) => {
        e.preventDefault();
        try { localStorage.setItem(COUNT_STORE, String(count)); } catch { /* default stays usable */ }
        const r = await write("/api/batch", { count });
        if (r) setMessage(`${r.pulled} lead${r.pulled === 1 ? "" : "s"} added to today's batch.`);
      }}><input type="number" min={1} step={1} required aria-label="Batch size" value={count} onChange={(e) => setCount(Number(e.target.value))} />
        <button type="submit" disabled={busy}>Pull batch</button></form>
      <button type="button" aria-expanded={popover?.kind === "filter"} onClick={(e) => openPopover(e, "filter")}><Filter size={14} />Filters{activeFilters.length ? ` · ${activeFilters.length}` : ""}</button>
      <button type="button" aria-expanded={popover?.kind === "columns"} onClick={(e) => openPopover(e, "columns")}>Columns · {columns.length}</button>
      <button type="button" aria-expanded={popover?.kind === "views"} onClick={(e) => openPopover(e, "views")}><Bookmark size={14} />Saved views{views.length ? ` · ${views.length}` : ""}</button>
    </div>

    <div className="stages" role="group" aria-label="Stages">
      <button type="button" aria-pressed={view.social} title="Only leads with Instagram, Facebook or LinkedIn; most channels first" onClick={() => change({ social: !view.social })}>Social <span>{socialCount}</span></button>
      <button type="button" aria-pressed={!view.stage} onClick={() => change({ stage: "" })}>All <span>{stageBase.length}</span></button>
      {STAGES.map((s) => <button key={s} type="button" aria-pressed={view.stage === s} onClick={() => change({ stage: view.stage === s ? "" : s })}>
        {STAGE_LABEL[s]} <span>{stageBase.filter((r) => stageOf(r.status) === s).length}</span></button>)}
    </div>

    {(activeFilters.length > 0 || view.today) && <div className="chips">
      {view.today && <span>{done} of {batch.length} done today</span>}
      {activeFilters.map((c) => <button type="button" key={c.id} onClick={() => setFilter(c.id)}>{c.label}<X size={11} /></button>)}
    </div>}

    {selected.size > 0 && <div className="bulkbar" aria-label="Bulk actions">
      <strong>{selected.size} selected</strong>
      <select aria-label="Channel for bulk send" value={bulkChannel} onChange={(e) => setBulkChannel(e.target.value as Channel)}>{CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}</select>
      <button type="button" disabled={busy} onClick={async () => {
        const r = await write("/api/bulk", { lead_ids: [...selected], channel: bulkChannel });
        if (r) setMessage(`${r.marked} marked as sent, stage unchanged${r.no_channel ? `, ${r.no_channel} skipped without that channel` : ""}.`);
      }}>Mark sent</button>
      <select aria-label="Stage for bulk change" value={bulkStage} onChange={(e) => setBulkStage(e.target.value as Stage)}>{STAGES.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}</select>
      <button type="button" disabled={busy} onClick={() => stage([...selected], bulkStage)}>Set stage</button>
      <button type="button" className="clear" onClick={() => setSelected(new Set())}>Clear selection</button>
    </div>}

    <div className="grid-wrap"><div className="grid-scroll">
      <table style={{ width: "100%", minWidth: tableWidth } as CSSProperties}>
        <colgroup><col style={{ width: 48 }} />{columns.map((c) => <col key={c.id} style={{ width: c.width }} />)}</colgroup>
        <thead><tr><th className="select-cell"><SelectBox checked={allSelected} mixed={!allSelected && someSelected} label="Select all on this page" toggle={() => select(visibleIds, !allSelected)} /></th>
          {columns.map((c) => <th key={c.id} data-column={c.id} draggable
            aria-sort={view.sort.column === c.id ? view.sort.direction === "asc" ? "ascending" : "descending" : "none"}
            onDragStart={(e) => { setDragged(c.id); e.dataTransfer.setData("text/plain", c.id); }} onDragEnd={() => setDragged(null)}
            onDragOver={(e) => { if (dragged && dragged !== c.id) e.preventDefault(); }}
            onDrop={(e) => { e.preventDefault(); if (dragged && dragged !== c.id) { const next = view.columns.filter((id) => id !== dragged); next.splice(next.indexOf(c.id), 0, dragged); setColumns(next); } setDragged(null); }}>
            <HeaderCell id={c.id} view={view} setSort={(sort) => change({ sort })} isOpen={popover?.kind === "filter" && popover.id === c.id}
              open={() => {
                const th = document.querySelector<HTMLElement>(`th[data-column="${c.id}"]`)!.getBoundingClientRect();
                setPopover(popover?.id === c.id ? null : { kind: "filter", id: c.id, left: Math.max(12, Math.min(th.left, window.innerWidth - 320)), top: Math.min(th.bottom + 5, window.innerHeight - 150) });
              }} /></th>)}
        </tr></thead>
        <tbody>{visible.map((r) => <tr key={r.lead.id} data-lead={r.lead.id} data-selected={selected.has(r.lead.id) ? "yes" : undefined}>
          <td className="select-cell"><SelectBox checked={selected.has(r.lead.id)} label={`Select ${r.lead.name}`} toggle={() => select([r.lead.id], !selected.has(r.lead.id))} /></td>
          {columns.map((c) => <td key={c.id} data-column={c.id}>{cell(r, c.id)}</td>)}
        </tr>)}</tbody>
      </table>
      {!visible.length && <div className="empty-row">{rows.length ? "No leads match. Adjust the filters." : "No leads imported yet."}</div>}
    </div></div>

    <div className="pagebar">
      {result.length > 0 && selected.size < result.length && <button type="button" className="select-all" onClick={() => select(result.map((r) => r.lead.id), true)}>Select all {result.length} results</button>}
      <span>Page {current} of {pages}</span>
      <button type="button" disabled={current === 1} onClick={() => setPage(1)}>First</button>
      <button type="button" disabled={current === 1} onClick={() => setPage(current - 1)}>Previous</button>
      <button type="button" disabled={current >= pages} onClick={() => setPage(current + 1)}>Next</button>
      <button type="button" disabled={current >= pages} onClick={() => setPage(pages)}>Last</button>
      <button type="button" onClick={resetAll}>Clear filters</button>
      <span className="where">{result.length ? `${(current - 1) * PAGE_SIZE + 1} to ${Math.min(current * PAGE_SIZE, result.length)} of ${result.length}` : "0 leads"}</span>
    </div>

    {(message || error || undo.length > 0) && <div className="notice" role={error ? "alert" : "status"}>
      <span className={error ? "err" : ""}>{error || message}</span>
      {undo.length > 0 && <button type="button" disabled={busy} onClick={async () => { if (await write("/api/stage", { restore: undo })) { setUndo([]); setMessage("Stage entry restored."); } }}>Undo</button>}
      <button type="button" className="icon-btn" aria-label="Dismiss message" onClick={() => setMessage("")}><X size={13} /></button>
    </div>}

    {popover && <><button type="button" className="backdrop" aria-label="Close menu" onClick={() => setPopover(null)} />
      <div role="region" aria-label={popover.kind === "columns" ? "Choose columns" : popover.kind === "views" ? "Saved views" : "Column filter"}
        className={`popover ${popover.kind}`} style={{ left: popover.left, top: popover.top }}>
        {popover.kind === "columns" && <ColumnPicker columns={view.columns} set={setColumns} drag={setDragged} dragged={dragged} />}
        {popover.kind === "views" && <ViewsPanel views={views} current={view} load={(v) => { change(v); setColumns(v.columns); setPopover(null); router.replace(v.today ? "/?view=today" : "/", { scroll: false }); }} />}
        {popover.kind === "filter" && (popover.id
          ? <FilterField key={popover.id} id={popover.id} rows={filterRows(rows, view, timezone, popover.id)} allRows={rows} value={view.filters[popover.id]}
            set={(v) => setFilter(popover.id!, v)} close={() => setPopover(null)} />
          : <div className="pick"><strong>Filter by column</strong>{COLUMNS.map((c) => <button key={c.id} type="button" onClick={() => setPopover({ ...popover, id: c.id })}>
            {c.label}{filterActive(view.filters[c.id]) && <Check size={12} />}</button>)}</div>)}
      </div></>}
  </section>;
}
