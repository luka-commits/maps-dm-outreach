import { leadById, touchesFor, updateLead, type LeadPatch } from "../../../../lib/db";
import { fail, objectBody } from "../../../../lib/api";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const FIELDS = ["opener", "notes", "neighbour_town_manual", "linkedin", "strategy"];

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await context.params;
    const lead = leadById(id);
    if (!lead) return Response.json({ error: "Lead not found." }, { status: 404 });
    return Response.json({ lead, touches: touchesFor(id) });
  } catch (error) { return fail(error, "Could not read the lead.", 500); }
}

export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }) {
  try {
    const body = await objectBody(request);
    if (Object.keys(body).some((key) => !FIELDS.includes(key)))
      throw new Error(`Only ${FIELDS.join(", ")} can be changed.`);
    const { id } = await context.params;
    updateLead(id, body as LeadPatch);
    return Response.json({ ok: true });
  } catch (error) { return fail(error, "Could not save the change."); }
}
