"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { dayIn } from "@/lib/date";

export function Header({ sender, timezone }: { sender: string; timezone: string }) {
  const path = usePathname();
  const router = useRouter();
  // The table is date-aware: refresh when the day rolls over in the configured timezone, and when the tab regains focus.
  useEffect(() => {
    let day = dayIn(timezone);
    const check = () => { const now = dayIn(timezone); if (now !== day) { day = now; router.refresh(); } };
    const onFocus = () => { check(); router.refresh(); };
    const timer = setInterval(check, 15000);
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [router, timezone]);
  const link = (href: string, label: string) =>
    <Link href={href} prefetch={false} aria-current={path === href ? "page" : undefined}>{label}</Link>;
  return <header className="topbar">
    <Link className="brand" href="/" prefetch={false}>Outreach Table</Link>
    <nav aria-label="Sections">{link("/", "Leads")}{link("/analytics", "Analytics")}</nav>
    <span className="who muted">{sender}</span>
  </header>;
}
