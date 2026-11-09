"use client";
import { useState } from "react";
import { CHANNEL_LABEL, KIND_LABEL, type Channel, type Kind } from "@/lib/types";
import { useWrite } from "./useWrite";

const RESULTS: Kind[] = ["reply", "asset_sent", "meeting", "not_interested"];

export function LogResult({ leadId, channels }: { leadId: string; channels: Channel[] }) {
  const [channel, setChannel] = useState<Channel>(channels[0] ?? "instagram");
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");
  const { write, busy, error } = useWrite();
  async function log(kind: Kind) {
    if (await write("/api/touches", { lead_id: leadId, channel, kind, text: text || null })) { setText(""); setMessage(`${KIND_LABEL[kind]} logged.`); }
  }
  return <div><div className="fields">
    <label>Channel<select aria-label="Channel" value={channel} onChange={(e) => setChannel(e.target.value as Channel)} disabled={!channels.length || busy}>
      {channels.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}</select></label>
    <label>Text <span className="muted">optional</span><textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} disabled={busy} /></label></div>
    <div className="btn-row">{RESULTS.map((k) => <button key={k} className={k === "reply" ? "btn-primary" : "btn"} disabled={busy || !channels.length} onClick={() => log(k)}>{KIND_LABEL[k]}</button>)}</div>
    {!channels.length && <p className="muted">No active channel.</p>}
    <p role="status" className="muted">{message}</p>{error && <p role="alert" className="err">{error}</p>}</div>;
}
