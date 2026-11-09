"use client";
import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function CopyButton({ text, label = "Copy message" }: { text: string; label?: string }) {
  const [state, setState] = useState<"" | "copied" | "error">("");
  return <button type="button" className="btn" onClick={() => {
    void navigator.clipboard.writeText(text).then(() => setState("copied")).catch(() => setState("error"));
    setTimeout(() => setState(""), 1500);
  }}>{state === "copied" ? <><Check size={13} />Copied</> : <><Copy size={13} />{label}</>}{state === "error" && <span className="err">failed</span>}</button>;
}
