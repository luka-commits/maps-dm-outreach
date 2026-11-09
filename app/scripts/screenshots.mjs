// Verifies the main flows in a real browser and writes the documentation screenshots.
//   BASE=http://127.0.0.1:4391 EMPTY_BASE=http://127.0.0.1:4392 node scripts/screenshots.mjs <output-dir>
// BASE must serve a seeded demo database (npm run seed-demo); EMPTY_BASE a database without leads.
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const out = resolve(process.argv[2] ?? "../docs/screenshots");
mkdirSync(out, { recursive: true });
const base = process.env.BASE ?? "http://127.0.0.1:4391";
const emptyBase = process.env.EMPTY_BASE;
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const context = await browser.newContext({ viewport: { width: 1440, height: 860 }, permissions: ["clipboard-read", "clipboard-write"] });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const log = (s) => console.log("ok  " + s);

await page.goto(base);
await page.getByRole("heading", { name: "Analytics" }).waitFor({ state: "detached" }).catch(() => {});
await page.getByLabel("Search leads").waitFor();
log("table renders");
const initialRows = await page.locator("tbody tr").count();
assert.ok(initialRows > 0);

// Pull batch
await page.getByLabel("Batch size").fill("3");
await page.getByRole("button", { name: "Pull batch" }).click();
await page.getByText(/added to today's batch/).waitFor();
log("pull batch: " + (await page.getByText(/added to today's batch/).innerText()));
assert.equal(await page.evaluate(() => localStorage.getItem("outreach.batchCount")), "3");

// Today view
await page.getByRole("button", { name: /^Today ·/ }).click();
await page.waitForTimeout(300);
const todayRows = await page.locator("tbody tr").count();
assert.ok(todayRows >= 8, `today rows ${todayRows}`);
log(`today view shows ${todayRows} leads`);

// Copy + tick on a lead that has Facebook and no send yet
const candidate = page.locator("tbody tr", { has: page.locator('[aria-label^="Facebook sent:"][aria-pressed="false"]') }).first();
const leadId = await candidate.getAttribute("data-lead");
const row = page.locator(`tbody tr[data-lead="${leadId}"]`);
const name = (await row.locator("td[data-column=name]").innerText()).trim();
const tick = row.locator('[aria-label^="Facebook sent:"]');
await row.locator('a[aria-label^="Open Facebook"]').evaluate((a) => a.addEventListener("click", (e) => e.preventDefault()));
await row.locator('a[aria-label^="Open Facebook"]').click();
const copied = await page.evaluate(() => navigator.clipboard.readText());
assert.ok(copied.length > 5, "clipboard has the message");
log(`copied message for ${name}: "${copied.slice(0, 60)}"`);
await tick.click();
await page.waitForFunction((n) => [...document.querySelectorAll("tbody tr")].find((r) => r.innerText.includes(n))?.querySelector('[aria-label^="Facebook sent:"]')?.getAttribute("aria-pressed") === "true", name);
log("tick logged (aria-pressed true)");
await tick.click();
await page.waitForFunction((n) => [...document.querySelectorAll("tbody tr")].find((r) => r.innerText.includes(n))?.querySelector('[aria-label^="Facebook sent:"]')?.getAttribute("aria-pressed") === "false", name);
log("same button untoggles today's tick");
await tick.click();

// Stage change and undo
const stageValue = (v) => page.waitForFunction(([id, want]) => document.querySelector(`tr[data-lead="${id}"] select`)?.value === want, [leadId, v]);
const stageSelect = row.locator('select[aria-label^="Stage:"]');
await stageSelect.selectOption("replied");
await page.getByText(/stage entr/).first().waitFor();
await stageValue("replied");
log("stage set to Replied");
await stageSelect.selectOption("new");
await page.getByRole("button", { name: "Undo" }).waitFor();
await stageValue("new");
await page.getByRole("button", { name: "Undo" }).click();
await page.getByText("Stage entry restored.").waitFor();
await stageValue("replied");
log("New withdrew the entry, Undo restored it");

// Table screenshot (leave Today view for a fuller table)
await page.getByRole("button", { name: /^Today ·/ }).click();
await page.getByRole("button", { name: "Dismiss message" }).click().catch(() => {});
await page.waitForTimeout(400);
await page.screenshot({ path: resolve(out, "table.png") });

// Drawer
await page.locator("td[data-column=name] a").first().click();
await page.getByRole("dialog").waitFor();
await page.getByLabel("Opener").waitFor();
await page.getByLabel("Opener").fill("love the slate work on Mill Lane");
await page.getByLabel("Opener").blur();
await page.getByText("Saved").first().waitFor();
log("drawer opened, opener saved on blur");
const first = await page.getByRole("dialog").getAttribute("aria-label");
await page.keyboard.press("ArrowRight");
await page.waitForFunction((f) => document.querySelector('[role=dialog]')?.getAttribute("aria-label") !== f, first);
log("arrow key moves to the next lead");
await page.keyboard.press("ArrowLeft");
await page.waitForFunction((f) => document.querySelector('[role=dialog]')?.getAttribute("aria-label") === f, first);
await page.screenshot({ path: resolve(out, "drawer.png") });
await page.keyboard.press("Escape");
await page.getByRole("dialog").waitFor({ state: "detached" });
log("Escape closes the drawer");

// Column picker, filter, saved view
await page.getByRole("button", { name: /^Columns/ }).click();
await page.getByRole("button", { name: "Phone", exact: true }).click();
await page.keyboard.press("Escape");
assert.ok(await page.locator('th[data-column=phone]').count());
log("column picker adds a column");
await page.getByRole("button", { name: "Filter Town" }).click();
await page.getByLabel("Harrowfield", { exact: true }).check();
await page.getByRole("button", { name: "Done" }).click();
await page.waitForTimeout(300);
const filtered = await page.locator("tbody tr").count();
assert.ok(filtered > 0 && filtered < 25);
log(`town filter leaves ${filtered} leads`);
await page.getByRole("button", { name: /^Saved views/ }).click();
await page.getByLabel("Name of the view").fill("Harrowfield only");
await page.getByRole("button", { name: "Save", exact: true }).click();
await page.getByText('Saved "Harrowfield only".').waitFor();
log("saved view stored");
await page.keyboard.press("Escape");

// Bulk
await page.getByRole("button", { name: "Clear filters" }).click();
await page.getByLabel("Select all on this page").check();
await page.getByRole("button", { name: "Mark sent" }).click();
await page.getByText(/marked as sent/).waitFor();
log("bulk mark sent: " + (await page.getByText(/marked as sent/).innerText()));

// Analytics
await page.goto(base + "/analytics");
await page.getByRole("heading", { name: "Analytics" }).waitFor();
assert.ok(await page.locator("table").count() >= 1);
await page.screenshot({ path: resolve(out, "analytics.png"), fullPage: true });
log("analytics renders");

// Mobile width
const phone = await browser.newPage({ viewport: { width: 390, height: 800 } });
await phone.goto(base);
await phone.getByLabel("Search leads").waitFor();
const overflowX = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
assert.equal(overflowX, false, "no page-level horizontal scroll at 390px");
log("390px: page does not scroll sideways, the table scrolls inside its frame");
await phone.screenshot({ path: resolve(out, "mobile.png") });

if (emptyBase) {
  const empty = await context.newPage();
  await empty.goto(emptyBase);
  await empty.getByRole("heading", { name: "No leads yet" }).waitFor();
  await empty.screenshot({ path: resolve(out, "empty-state.png") });
  log("empty state renders");
}
await browser.close();
if (errors.length) { console.log("browser errors:\n" + errors.join("\n")); process.exitCode = 1; } else console.log("no console errors");
