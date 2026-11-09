// Fills the database named by OUTREACH_DB with invented businesses, for screenshots and demos.
// Refuses to run without OUTREACH_DB so it can never touch data/leads.db by accident.
//   OUTREACH_DB=/tmp/demo.db npm run seed-demo
import { allLeads, getDb, pullBatch, today, writeTouch } from "../lib/db";

if (!process.env.OUTREACH_DB) { console.error("Set OUTREACH_DB to a throwaway database path first."); process.exit(1); }
const db = getDb();
if ((db.prepare("SELECT COUNT(*) AS n FROM leads").get() as { n: number }).n > 0) { console.error("That database already has leads; use a fresh file."); process.exit(1); }

// Every business has an Instagram or a Facebook profile, as imported leads do.
type Seed = [name: string, town: string, owner: string | null, ig: boolean, fb: boolean, reviews: number, rating: number];
const towns = { Millbrook: { postcode: "MB1", lat: 53.8, lng: -1.55 }, Harrowfield: { postcode: "HF2", lat: 53.86, lng: -1.62 } };
const seeds: Seed[] = [
  ["Millbrook Roofing Co", "Millbrook", "Dan Whitaker", true, true, 212, 4.8],
  ["Ironbridge Roof Repairs Ltd", "Millbrook", null, true, false, 148, 4.7],
  ["Slate & Tile Specialists", "Millbrook", "Priya Nair", false, true, 96, 4.6],
  ["Northshire Flat Roof Experts", "Millbrook", "Tom Ellery", true, true, 64, 4.9],
  ["A1 Roofline Services", "Millbrook", null, false, true, 33, 4.3],
  ["Greenfield Roofing LLC | Free quotes", "Millbrook", "Hannah Cole", true, false, 41, 4.5],
  ["Kestrel Roofing", "Millbrook", "Mr Ben Archer", true, true, 27, 4.4],
  ["Millbrook Leadwork", "Millbrook", null, false, true, 12, 4.1],
  ["Copperfield Roofers", "Millbrook", "Sam Okafor", true, false, 18, 4.6],
  ["Castle Street Roofing", "Millbrook", null, false, true, 8, 3.9],
  ["Harrowfield Roofing Ltd", "Harrowfield", "Gavin Marsh", true, true, 187, 4.8],
  ["Vale Roof Care", "Harrowfield", "Lena Fischer", true, true, 120, 4.7],
  ["Pennine Roofers (Harrowfield)", "Harrowfield", null, true, false, 77, 4.6],
  ["Summit Roof & Gutter Inc", "Harrowfield", "Carlos Mendes", false, true, 59, 4.5],
  ["Oakridge Roofing Services", "Harrowfield", "Dr Amara Obi", true, false, 38, 4.4],
  ["Beacon Roofing", "Harrowfield", null, false, true, 22, 4.2],
  ["Stonegate Slate Roofs", "Harrowfield", "Ruth Calder", true, true, 15, 4.7],
  ["Harrowfield Roof Doctors", "Harrowfield", "Ian Pryce", true, false, 11, 4.0],
  ["Pioneer Roof Tech", "Harrowfield", null, false, true, 6, 3.8],
  ["Weatherproof Roofers", "Harrowfield", "Mia Lindqvist", true, true, 52, 4.6],
  ["Riverside Roofing & Building", "Harrowfield", "Joe Barnett", true, false, 29, 4.3],
  ["Tilemaster Roofing", "Millbrook", "Nina Alvarez", true, true, 71, 4.7],
  ["Crown Roof Solutions", "Millbrook", null, false, true, 14, 4.2],
  ["Highland Roofing", "Harrowfield", "Callum Reid", true, false, 9, 4.1],
  ["Eaves & Gutters Co", "Harrowfield", null, false, true, 5, 3.7],
];
const insert = db.prepare(`INSERT INTO leads(id,name,category,address,postcode,town,region,country,lat,lng,phone,website,rating,reviews,instagram,facebook,
  neighbour_town,owner_name,niche,run,imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`);
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");
seeds.forEach(([name, town, owner, ig, fb, reviews, rating], i) => {
  const t = towns[town as keyof typeof towns];
  const other = town === "Millbrook" ? "Harrowfield" : "Millbrook";
  const key = slug(name).slice(0, 18);
  insert.run(`demo-${i + 1}`, name, "Roofing contractor", `${10 + i} Demo Street, ${town}`, `${t.postcode} ${i}AA`, town, "Northshire", "GB", t.lat, t.lng,
    `01234 5${String(i).padStart(5, "0")}`, `https://${key}.example.test`, rating, reviews,
    ig ? `https://www.instagram.com/${key}_example/` : null, fb ? `https://www.facebook.com/${key}.example/` : null,
    i % 5 === 4 ? `${other} Heights` : other, owner, "roofer", "GB-roofer-northshire", `2026-11-0${1 + (i % 5)}T09:00:00Z`);
});
db.prepare("UPDATE leads SET instagram_inactive = 'last post 2023-08-17' WHERE id = 'demo-9'").run();

const leads = allLeads();
const openers = ["love the slate job on Mill Lane, those lines are crisp", "that before and after of the chimney flashing is a proper transformation",
  "saw the storm repair you did last week, great turnaround", "nice work on the green roof extension"];
let k = 0;
for (const l of leads) if (l.instagram && !l.instagram_inactive && k < 12) {
  db.prepare("UPDATE leads SET opener = ? WHERE id = ?").run(openers[k % openers.length], l.id); k++;
}

// Earlier days: sent touches with snapshots, a few replies and stages.
const strategyOf = new Map(allLeads().map((l) => [l.id, l.strategy]));
const past = db.prepare("INSERT INTO touches(lead_id, channel, kind, date, text, created_at, strategy) VALUES (?,?,?,?,?,?,?)");
const day = (back: number) => { const d = new Date(Date.now() - back * 86400000); return d.toISOString().slice(0, 10); };
const history: [string, "instagram" | "facebook", number, string?][] = [
  ["demo-1", "instagram", 3, "reply"], ["demo-2", "instagram", 3], ["demo-3", "facebook", 3, "not_interested"], ["demo-4", "instagram", 2, "reply"],
  ["demo-6", "instagram", 2], ["demo-11", "instagram", 2, "reply"], ["demo-12", "instagram", 2, "meeting"], ["demo-13", "instagram", 1], ["demo-14", "facebook", 1],
  ["demo-20", "instagram", 1, "asset_sent"], ["demo-21", "instagram", 1],
];
for (const [id, channel, back, outcome] of history) {
  const date = day(back), at = `${date}T10:00:00Z`;
  past.run(id, channel, "sent", date, null, at, strategyOf.get(id) ?? null);
  if (outcome) past.run(id, channel, outcome, day(Math.max(0, back - 1)), null, `${day(Math.max(0, back - 1))}T14:00:00Z`, null);
}
db.prepare("UPDATE leads SET contacted_on = ? WHERE id IN ('demo-2','demo-6','demo-13')").run(day(2));
db.prepare("UPDATE leads SET notes = 'Owner asked for a quote on Friday.' WHERE id = 'demo-4'").run();

// Today's batch: pulled for real, a few ticks done.
pullBatch(8);
const batch = (db.prepare("SELECT lead_id FROM batches WHERE date = ? ORDER BY position").all(today()) as { lead_id: string }[]).map((r) => r.lead_id);
for (const id of batch.slice(0, 3)) {
  const lead = allLeads().find((l) => l.id === id)!;
  for (const c of ["instagram", "facebook"] as const) if (lead[c] && !(c === "instagram" && lead.instagram_inactive)) writeTouch(id, c, "sent");
}

console.log(`Seeded ${seeds.length} demo leads into ${process.env.OUTREACH_DB}; ${batch.length} in today's batch.`);
