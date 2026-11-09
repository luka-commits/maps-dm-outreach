"use client";
import { useState } from "react";
import { Check, ExternalLink, Facebook, Instagram, Linkedin, SkipForward } from "lucide-react";
import { CHANNEL_LABEL, type Channel } from "@/lib/types";
import type { Row } from "@/lib/table";
import { channelInactive } from "@/lib/state";
import { shortDay } from "@/lib/date";
import { useWrite } from "./useWrite";

const ICONS = { instagram: Instagram, facebook: Facebook, linkedin: Linkedin } as const;

/** Opens the profile in a new tab AND copies the rendered message. The tick logs the send for today. */
export function ChannelCell({ row, channel, date }: { row: Row; channel: Channel; date: string }) {
  const { write, busy, error } = useWrite();
  const [copyError, setCopyError] = useState("");
  const { lead } = row;
  const target = lead[channel]?.trim();
  if (!target) return <span className="muted">—</span>;
  const inactive = channelInactive(lead, channel);
  if (inactive) return <div className="channel-cell"><a href={target} target="_blank" rel="noreferrer"
    className="channel-link off" title={`Inactive: ${inactive}`}><span>inactive · {inactive}</span></a></div>;
  const text = lead.message;
  const Icon = ICONS[channel];
  const label = CHANNEL_LABEL[channel];
  const sentDays = row.history.filter((t) => t.channel === channel && t.kind === "sent").map((t) => t.date).sort();
  const lastSent = sentDays.at(-1);
  const sentToday = lastSent === date;
  const skippedToday = row.history.some((t) => t.channel === channel && t.kind === "skipped" && t.date === date);
  const post = (kind: "sent" | "skipped") => write("/api/touches", { lead_id: lead.id, channel, kind });
  return <div className="channel-cell">
    {text ? <a href={target} target="_blank" rel="noreferrer" className="channel-link"
      aria-label={`Open ${label}: ${lead.name}`} title={`${target}\n${text}`}
      onClick={() => { void navigator.clipboard.writeText(text).then(() => setCopyError("")).catch(() => setCopyError("Could not copy the message.")); }}>
      <Icon size={13} /><span>Open</span><ExternalLink size={10} /></a>
      : <span className="warn" title={target}>{lead.missing ?? "No message"}</span>}
    <button type="button" className="tick" aria-pressed={!!lastSent} aria-label={`${label} sent: ${lead.name}`}
      title={sentToday ? "Undo today's send" : lastSent ? `Sent on ${shortDay(lastSent)}` : "Mark as sent today"}
      disabled={busy || (!!lastSent && !sentToday)} onClick={() => post("sent")}><Check size={12} />{lastSent && <span>{shortDay(lastSent)}</span>}</button>
    {!lastSent && <button type="button" className="skip" aria-pressed={skippedToday} aria-label={`Skip ${label} today: ${lead.name}`}
      title={skippedToday ? "Undo skip" : "Skip this channel today"} disabled={busy} onClick={() => post("skipped")}><SkipForward size={11} /></button>}
    {(error || copyError) && <span role="alert" className="cell-error">{error || copyError}</span>}
  </div>;
}
