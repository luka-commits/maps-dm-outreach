import { CHANNELS, type Channel, type Touch } from "./types";
import type { Strategy } from "./strategies";

export interface AnalyticsRow {
  strategy: string; name: string; channel: Channel | "total";
  sent: number; replied: number; reply_rate: number; asset_sent: number; meetings: number; not_interested: number;
}

/**
 * One row per strategy and channel. The cohort is every lead with a `sent` touch carrying that strategy snapshot (on that channel
 * for channel rows), so a lead whose strategy was switched later still counts where it was actually sent.
 */
export function analytics(strategies: Strategy[], touches: Touch[]): AnalyticsRow[] {
  const byLead = new Map<string, Touch[]>();
  for (const t of touches) byLead.set(t.lead_id, [...(byLead.get(t.lead_id) ?? []), t]);
  const ids = new Set(strategies.map((s) => s.id));
  for (const t of touches) if (t.kind === "sent" && t.strategy) ids.add(t.strategy);
  const names = new Map(strategies.map((s) => [s.id, s.name]));
  const rows: AnalyticsRow[] = [];
  for (const strategy of ids) {
    for (const channel of [...CHANNELS, "total"] as const) {
      const cohort = new Set<string>();
      for (const t of touches) if (t.kind === "sent" && t.strategy === strategy && (channel === "total" || t.channel === channel)) cohort.add(t.lead_id);
      const row: AnalyticsRow = { strategy, name: names.get(strategy) ?? strategy, channel, sent: cohort.size, replied: 0, reply_rate: 0, asset_sent: 0, meetings: 0, not_interested: 0 };
      for (const id of cohort) {
        const kinds = new Set((byLead.get(id) ?? []).filter((t) => channel === "total" || t.channel === channel).map((t) => t.kind));
        row.replied += Number(kinds.has("reply"));
        row.asset_sent += Number(kinds.has("asset_sent"));
        row.meetings += Number(kinds.has("meeting"));
        row.not_interested += Number(kinds.has("not_interested"));
      }
      row.reply_rate = row.sent ? (100 * row.replied) / row.sent : 0;
      rows.push(row);
    }
  }
  return rows;
}
