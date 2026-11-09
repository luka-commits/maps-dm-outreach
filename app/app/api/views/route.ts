import { deleteView, saveView } from "../../../lib/db";
import { fail, objectBody } from "../../../lib/api";
export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await objectBody(request);
    saveView(body.name, body.view);
    return Response.json({ ok: true });
  } catch (error) { return fail(error, "Could not save the view."); }
}

export async function DELETE(request: Request) {
  try {
    deleteView((await objectBody(request)).name);
    return Response.json({ ok: true });
  } catch (error) { return fail(error, "Could not delete the view."); }
}
