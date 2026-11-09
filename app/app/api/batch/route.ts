import { pullBatch, todaysBatch, today } from "../../../lib/db";
import { fail, objectBody } from "../../../lib/api";
import { loadStrategies } from "../../../lib/strategies";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Today's batch with what a skill needs (for example to write openers): who needs one, and where to look. */
export async function GET() {
  try {
    const { byId } = loadStrategies();
    const leads = todaysBatch().map((l) => ({
      id: l.id, name: l.name, town: l.town, instagram: l.instagram, opener: l.opener, strategy: l.strategy,
      needs_opener: byId.get(l.strategy ?? "")?.needs_opener === true && !l.opener?.trim() && !!l.instagram,
      message: l.message, missing: l.missing,
    }));
    return Response.json({ date: today(), leads });
  } catch (error) { return fail(error, "Could not read the batch.", 500); }
}

export async function POST(request: Request) {
  try {
    const { count } = await objectBody(request);
    if (typeof count !== "number" || !Number.isSafeInteger(count) || count < 1) throw new Error("Please enter a positive whole number.");
    return Response.json({ ok: true, pulled: pullBatch(count) });
  } catch (error) { return fail(error, "Could not pull a batch."); }
}
