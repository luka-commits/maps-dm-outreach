import type { Strategy } from "./strategies";

export interface AssignInput { id: string; has_instagram: boolean }
export type Counts = Map<string, number>;
export const countKey = (hasInstagram: boolean, strategyId: string) => `${hasInstagram ? "ig" : "no-ig"}:${strategyId}`;

/**
 * Picks the strategy for one lead. Strategies that need an opener only go to leads with an active Instagram.
 * Among the eligible strategies the one used least so far wins (ties: config order); counts are kept per group
 * (with / without Instagram) so each group stays balanced on its own. No eligible strategy -> the fallback.
 */
export function pickStrategy(input: AssignInput, active: Strategy[], counts: Counts, fallback: string): string {
  const eligible = active.filter((s) => !s.needs_opener || input.has_instagram);
  if (!eligible.length) return fallback;
  let best = eligible[0];
  for (const s of eligible)
    if ((counts.get(countKey(input.has_instagram, s.id)) ?? 0) < (counts.get(countKey(input.has_instagram, best.id)) ?? 0)) best = s;
  const key = countKey(input.has_instagram, best.id);
  counts.set(key, (counts.get(key) ?? 0) + 1);
  return best.id;
}
