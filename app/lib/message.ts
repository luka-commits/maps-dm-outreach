import type { Config } from "./config";
import type { Lead } from "./types";
import type { Strategy } from "./strategies";

// ---- owner and town helpers ------------------------------------------------------------------------------------
const TITLES = new Set(["mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir"]);
export function firstName(owner: string | null | undefined): string {
  const parts = (owner ?? "").trim().split(/\s+/).filter(Boolean);
  let first = parts[0]?.replace(/\.$/, "") ?? "";
  if (TITLES.has(first.toLowerCase())) first = parts[1] ?? "";
  return /^[\p{L}][\p{L}'’-]*$/u.test(first) ? first : "";
}

// Leading words that are part of a place name, not a city ("West Bromwich" and "St Albans" are single towns).
const TOWN_PREFIXES = new Set(["north", "south", "east", "west", "upper", "lower", "great", "little", "new", "old", "st", "st.", "saint", "mount", "port", "market", "royal", "kings", "king's", "long", "high", "bad", "sankt"]);
const lc = (v: string | null | undefined) => (v ?? "").trim().toLowerCase();

/** City part of a town name: "Leeds Headingley" -> "leeds", "St Albans Fleetville" -> "st albans". */
export function cityKey(town: string | null | undefined): string {
  const words = (town ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  return words.slice(0, TOWN_PREFIXES.has(words[0].toLowerCase()) && words.length > 1 ? 2 : 1).join(" ").toLowerCase();
}

/** A neighbour in the same city reads better as the district alone: "Leeds Headingley" next to "Leeds" -> "Headingley". */
export function shortTown(neighbour: string, ownTown: string | null | undefined): string {
  const city = neighbour.split(" ")[0];
  const sameCity = neighbour.includes(" ") && !TOWN_PREFIXES.has(city.toLowerCase()) && (ownTown ?? "").trim().split(" ")[0].toLowerCase() === city.toLowerCase();
  return sameCity ? neighbour.slice(city.length + 1).trim() : neighbour;
}

export function neighbourFor(lead: Pick<Lead, "neighbour_town" | "neighbour_town_manual" | "town">): string | null {
  const manual = lead.neighbour_town_manual?.trim();
  if (manual) return manual;
  const auto = lead.neighbour_town?.trim();
  return auto ? shortTown(auto, lead.town) : null;
}

// ---- trade -----------------------------------------------------------------------------------------------------
/** "roofer" -> "roofers", "hair-salon" -> "hair salons", "bakery" -> "bakeries". */
export function pluralTrade(niche: string | null | undefined): string {
  const words = (niche ?? "").replace(/[-_]+/g, " ").trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return "local businesses";
  const last = words[words.length - 1];
  let plural = last;
  if (/[^aeiou]y$/.test(last)) plural = `${last.slice(0, -1)}ies`;
  else if (/(ch|sh|x|z)$/.test(last)) plural = `${last}es`;
  else if (!last.endsWith("s")) plural = `${last}s`;
  words[words.length - 1] = plural;
  return words.join(" ");
}

// ---- competitor ------------------------------------------------------------------------------------------------
const LEGAL = /[,\s]+(?:pty\.?\s+ltd|pty|ltd|limited|llc|l\.l\.c|inc|incorporated|corp|corporation|plc|llp|gmbh|ag|sarl|b\.?v)\.?$/i;
const MAX_NAME = 30;

/** The name a person would say out loud: no legal suffix, no "| tagline", no brackets, short. */
export function cleanName(name: string, town?: string | null): string {
  let short = name.split(/\s[|–—-]\s/)[0].replace(/\([^)]*\)/g, "").replace(/\s+/g, " ").trim();
  for (let i = 0; i < 3 && LEGAL.test(short); i++) short = short.replace(LEGAL, "").trim();
  short = short.replace(/[,&\s]+$/, "");
  if (short.length <= MAX_NAME) return short;
  const townWord = cityKey(town);
  if (townWord) {
    const words = short.split(" ");
    if (words.length >= 3) short = words.filter((w) => w.toLowerCase() !== townWord).join(" ");
  }
  // "AOS Roofing Leeds & Roof Repairs Wakefield" -> first half, but only when that half is a real name (two words or more).
  for (const separator of [" & ", " and "]) {
    const head = short.split(separator)[0];
    if (short.length > MAX_NAME && short.includes(separator) && head.split(" ").length >= 2) short = head;
  }
  if (short.length > MAX_NAME) {
    const words = short.split(" ");
    while (words.length > 1 && words.join(" ").length > MAX_NAME) words.pop();
    short = words.join(" ");
  }
  return short.replace(/[,&\s]+$/, "").trim();
}

type CompetitorInput = Pick<Lead, "id" | "name" | "town" | "region" | "reviews" | "niche">;
interface Candidate { id: string; name: string; reviews: number }

/**
 * Per lead: the business with the most reviews (at least 10) in the same town, else the same region, within the same niche,
 * never the lead itself and never a branch with the same cleaned name. Null when nobody qualifies.
 */
export function competitorsFor(leads: readonly CompetitorInput[]): Map<string, string | null> {
  const towns = new Map<string, Candidate[]>();
  const regions = new Map<string, Candidate[]>();
  const push = (map: Map<string, Candidate[]>, key: string, c: Candidate) => map.set(key, [...(map.get(key) ?? []), c]);
  for (const lead of leads) {
    if (lead.reviews === null || lead.reviews === undefined || lead.reviews < 10) continue;
    const name = cleanName(lead.name, lead.town);
    if (!name) continue;
    const c = { id: lead.id, name, reviews: lead.reviews };
    const niche = lc(lead.niche);
    if (cityKey(lead.town)) push(towns, `${niche}|${cityKey(lead.town)}`, c);
    if (lc(lead.region)) push(regions, `${niche}|${lc(lead.region)}`, c);
  }
  for (const list of [...towns.values(), ...regions.values()]) list.sort((a, b) => b.reviews - a.reviews || a.id.localeCompare(b.id));
  const result = new Map<string, string | null>();
  for (const lead of leads) {
    const own = cleanName(lead.name, lead.town).toLowerCase();
    const generic = new Set([lc(lead.niche), pluralTrade(lead.niche), lc(lead.niche).replace(/[-_]+/g, " ")]);
    const niche = lc(lead.niche);
    const usable = (c: Candidate) => c.id !== lead.id && c.name.toLowerCase() !== own && !generic.has(c.name.toLowerCase());
    const found = towns.get(`${niche}|${cityKey(lead.town)}`)?.find(usable) ?? regions.get(`${niche}|${lc(lead.region)}`)?.find(usable);
    result.set(lead.id, found?.name ?? null);
  }
  return result;
}

// ---- rendering -------------------------------------------------------------------------------------------------
const REQUIRED_LABEL: Record<string, string> = {
  neighbour_town: "Neighbour town", town: "Town", opener: "Opener", owner_name: "Owner name", first_name: "First name",
  competitor: "Competitor", region: "Region", trade: "Trade",
};

export interface Rendered { text: string | null; missing: string | null }

export function renderMessage(
  lead: Pick<Lead, "town" | "neighbour_town" | "neighbour_town_manual" | "owner_name" | "opener" | "niche">,
  strategy: Strategy, config: Pick<Config, "sender_name" | "offer">, competitor: string | null,
): Rendered {
  const opener = lead.opener?.trim() ?? "";
  const town = lead.town?.trim() ?? "";
  const neighbour = neighbourFor(lead) ?? "";
  const first = firstName(lead.owner_name);
  if (strategy.needs_opener && !opener) return { text: null, missing: "Opener missing" };
  const have: Record<string, string> = { neighbour_town: neighbour, town, opener, first_name: first, owner_name: lead.owner_name?.trim() ?? "", competitor: competitor ?? "" };
  for (const field of strategy.requires)
    if (field in have && !have[field]) return { text: null, missing: `${REQUIRED_LABEL[field] ?? field} missing` };
  const distinct = neighbour && neighbour.toLowerCase() !== town.toLowerCase() && shortTown(neighbour, town).toLowerCase() !== town.toLowerCase();
  const values: Record<string, string> = {
    greeting: first ? `Hey ${first},` : "Hey,",
    first_name: first,
    town,
    neighbour_town: neighbour,
    towns: town && distinct ? `${town} and ${neighbour}` : town || neighbour,
    competitor: competitor ?? "",
    competitor_clause: competitor ? `so you can get past ${competitor}` : "so you rank higher on Google",
    opener,
    trade: pluralTrade(lead.niche),
    offer_service: config.offer.service,
    offer_promise: config.offer.promise,
    sender_name: config.sender_name,
  };
  const text = strategy.template.replace(/\{(\w+)\}/g, (whole, key: string) => (key in values ? values[key] : whole)).trim();
  return { text, missing: null };
}
