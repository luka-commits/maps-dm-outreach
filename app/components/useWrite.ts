"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** POST/PATCH/DELETE JSON, then refresh the server-rendered data. Returns the parsed result or null on error. */
export function useWrite() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function write(url: string, data: unknown, method = "POST") {
    setBusy(true); setError(null);
    try {
      const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Saving failed.");
      router.refresh();
      return result;
    } catch (e) { setError(e instanceof Error ? e.message : "Saving failed."); return null; }
    finally { setBusy(false); }
  }
  return { write, busy, error };
}
