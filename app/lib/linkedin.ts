/** Only person or company profiles; posts, searches and foreign hosts are rejected. Returns the canonical URL. */
export function linkedinProfile(raw: unknown): string | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  let url: URL;
  try { url = new URL(/^https?:\/\//i.test(raw.trim()) ? raw.trim() : `https://${raw.trim()}`); } catch { return null; }
  const host = url.hostname.toLowerCase();
  if (host !== "linkedin.com" && host !== "www.linkedin.com" && !/^[a-z]{2,3}\.linkedin\.com$/.test(host)) return null;
  const [kind, slug, ...rest] = url.pathname.split("/").filter(Boolean);
  if (!["in", "company"].includes(kind?.toLowerCase() ?? "") || !slug || rest.length > 0 || !/^[\p{L}\p{N}_%.-]+$/u.test(slug)) return null;
  return `https://www.linkedin.com/${kind.toLowerCase()}/${slug}/`;
}
