import { restoreStages, setStage } from "../../../lib/db";
import { fail, objectBody } from "../../../lib/api";
export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await objectBody(request);
    if (Object.hasOwn(body, "restore")) return Response.json({ ok: true, restored: restoreStages(body.restore) });
    return Response.json({ ok: true, ...setStage(body.lead_ids, body.stage) });
  } catch (error) { return fail(error, "Could not change the stage."); }
}
