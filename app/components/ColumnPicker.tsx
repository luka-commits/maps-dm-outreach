"use client";
import { ArrowDown, ArrowUp, GripVertical } from "lucide-react";
import { COLUMNS, DEFAULT_COLUMNS, type ColumnId } from "@/lib/table";

export function ColumnPicker({ columns, set, drag, dragged }: {
  columns: ColumnId[]; set: (c: ColumnId[]) => void; drag: (id: ColumnId | null) => void; dragged: ColumnId | null;
}) {
  function move(from: ColumnId, to: ColumnId) {
    if (from === to) return;
    const next = columns.filter((c) => c !== from);
    next.splice(next.indexOf(to), 0, from);
    set(next);
  }
  return <>
    <div className="pop-head"><strong>Columns</strong><button type="button" className="link-btn" onClick={() => set([...DEFAULT_COLUMNS])}>Reset columns</button></div>
    <div className="chip-list">{COLUMNS.map((c) => {
      const on = columns.includes(c.id);
      return <button type="button" key={c.id} aria-pressed={on} disabled={on && columns.length === 1}
        onClick={() => set(on ? columns.filter((x) => x !== c.id) : [...columns, c.id])}>{c.label}</button>;
    })}</div>
    <div className="order"><div className="pop-head"><strong>Order</strong><span className="muted">Drag, or use the arrows. Left to right.</span></div>
      <div className="order-list">{columns.map((id, i) => {
        const label = COLUMNS.find((c) => c.id === id)!.label;
        const swap = (d: -1 | 1) => { const next = [...columns]; [next[i], next[i + d]] = [next[i + d], next[i]]; set(next); };
        return <div key={id} draggable onDragStart={(e) => { drag(id); e.dataTransfer.setData("text/plain", id); }} onDragEnd={() => drag(null)}
          onDragOver={(e) => { if (dragged && dragged !== id) e.preventDefault(); }}
          onDrop={(e) => { e.preventDefault(); if (dragged) move(dragged, id); drag(null); }}>
          <GripVertical size={12} /><span>{label}</span>
          <button type="button" className="icon-btn" disabled={i === 0} aria-label={`Move ${label} left`} onClick={() => swap(-1)}><ArrowUp size={13} /></button>
          <button type="button" className="icon-btn" disabled={i === columns.length - 1} aria-label={`Move ${label} right`} onClick={() => swap(1)}><ArrowDown size={13} /></button>
        </div>;
      })}</div></div>
  </>;
}
