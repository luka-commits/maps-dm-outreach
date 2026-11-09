"use client";
import { useEffect, useRef, useState } from "react";
import { useWrite } from "./useWrite";

/** One lead field saved through PATCH /api/leads/<id> when it loses focus (Enter saves single-line fields). */
export function SavedField({ id, field, value, label, placeholder, multiline = false, type = "text" }: {
  id: string; field: "opener" | "neighbour_town_manual" | "linkedin"; value: string | null; label: string;
  placeholder?: string; multiline?: boolean; type?: "text" | "url";
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [saved, setSaved] = useState(value ?? "");
  const [message, setMessage] = useState("");
  const { write, busy, error } = useWrite();
  const received = useRef(value ?? "");
  useEffect(() => {
    const old = received.current, next = value ?? "";
    setDraft((v) => (v === old ? next : v)); setSaved(next); received.current = next;
  }, [value]);
  async function save() {
    if (draft.trim() === saved.trim()) return;
    const r = await write(`/api/leads/${encodeURIComponent(id)}`, { [field]: draft.trim() || null }, "PATCH");
    if (r) { setSaved(draft.trim()); setDraft(draft.trim()); setMessage("Saved"); }
  }
  const common = { "aria-label": label, placeholder, value: draft, disabled: busy, onChange: (e: { target: { value: string } }) => setDraft(e.target.value), onBlur: save };
  return <div>
    {multiline ? <textarea rows={3} {...common} />
      : <input type={type} {...common} onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />}
    <span className="muted" role="status">{busy ? "Saving…" : message}</span>{error && <p role="alert" className="err">{error}</p>}
  </div>;
}
