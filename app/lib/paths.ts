import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";

export interface Locations { appDir: string; repoRoot: string }
let cached: Locations | undefined;

/** Finds app/ and the repo root without relying on process.cwd() being app/. OUTREACH_ROOT overrides the root. */
export function locate(): Locations {
  if (cached) return cached;
  const forced = process.env.OUTREACH_ROOT;
  if (forced) return (cached = { repoRoot: resolve(forced), appDir: resolve(forced, "app") });
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    if (existsSync(resolve(dir, "lib/schema.sql")) && existsSync(resolve(dir, "package.json")))
      return (cached = { appDir: dir, repoRoot: dirname(dir) });
    if (existsSync(resolve(dir, "app/lib/schema.sql")))
      return (cached = { appDir: resolve(dir, "app"), repoRoot: dir });
    dir = dirname(dir);
  }
  throw new Error("Cannot locate the app directory (expected app/lib/schema.sql above the working directory).");
}
