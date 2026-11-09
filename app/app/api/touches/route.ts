import { writeTouch } from "../../../lib/db";
import { fail, objectBody } from "../../../lib/api";
import { CHANNELS, KINDS, type Channel, type Kind } from "../../../lib/types";
export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const { lead_id, channel, kind, text } = await objectBody(request);
    if (typeof lead_id !== "string" || !lead_id || !CHANNELS.includes(channel as Channel) || !KINDS.includes(kind as Kind) ||
      (text !== undefined && text !== null && typeof text !== "string"))
      throw new Error("Check lead_id, channel, kind and text.");
    return Response.json({ ok: true, action: writeTouch(lead_id, channel as Channel, kind as Kind, (text as string | null | undefined) ?? null) });
  } catch (error) { return fail(error, "Could not save the touch."); }
}
