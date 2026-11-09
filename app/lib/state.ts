import { CHANNELS, type Channel, type Lead, type Stage, type Status, type Touch } from "./types";

export function channelInactive(lead: Lead, channel: Channel): string | null {
  return channel === "instagram" || channel === "facebook" ? lead[`${channel}_inactive`] ?? null : null;
}
export const hasChannel = (lead: Lead, channel: Channel) => Boolean(lead[channel]?.trim());
/** An inactive channel counts as missing: it is never batched and never has to be ticked. */
export function activeChannels(lead: Lead): Channel[] {
  return CHANNELS.filter((c) => hasChannel(lead, c) && !channelInactive(lead, c));
}
/** Done today only when every active channel is ticked (sent) or skipped for that date. */
export function doneToday(lead: Lead, touches: Touch[], date: string): boolean {
  return activeChannels(lead).every((channel) => touches.some((t) =>
    t.lead_id === lead.id && t.channel === channel && t.date === date && (t.kind === "sent" || t.kind === "skipped")));
}
/** Highest-priority fact wins. Ticks never change the stage; "contacted" is a date set by hand. */
export function statusOf(lead: Lead, touches: Touch[], inTodaysBatch = false, date = ""): Status {
  const kinds = new Set(touches.filter((t) => t.lead_id === lead.id).map((t) => t.kind));
  if (lead.disqualified) return "disqualified";
  if (kinds.has("not_interested")) return "not_interested";
  if (kinds.has("meeting")) return "meeting";
  if (kinds.has("asset_sent")) return "asset_sent";
  if (kinds.has("reply")) return "replied";
  if (lead.contacted_on) return "contacted";
  if (inTodaysBatch && !doneToday(lead, touches, date)) return "today";
  if (!activeChannels(lead).length) return "no_channel";
  return "new";
}
/** Operational states get no pipeline step of their own. */
export function stageOf(status: Status): Stage {
  return status === "today" || status === "no_channel" ? "new" : status;
}
