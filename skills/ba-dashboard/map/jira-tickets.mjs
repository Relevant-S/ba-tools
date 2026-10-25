// Read-only: status, area (component), parent and finish date of every ticket the dashboard mentions.
// Usage: node jira-tickets.mjs <refs.json> <out.json>   (build.py --refresh writes refs.json)
import { readFile, writeFile } from 'node:fs/promises';
const { JIRA_BASE_URL: BASE, JIRA_EMAIL: EMAIL, JIRA_API_TOKEN: TOKEN } = process.env;
const headers = { Authorization: 'Basic ' + Buffer.from(EMAIL + ':' + TOKEN).toString('base64'), Accept: 'application/json', 'Content-Type': 'application/json' };
const refs = JSON.parse(await readFile(process.argv[2], 'utf-8'));
const keys = Object.keys(refs), out = {};
for (let i = 0; i < keys.length; i += 80) {
  const r = await fetch(BASE + '/rest/api/3/search/jql', { method: 'POST', headers, body: JSON.stringify({ jql: `key in (${keys.slice(i, i + 80).join(',')})`, fields: ['parent', 'status', 'summary', 'resolutiondate', 'components'], maxResults: 100 }) });
  const j = await r.json();
  if (!r.ok) { console.error(JSON.stringify(j)); process.exit(1); }
  for (const x of j.issues) out[x.key] = { parent: x.fields.parent?.key ?? null, parentName: x.fields.parent?.fields?.summary ?? null, status: x.fields.status.name, category: x.fields.status.statusCategory.key, resolved: x.fields.resolutiondate?.slice(0, 10) ?? null, components: x.fields.components.map(c => c.name), summary: x.fields.summary, by: refs[x.key] };
}
await writeFile(process.argv[3], JSON.stringify(out, null, 1));
console.log(Object.keys(out).length);
