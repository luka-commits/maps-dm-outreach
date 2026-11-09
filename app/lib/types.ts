export const CHANNELS = ["instagram", "facebook", "linkedin"] as const;
export type Channel = (typeof CHANNELS)[number];
export const KINDS = ["sent", "skipped", "reply", "asset_sent", "meeting", "not_interested"] as const;
export type Kind = (typeof KINDS)[number];
/** Pipeline stages a user can set. Operational states (today, no_channel) are derived, never set. */
export const STAGES = ["new", "contacted", "replied", "asset_sent", "meeting", "not_interested", "disqualified"] as const;
export type Stage = (typeof STAGES)[number];
export type Status = Stage | "today" | "no_channel";

export interface Lead {
  id: string; name: string; category: string | null; address: string | null; postcode: string | null;
  town: string | null; region: string | null; country: string | null; lat: number | null; lng: number | null;
  phone: string | null; website: string | null; rating: number | null; reviews: number | null;
  instagram: string | null; facebook: string | null; linkedin: string | null;
  neighbour_town: string | null; neighbour_town_manual: string | null; owner_name: string | null;
  opener: string | null; notes: string | null; niche: string | null; run: string | null;
  imported_at: string; contacted_on: string | null; disqualified: string | null;
  instagram_inactive: string | null; facebook_inactive: string | null; strategy: string | null;
  // Computed on read, never stored.
  strategy_name?: string | null; message?: string | null; missing?: string | null;
}
export interface Touch {
  id: number; lead_id: string; channel: Channel; kind: Kind; date: string;
  text: string | null; created_at: string; strategy: string | null;
}
/** What "New" removed, so Undo can put it back. */
export type Undo = Touch | { lead_id: string; contacted_on: string };

export const CHANNEL_LABEL: Record<Channel, string> = { instagram: "Instagram", facebook: "Facebook", linkedin: "LinkedIn" };
export const STAGE_LABEL: Record<Stage, string> = {
  new: "New", contacted: "Contacted", replied: "Replied", asset_sent: "Asset sent", meeting: "Meeting",
  not_interested: "Not interested", disqualified: "Disqualified",
};
export const STATUS_LABEL: Record<Status, string> = { ...STAGE_LABEL, today: "Today", no_channel: "No channel" };
export const KIND_LABEL: Record<Kind, string> = {
  sent: "Sent", skipped: "Skipped", reply: "Reply", asset_sent: "Asset sent", meeting: "Meeting", not_interested: "Not interested",
};
