import type { Metadata } from "next";
import { Header } from "@/components/Header";
import { loadConfig } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = { title: "Outreach Table", description: "Local outreach table for hand-sent DMs with split-tested strategies." };
export const dynamic = "force-dynamic";

export default function Layout({ children }: { children: React.ReactNode }) {
  const config = loadConfig();
  return <html lang="en"><body><Header sender={config.sender_name} timezone={config.timezone} />{children}</body></html>;
}
