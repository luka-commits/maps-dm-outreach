export const fail = (error: unknown, fallback: string, status = 400) =>
  Response.json({ error: error instanceof Error ? error.message : fallback }, { status });

/** Parses a JSON object body; anything else is a 400 for the caller. */
export async function objectBody(request: Request): Promise<Record<string, unknown>> {
  let body: unknown;
  try { body = await request.json(); } catch { throw new Error("The request body must be JSON."); }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("The request body must be a JSON object.");
  return body as Record<string, unknown>;
}
