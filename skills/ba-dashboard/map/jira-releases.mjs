// Read-only: every release (Jira fixVersion) in the given Jira projects, and the tickets the board shows —
// every ticket in a release, plus every open ticket with no release.
// Usage: node jira-releases.mjs <out.json> <PROJ1,PROJ2>
import { writeFile } from 'node:fs/promises';
const { JIRA_BASE_URL: BASE, JIRA_EMAIL: EMAIL, JIRA_API_TOKEN: TOKEN } = process.env;
const headers = { Authorization: 'Basic ' + Buffer.from(EMAIL + ':' + TOKEN).toString('base64'), Accept: 'application/json', 'Content-Type': 'application/json' };
const get = async p => (await fetch(BASE + p, { headers })).json();
const post = async (p, b) => { const r = await fetch(BASE + p, { method: 'POST', headers, body: JSON.stringify(b) }); if (!r.ok) throw new Error(await r.text()); return r.json(); };
async function all(jql, fields) {
  const out = []; let nextPageToken;
  do { const r = await post('/rest/api/3/search/jql', { jql, fields, maxResults: 100, nextPageToken }); out.push(...r.issues); nextPageToken = r.nextPageToken; } while (nextPageToken);
  return out;
}
const FIELDS = ['summary', 'status', 'components', 'fixVersions', 'parent', 'resolutiondate', 'assignee', 'issuetype'];
const out = { releases: [], tickets: {} };
for (const project of (process.argv[3] || '').split(',').filter(Boolean)) {
  for (const v of await get(`/rest/api/3/project/${project}/versions`)) {
    if (v.archived) continue;
    out.releases.push({ project, id: v.id, name: v.name, released: v.released, date: v.releaseDate ?? null, start: v.startDate ?? null });
  }
  const q = `project = ${project} AND issuetype != Epic AND issuetype not in subTaskIssueTypes()`;
  const issues = [
    ...await all(`${q} AND fixVersion is not EMPTY`, FIELDS),
    ...await all(`${q} AND fixVersion is EMPTY AND statusCategory != Done`, FIELDS),
  ];
  for (const x of issues) {
    const f = x.fields;
    out.tickets[x.key] = {
      summary: f.summary, status: f.status.name, category: f.status.statusCategory.key,
      components: f.components.map(c => c.name), releases: f.fixVersions.map(v => v.name),
      parent: f.parent?.key ?? null, parentName: f.parent?.fields?.summary ?? null,
      resolved: f.resolutiondate?.slice(0, 10) ?? null, assignee: f.assignee?.displayName ?? null,
    };
  }
}
await writeFile(process.argv[2], JSON.stringify(out, null, 1));
console.log('releases', out.releases.length, 'tickets', Object.keys(out.tickets).length);
