/** Calendar day in an IANA timezone as YYYY-MM-DD. Date parts, never UTC slicing. */
export function dayIn(timeZone: string, moment = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(moment);
  const pick = (type: string) => parts.find((p) => p.type === type)!.value;
  return `${pick("year")}-${pick("month")}-${pick("day")}`;
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-11-09" -> "9 Nov". */
export function shortDay(day: string | null): string {
  if (!day) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : day;
}
