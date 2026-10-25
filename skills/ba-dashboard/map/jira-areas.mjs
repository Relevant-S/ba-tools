// Read-only: every component (area) in the given Jira projects with its ticket activity.
// Usage: node jira-areas.mjs <out.json> <PROJ1,PROJ2>   (the projects come from the profile's products)
import { writeFile } from 'node:fs/promises';
const { JIRA_BASE_URL: BASE, JIRA_EMAIL: EMAIL, JIRA_API_TOKEN: TOKEN } = process.env;
const headers = { Authorization: 'Basic ' + Buffer.from(EMAIL + ':' + TOKEN).toString('base64'), Accept: 'application/json', 'Content-Type': 'application/json' };
const get = async p => (await fetch(BASE + p, { headers })).json();
const post = async (p, b) => { const r = await fetch(BASE + p, { method: 'POST', headers, body: JSON.stringify(b) }); if (!r.ok) throw new Error(await r.text()); return r.json(); };
const count = async jql => (await post('/rest/api/3/search/approximate-count', { jql })).count;
async function all(jql, fields) {
  const out = []; let nextPageToken;
  do { const r = await post('/rest/api/3/search/jql', { jql, fields, maxResults: 100, nextPageToken }); out.push(...r.issues); nextPageToken = r.nextPageToken; } while (nextPageToken);
  return out;
}
const rows = [];
for (const project of (process.argv[3] || '').split(',').filter(Boolean)) {
  for (const c of await get(`/rest/api/3/project/${project}/components`)) {
    const q = `project = ${project} AND component = ${c.id} AND issuetype != Epic`;
    const [done, recent, openIssues, last, shipped] = await Promise.all([
      count(`${q} AND statusCategory = Done`),
      count(`${q} AND updated >= -30d`),
      all(`${q} AND statusCategory != Done`, ['status']),
      post('/rest/api/3/search/jql', { jql: `${q} ORDER BY updated DESC`, fields: ['updated'], maxResults: 1 }),
      post('/rest/api/3/search/jql', { jql: `${q} AND statusCategory = Done ORDER BY resolved DESC`, fields: ['summary', 'resolutiondate'], maxResults: 5 }),
    ]);
    rows.push({
      project, id: c.id, name: c.name, description: c.description || '', done, recent,
      open: openIssues.map(i => ({ status: i.fields.status.name, category: i.fields.status.statusCategory.key })),
      lastUpdated: last.issues[0]?.fields.updated.slice(0, 10) ?? null,
      lastDone: shipped.issues[0]?.fields.resolutiondate?.slice(0, 10) ?? null,
      shipped: shipped.issues.map(x => ({ key: x.key, summary: x.fields.summary, date: x.fields.resolutiondate?.slice(0, 10) ?? null })),
      search: `${BASE}/issues/?jql=${encodeURIComponent(`project = ${project} AND component = "${c.name}" ORDER BY updated DESC`)}`,
    });
  }
}
await writeFile(process.argv[2], JSON.stringify(rows, null, 1));
console.log('areas', rows.length);
