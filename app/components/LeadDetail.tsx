import { CHANNEL_LABEL, KIND_LABEL, STATUS_LABEL, type Lead, type Status, type Touch } from "@/lib/types";
import { activeChannels, channelInactive, hasChannel } from "@/lib/state";
import { neighbourFor } from "@/lib/message";
import type { Strategy } from "@/lib/strategies";
import { CHANNELS } from "@/lib/types";
import { SavedField } from "./SavedField";
import { NotesField } from "./NotesField";
import { StrategyPicker } from "./StrategyPicker";
import { CopyButton } from "./CopyButton";
import { LogResult } from "./LogResult";

export function LeadDetail({ lead, history, status, strategies, current, timezone }: {
  lead: Lead; history: Touch[]; status: Status; strategies: Strategy[]; current?: Strategy; timezone: string;
}) {
  const channels = activeChannels(lead);
  const href = (u: string) => (/^https?:\/\//i.test(u) ? u : `https://${u}`);
  return <article>
    <header className="lead-head">
      <p className="eyebrow">Lead</p><h1>{lead.name}</h1>
      <p className="muted">{[lead.town, lead.region, lead.country].filter(Boolean).join(" · ")}</p>
      <span className="pill">{STATUS_LABEL[status]}</span>
    </header>

    <section className="section"><h2>Business</h2><dl>
      <dt>Address</dt><dd>{lead.address || "No address"}</dd>
      <dt>Category</dt><dd>{lead.category || "Not given"}</dd>
      <dt>Owner</dt><dd>{lead.owner_name || "Not found"}</dd>
      <dt>Website</dt><dd>{lead.website ? <a href={href(lead.website)} target="_blank" rel="noreferrer">{lead.website.replace(/^https?:\/\//, "")}</a> : "No website"}</dd>
      <dt>Phone</dt><dd>{lead.phone || "Not given"}</dd>
      <dt>Rating</dt><dd>{lead.rating === null ? "Not given" : `${lead.rating.toLocaleString("en")} / 5 · ${lead.reviews ?? 0} reviews`}</dd>
      {CHANNELS.filter((c) => c !== "linkedin" && hasChannel(lead, c)).map((c) => {
        const off = channelInactive(lead, c);
        return <div className="pair" key={c}><dt>{CHANNEL_LABEL[c]}</dt><dd>
          <a href={lead[c]!} target="_blank" rel="noreferrer">{lead[c]}</a>
          {off && <span className="muted"> · inactive: {off}</span>}</dd></div>;
      })}
      <dt>LinkedIn</dt><dd><SavedField key={lead.id} id={lead.id} field="linkedin" value={lead.linkedin} label={`LinkedIn profile: ${lead.name}`} type="url" placeholder="Paste a linkedin.com/in/… or /company/… link" />
        {lead.linkedin && <a href={lead.linkedin} target="_blank" rel="noreferrer" className="muted">Open profile</a>}</dd>
    </dl></section>

    <section className="section"><h2>Strategy and message</h2><div>
      <StrategyPicker key={lead.id} id={lead.id} value={lead.strategy} options={strategies.map((s) => ({ id: s.id, name: s.name }))} />
      {current && <p className="muted" style={{ marginTop: 6 }}>{current.summary}</p>}
      {lead.message ? <><p className="quote">{lead.message}</p><CopyButton text={lead.message} /></>
        : <p className="warn" style={{ margin: "10px 0" }}>{lead.missing ?? "No message"}. Fill in the field below.</p>}
      {current?.follow_up && <p className="muted" style={{ marginTop: 10 }}><strong>After they reply:</strong> {current.follow_up.replace(/\{(\w+)\}/g, (m, k) => k === "towns" ? [lead.town, neighbourFor(lead)].filter(Boolean).join(" and ") : k === "neighbour_town" ? neighbourFor(lead) ?? m : m)}</p>}
    </div></section>

    <section className="section"><h2>Opener</h2><div>
      <SavedField key={lead.id} id={lead.id} field="opener" value={lead.opener} label="Opener" multiline placeholder="One personal line about a recent post" />
      <p className="muted">Used by strategies that need an opener. Saved when you leave the field.</p></div></section>

    <section className="section"><h2>Neighbour town</h2><div>
      <SavedField key={lead.id} id={lead.id} field="neighbour_town_manual" value={lead.neighbour_town_manual} label="Neighbour town override" placeholder="Override the computed neighbour town" />
      <p className="muted">Computed: {lead.neighbour_town ?? "none"}</p></div></section>

    <section className="section"><h2>Notes</h2><NotesField key={lead.id} id={lead.id} text={lead.notes} rows={3} /></section>
    <section className="section"><h2>Log result</h2><LogResult key={lead.id} leadId={lead.id} channels={channels} /></section>

    <section className="section"><h2>History <span className="muted">{history.length}</span></h2>
      {history.length ? <ol className="history">{history.map((t) => <li key={t.id}><span className="dot" /><div>
        <strong>{KIND_LABEL[t.kind]}</strong><span className="muted"> · {CHANNEL_LABEL[t.channel]}{t.strategy ? ` · ${t.strategy}` : ""}</span>
        {t.text && <p>{t.text}</p>}
        <time dateTime={t.created_at}>{new Date(t.created_at).toLocaleString("en-GB", { timeZone: timezone, dateStyle: "medium", timeStyle: "short" })}</time></div></li>)}</ol>
        : <p className="muted">No touches yet.</p>}</section>
  </article>;
}
