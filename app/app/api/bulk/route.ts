import { bulkMarkSent } from "../../../lib/db";
import { fail, objectBody } from "../../../lib/api";
export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await objectBody(request);
    return Response.json({ ok: true, ...bulkMarkSent(body.lead_ids, body.channel) });
  } catch (error) { return fail(error, "Could not save the bulk action."); }
}
