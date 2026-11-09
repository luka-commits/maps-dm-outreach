"use client";
import { useEffect, useRef, useState } from "react";
import { useWrite } from "./useWrite";

/** Free-text note, saved when the field loses focus. */
export function NotesField({ id, text, rows = 1 }: { id: string; text: string | null; rows?: number }) {
  const [draft, setDraft] = useState(text ?? "");
  const [saved, setSaved] = useState(text ?? "");
  const [message, setMessage] = useState("");
  const { write, busy, error } = useWrite();
  const received = useRef(text ?? "");
  useEffect(() => {
    const old = received.current, next = text ?? "";
    setDraft((v) => (v === old ? next : v)); setSaved(next); received.current = next;
  }, [text]);
  return <div><textarea aria-label="Notes" placeholder="Anything worth remembering?" rows={rows} value={draft} disabled={busy}
    onChange={(e) => setDraft(e.target.value)}
    onBlur={async () => { if (draft !== saved && await write(`/api/leads/${encodeURIComponent(id)}`, { notes: draft }, "PATCH")) { setSaved(draft); setMessage("Saved"); } }} />
    <span className="muted" role="status">{busy ? "Saving…" : message}</span>{error && <p role="alert" className="err">{error}</p>}</div>;
}
