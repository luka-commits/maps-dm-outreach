// Starts `next dev` or `next start` on the port from outreach.config.json (falls back to the example, then 4319).
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = dirname(appDir);
let port = 4319;
for (const name of ["outreach.config.json", "outreach.config.example.json"]) {
  const file = resolve(root, name);
  if (!existsSync(file)) continue;
  try {
    const value = Number(JSON.parse(readFileSync(file, "utf8")).app_port);
    if (Number.isInteger(value) && value > 0 && value < 65536) { port = value; break; }
  } catch { /* try the next file */ }
}
if (process.env.PORT) port = Number(process.env.PORT) || port;
const mode = process.argv[2] === "start" ? "start" : "dev";
const bin = resolve(appDir, "node_modules/next/dist/bin/next");
console.log(`Outreach Table: http://127.0.0.1:${port}`);
const child = spawn(process.execPath, [bin, mode, "--hostname", "127.0.0.1", "-p", String(port)], { cwd: appDir, stdio: "inherit" });
child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
