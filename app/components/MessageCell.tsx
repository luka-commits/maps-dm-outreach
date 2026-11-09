"use client";
import { useState } from "react";
import { Check, Copy } from "lucide-react";
import type { Row } from "@/lib/table";

export function MessageCell({ row }: { row: Row }) {
  const [state, setState] = useState<"" | "copied" | "error">("");
  const { lead } = row;
  const text = lead.message;
  if (!text) return <span className="warn">{lead.missing ?? "No message"}</span>;
  return <div className="message-cell">
    <span title={text}>{text}</span>
    <button type="button" className="copy-btn" aria-label={`Copy message: ${lead.name}`} title="Copy message" onClick={() => {
      void navigator.clipboard.writeText(text).then(() => setState("copied")).catch(() => setState("error"));
      setTimeout(() => setState(""), 1500);
    }}>{state === "copied" ? <><Check size={12} />Copied</> : <><Copy size={12} />Copy</>}</button>
    {state === "error" && <span role="alert" className="cell-error">Could not copy the message.</span>}
  </div>;
}
