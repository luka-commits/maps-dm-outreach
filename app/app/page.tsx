import { allBatches, allLeads, allTouches, leadCount, savedViews, today, todaysBatch, touchesFor } from "@/lib/db";
import { loadConfig } from "@/lib/config";
import { loadStrategies } from "@/lib/strategies";
import { buildRows } from "@/lib/table";
import { statusOf } from "@/lib/state";
import { LeadTable } from "@/components/LeadTable";
import { DrawerShell } from "@/components/DrawerShell";
import { LeadDetail } from "@/components/LeadDetail";
import { EmptyState } from "@/components/EmptyState";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  if (leadCount() === 0) return <main className="page"><EmptyState /></main>;
  const config = loadConfig();
  const date = today();
  const leads = allLeads();
  const rows = buildRows(leads, allTouches(), allBatches(), date);
  const id = typeof params.lead === "string" ? params.lead : undefined;
  const set = loadStrategies();
  let drawer = null;
  if (id) {
    const lead = leads.find((l) => l.id === id);
    if (!lead) drawer = <p role="alert" className="err">Lead not found.</p>;
    else {
      const history = touchesFor(id);
      const ids = rows.map((r) => r.lead.id);
      const i = ids.indexOf(id);
      const url = (to?: string) => { const p = new URLSearchParams(); if (params.view === "today") p.set("view", "today"); if (to) p.set("lead", to); return `/?${p}`; };
      const batchIds = new Set(todaysBatch(date).map((l) => l.id));
      drawer = <DrawerShell title={`Lead: ${lead.name}`} prev={i > 0 ? url(ids[i - 1]) : undefined} next={i >= 0 && i < ids.length - 1 ? url(ids[i + 1]) : undefined} position={i + 1} total={ids.length}>
        <LeadDetail lead={lead} history={history} status={statusOf(lead, history, batchIds.has(id), date)} strategies={set.list}
          current={lead.strategy ? set.byId.get(lead.strategy) : undefined} timezone={config.timezone} />
      </DrawerShell>;
    }
  }
  return <main className="page">
    <LeadTable rows={rows} date={date} timezone={config.timezone} limits={config.daily_limits} views={savedViews()} todayDefault={params.view === "today"} />
    {drawer}
  </main>;
}
