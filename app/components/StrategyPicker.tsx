"use client";
import { useWrite } from "./useWrite";

export function StrategyPicker({ id, value, options }: { id: string; value: string | null; options: { id: string; name: string }[] }) {
  const { write, busy, error } = useWrite();
  return <div><select aria-label="Strategy" value={value ?? ""} disabled={busy} onChange={(e) => write(`/api/leads/${encodeURIComponent(id)}`, { strategy: e.target.value }, "PATCH")}>
    {!value && <option value="" disabled>None</option>}{options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
    {error && <p role="alert" className="err">{error}</p>}</div>;
}
