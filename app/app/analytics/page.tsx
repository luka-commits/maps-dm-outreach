import { allTouches } from "@/lib/db";
import { loadConfig } from "@/lib/config";
import { activeStrategies, loadStrategies } from "@/lib/strategies";
import { analytics } from "@/lib/analytics";
import { CHANNEL_LABEL } from "@/lib/types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default function AnalyticsPage() {
  const touches = allTouches();
  const set = loadStrategies();
  const active = new Set(activeStrategies(loadConfig().active_strategies, set).map((s) => s.id));
  const rows = analytics(set.list, touches);
  const sentAnything = rows.some((r) => r.sent > 0);
  const strategyIds = [...new Set(rows.map((r) => r.strategy))].filter((id) => active.has(id) || rows.some((r) => r.strategy === id && r.sent > 0));
  return <main className="page analytics-page">
    <h1>Analytics</h1>
    <p className="muted">Each lead counts once per strategy and channel, by the strategy it was actually sent with. Below 30 sent per strategy a difference is noise.</p>
    {!sentAnything && <section className="panel" style={{ margin: "4vh 0" }}>
      <h2>Nothing sent yet</h2>
      <p>Pull a batch on the Leads page, send the messages by hand and tick each one. Once messages are logged, reply rates per strategy and channel show up here.</p>
    </section>}
    {strategyIds.map((id) => {
      const list = rows.filter((r) => r.strategy === id);
      return <section key={id}>
        <div className="strategy-title"><h2>{list[0].name}</h2><span className="muted">{id}{active.has(id) ? " · active" : " · not active"}</span></div>
        <div className="table-card"><table className="num">
          <caption className="sr-only">Results for {list[0].name} by channel</caption>
          <thead><tr>{["Channel", "Sent", "Replied", "Reply rate", "Asset sent", "Meetings", "Not interested"].map((t) => <th scope="col" key={t}>{t}</th>)}</tr></thead>
          <tbody>{list.map((r) => <tr key={r.channel} className={r.channel === "total" ? "total" : undefined}>
            <td>{r.channel === "total" ? "Total" : CHANNEL_LABEL[r.channel]}</td><td>{r.sent}</td><td>{r.replied}</td>
            <td>{r.sent ? `${r.reply_rate.toLocaleString("en", { maximumFractionDigits: 1 })} %` : "—"}</td>
            <td>{r.asset_sent}</td><td>{r.meetings}</td><td>{r.not_interested}</td></tr>)}</tbody>
        </table></div></section>;
    })}
  </main>;
}
