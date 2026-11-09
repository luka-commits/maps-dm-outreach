"use client";
import { useState } from "react";
import { Filter } from "lucide-react";
import { COLUMNS, filterActive, optionsFor, valueOf, type ColumnFilter, type ColumnId, type Row, type TableView } from "@/lib/table";
import { STAGE_LABEL, type Stage } from "@/lib/types";

export function FilterField({ id, rows, allRows, value, set, close }: {
  id: ColumnId; rows: Row[]; allRows: Row[]; value?: ColumnFilter; set: (v?: ColumnFilter) => void; close: () => void;
}) {
  const column = COLUMNS.find((c) => c.id === id)!;
  const [search, setSearch] = useState("");
  const counts = new Map(optionsFor(rows, id).map((o) => [o.value, o.count]));
  const options = optionsFor(allRows, id).map((o) => ({ ...o, count: counts.get(o.value) ?? 0 }));
  const numbers = rows.map((r) => valueOf(r, id)).filter((v): v is number => typeof v === "number");
  const range = value?.kind === "range" ? value : { kind: "range" as const };
  const dates = value?.kind === "date" ? value : { kind: "date" as const };
  return <div className="filterfield">
    <fieldset><legend>{column.label}</legend>
      {column.filter === "boolean" && <div className="seg">
        {([["", "All"], ["yes", "Present"], ["no", "Missing"]] as const).map(([v, label]) =>
          <button key={v} type="button" aria-pressed={(value?.kind === "boolean" ? value.value : "") === v}
            onClick={() => set(v ? { kind: "boolean", value: v } : undefined)}>{label}{v ? ` · ${options.find((o) => o.value === v)?.count ?? 0}` : ""}</button>)}
      </div>}
      {column.filter === "multi" && <>
        {options.length > 8 && <input type="search" aria-label={`Search ${column.label} values`} placeholder="Find a value…" value={search} onChange={(e) => setSearch(e.target.value)} />}
        <div className="options">{options.filter((o) => o.value.toLowerCase().includes(search.toLowerCase())).map((o) => {
          const chosen = value?.kind === "multi" ? value.values : [];
          const on = chosen.includes(o.value);
          const label = id === "stage" ? STAGE_LABEL[o.value as Stage] ?? o.value : o.value || "Blank";
          return <label key={o.value} className={on ? "on" : o.count === 0 ? "none" : ""}>
            <input type="checkbox" checked={on} aria-label={label} onChange={() => {
              const values = on ? chosen.filter((v) => v !== o.value) : [...chosen, o.value];
              set(values.length ? { kind: "multi", values } : undefined);
            }} /><span>{label}</span><span className="num muted">{o.count}</span></label>;
        })}</div>
      </>}
      {column.filter === "text" && <input type="search" aria-label={`${column.label} contains`} placeholder="Contains…"
        value={value?.kind === "text" ? value.value : ""} onChange={(e) => set(e.target.value ? { kind: "text", value: e.target.value } : undefined)} />}
      {column.filter === "range" && <>
        <p className="muted">{numbers.length ? `${Math.min(...numbers)} to ${Math.max(...numbers)} · ${numbers.length} values` : "No values"}</p>
        <div className="range">{(["from", "to"] as const).map((side) => <label key={side}>{side === "from" ? "Min" : "Max"}
          <input type="number" step="any" aria-label={`${column.label} ${side === "from" ? "minimum" : "maximum"}`} value={range[side] ?? ""}
            onChange={(e) => set({ ...range, [side]: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>)}</div>
        <label className="include-empty"><input type="checkbox" checked={!!range.empty} onChange={(e) => set({ ...range, empty: e.target.checked })} />Include blank values</label>
      </>}
      {column.filter === "date" && <div className="range">{(["from", "to"] as const).map((side) => <label key={side}>{side === "from" ? "From" : "To"}
        <input type="date" aria-label={`${column.label} ${side}`} value={dates[side] ?? ""} onChange={(e) => set({ ...dates, [side]: e.target.value || undefined })} /></label>)}</div>}
    </fieldset>
    <div className="filter-foot"><button type="button" disabled={!filterActive(value)} onClick={() => set(undefined)}>Clear</button><button type="button" onClick={close}>Done</button></div>
  </div>;
}

export function HeaderCell({ id, view, setSort, open, isOpen }: {
  id: ColumnId; view: TableView; setSort: (s: TableView["sort"]) => void; open: () => void; isOpen: boolean;
}) {
  const column = COLUMNS.find((c) => c.id === id)!;
  const sorted = view.sort.column === id;
  const active = filterActive(view.filters[id]);
  return <div className="th-inner">
    <button type="button" aria-label={`Sort by ${column.label}`} data-on={sorted ? "yes" : undefined}
      onClick={() => setSort(sorted && view.sort.direction === "asc" ? { column: id, direction: "desc" } : sorted ? { column: "name", direction: "asc" } : { column: id, direction: "asc" })}>
      <span>{column.label}</span>{sorted && <span aria-hidden="true">{view.sort.direction === "asc" ? "↑" : "↓"}</span>}</button>
    <button type="button" aria-label={`Filter ${column.label}`} aria-expanded={isOpen} data-on={active ? "yes" : undefined} onClick={open}>
      <Filter size={12} fill={active ? "currentColor" : "none"} /></button>
  </div>;
}
