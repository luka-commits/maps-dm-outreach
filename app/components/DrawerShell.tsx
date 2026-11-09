"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

/** Right-hand drawer. Escape closes, arrow keys move through the order the table showed (falls back to the server order). */
export function DrawerShell({ children, title, prev, next, position, total }: {
  children: React.ReactNode; title: string; prev?: string; next?: string; position: number; total: number;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [order, setOrder] = useState<string[]>([]);
  const index = order.indexOf(params.get("lead") ?? "");
  const target = (id: string) => { const p = new URLSearchParams(params.toString()); p.set("lead", id); return `/?${p}`; };
  if (index >= 0) {
    prev = index > 0 ? target(order[index - 1]) : undefined;
    next = index < order.length - 1 ? target(order[index + 1]) : undefined;
    position = index + 1; total = order.length;
  }
  const panel = useRef<HTMLElement>(null);
  const close = () => {
    const p = new URLSearchParams(params.toString()); p.delete("lead");
    if (window.history.length > 1) router.back(); else router.replace(p.size ? `/?${p}` : "/", { scroll: false });
  };
  useEffect(() => {
    try { const ids = JSON.parse(sessionStorage.getItem("outreach.order") ?? "[]"); if (Array.isArray(ids) && ids.every((i) => typeof i === "string")) setOrder(ids); } catch { /* use server order */ }
  }, []);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      if (e.key === "Tab") {
        const items = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,textarea,[tabindex="0"]');
        if (!items?.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === "ArrowLeft" && prev) router.replace(prev, { scroll: false });
      if (e.key === "ArrowRight" && next) router.replace(next, { scroll: false });
    };
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = overflow; window.removeEventListener("keydown", onKey); before?.focus(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, prev, next]);
  return <div className="drawer-frame">
    <button className="drawer-backdrop" aria-label="Close lead" onClick={close} />
    <aside ref={panel} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className="drawer">
      <div className="drawer-head">
        <div className="row">
          <button className="btn" aria-label="Previous lead" disabled={!prev} onClick={() => prev && router.replace(prev, { scroll: false })}><ChevronLeft size={15} /></button>
          <span className="muted num">{position} / {total}</span>
          <button className="btn" aria-label="Next lead" disabled={!next} onClick={() => next && router.replace(next, { scroll: false })}><ChevronRight size={15} /></button>
        </div>
        <button className="btn" onClick={close}><X size={14} />Close · Esc</button>
      </div>
      <div className="drawer-body">{children}</div>
    </aside>
  </div>;
}
