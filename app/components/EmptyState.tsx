export function EmptyState() {
  return <section className="panel" aria-label="No leads yet">
    <h1>No leads yet</h1>
    <p>The table fills from a scrape. Pick one niche in one country and run the pipeline once; a small probe takes a few minutes and costs well under a dollar.</p>
    <pre><code>python run.py --country GB --niche roofer --region "West Yorkshire" --cells 20</code></pre>
    <p>When the run finishes, reload this page. New businesses appear with their Instagram and Facebook profiles.</p>
    <p className="muted">First time here? Open this repo in Claude Code and say &ldquo;set up&rdquo;, or follow the setup steps in the README. Settings live in <code>outreach.config.json</code>.</p>
  </section>;
}
