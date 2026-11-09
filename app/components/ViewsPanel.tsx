"use client";
import { useState } from "react";
import { Bookmark, Trash2 } from "lucide-react";
import { normalizeView, type TableView } from "@/lib/table";
import { useWrite } from "./useWrite";

export function ViewsPanel({ views, current, load }: { views: { name: string; json: string }[]; current: TableView; load: (v: TableView) => void }) {
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const { write, busy, error } = useWrite();
  return <>
    <div className="pop-head"><strong>Saved views</strong></div>
    <p className="muted">Search, filters, sort and columns are saved together.</p>
    <div className="view-list">{views.length ? views.map((v) => <div key={v.name}>
      <button type="button" className="view-load" onClick={() => { try { load(normalizeView(JSON.parse(v.json))); } catch { setMessage("The view could not be loaded."); } }}>
        <Bookmark size={13} />{v.name}</button>
      <button type="button" className="icon-btn" disabled={busy} aria-label={`Delete view ${v.name}`}
        onClick={async () => { if (await write("/api/views", { name: v.name }, "DELETE")) setMessage("View deleted."); }}><Trash2 size={13} /></button>
    </div>) : <p className="muted">No saved views yet.</p>}</div>
    <form className="view-save" onSubmit={async (e) => {
      e.preventDefault();
      if (await write("/api/views", { name: name.trim(), view: current })) { setMessage(`Saved "${name.trim()}".`); setName(""); }
    }}><label htmlFor="view-name">Name of the view</label><div className="row"><input id="view-name" value={name} maxLength={80} required
      onChange={(e) => setName(e.target.value)} placeholder="For example: Leeds with Instagram" />
      <button type="submit" className="btn" disabled={busy || !name.trim()}>Save</button></div></form>
    <p role="status" className="muted">{message}</p>{error && <p role="alert" className="err">{error}</p>}
  </>;
}
