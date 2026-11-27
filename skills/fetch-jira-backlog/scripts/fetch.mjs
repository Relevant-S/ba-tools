#!/usr/bin/env node
// fetch-jira-backlog skill — pulls open JIRA tickets and writes template-shaped spec stubs
// at docs/BA/specs/{project}/{release_slug}/{slug}.md for the ba-spec skill to complete
//
// Subcommands:
//   list  [--jql <query>] [--limit N]
//   fetch <KEY>[,<KEY2>,...] [--refresh]
//
// Run from the project root (cwd is used to resolve docs/BA/specs/).

import { readFile, writeFile, mkdir, readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve, relative } from 'node:path';

const BASE = process.env.JIRA_BASE_URL;
const EMAIL = process.env.JIRA_EMAIL;
const TOKEN = process.env.JIRA_API_TOKEN;

if (!BASE || !EMAIL || !TOKEN) {
  console.error('JIRA env vars not set. Required: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.');
  console.error('Add to ~/.claude/settings.json env block, then start a new session.');
  process.exit(1);
}

const auth = 'Basic ' + Buffer.from(EMAIL + ':' + TOKEN).toString('base64');
const headers = { Authorization: auth, Accept: 'application/json', 'Content-Type': 'application/json' };

// --projects KEY=folder,KEY=folder — from the project profile (products[].jira_project → products[].key).
// For example --projects APP=app,PORTAL=portal, built from products[] in the project profile. Required.
const PROJ_ARG = (() => { const i = process.argv.indexOf('--projects'); return i >= 0 ? process.argv[i + 1] : ''; })();
const PROJECT_FOLDER = Object.fromEntries(PROJ_ARG.split(',').map(p => p.split('=').map(x => x.trim())).filter(p => p[0] && p[1]));
const DEFAULT_JQL = `project in (${Object.keys(PROJECT_FOLDER).join(', ')}) AND statusCategory != Done ORDER BY updated DESC`;
const DEFAULT_LIMIT = 50;
const TODAY = new Date().toISOString().slice(0, 10);


// ===== HTTP =====

async function jiraGet(path) {
  const r = await fetch(BASE + path, { headers });
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`GET ${path} failed: ${r.status} ${body}`);
  }
  return r.json();
}

async function jiraPost(path, body) {
  const r = await fetch(BASE + path, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`POST ${path} failed: ${r.status} ${text}`);
  }
  return r.json();
}

// ===== Slug + frontmatter helpers =====

function slugify(text) {
  return String(text)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')   // strip combining diacritics
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')       // non-alphanum → hyphen
    .replace(/^-+|-+$/g, '')           // trim
    .replace(/-{2,}/g, '-')            // collapse runs
    .slice(0, 80);                     // cap length
}

function parseFrontmatter(content) {
  const m = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { frontmatter: {}, body: content };
  const fm = {};
  const lines = m[1].split(/\r?\n/);
  for (const line of lines) {
    const kv = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$/);
    if (!kv) continue;
    let val = kv[2].trim();
    // strip surrounding quotes
    if ((val.startsWith("'") && val.endsWith("'")) || (val.startsWith('"') && val.endsWith('"'))) {
      val = val.slice(1, -1);
    }
    fm[kv[1]] = val;
  }
  return { frontmatter: fm, body: m[2] };
}

function quote(s) {
  // Single-quote and escape inner single-quotes per YAML 1.2
  if (s === undefined || s === null) return "''";
  return `'${String(s).replace(/'/g, "''")}'`;
}

// ===== ADF → Markdown rendering =====

function adfToMd(node, depth = 0) {
  if (!node) return '';
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(n => adfToMd(n, depth)).join('');

  const renderInline = (n) => {
    if (n.type !== 'text') return adfToMd(n, depth);
    let t = n.text || '';
    const marks = n.marks || [];
    let pre = '', post = '';
    for (const mk of marks) {
      switch (mk.type) {
        case 'strong': pre = '**' + pre; post = post + '**'; break;
        case 'em':     pre = '*' + pre;  post = post + '*'; break;
        case 'code':   pre = '`' + pre;  post = post + '`'; break;
        case 'strike': pre = '~~' + pre; post = post + '~~'; break;
        case 'link':   pre = '[' + pre;  post = post + `](${mk.attrs?.href || ''})`; break;
        // underline, textColor, etc — drop the mark, keep the text
      }
    }
    return pre + t + post;
  };

  const childrenInline = (n) => (n.content || []).map(renderInline).join('');
  const childrenBlocks = (n) => (n.content || []).map(c => adfToMd(c, depth)).join('');

  switch (node.type) {
    case 'doc':
      return childrenBlocks(node).replace(/\n{3,}/g, '\n\n').trim() + '\n';
    case 'paragraph':
      return childrenInline(node) + '\n\n';
    case 'heading': {
      const lvl = node.attrs?.level || 1;
      // Bump JIRA H1 to H4 inside our embedded section (we already have ### Description),
      // so seeded content doesn't disrupt the spec's section hierarchy.
      const renderedLvl = Math.min(6, lvl + 3);
      return '#'.repeat(renderedLvl) + ' ' + childrenInline(node) + '\n\n';
    }
    case 'bulletList':
      return (node.content || []).map(li => '- ' + adfToMd(li, depth + 1).trim().replace(/\n/g, '\n  ') + '\n').join('') + '\n';
    case 'orderedList':
      return (node.content || []).map((li, i) => `${i + 1}. ` + adfToMd(li, depth + 1).trim().replace(/\n/g, '\n  ') + '\n').join('') + '\n';
    case 'listItem':
      return childrenBlocks(node).trim();
    case 'blockquote':
      return childrenBlocks(node).trim().split('\n').map(l => '> ' + l).join('\n') + '\n\n';
    case 'codeBlock': {
      const lang = node.attrs?.language || '';
      const text = (node.content || []).map(t => t.text || '').join('');
      return '```' + lang + '\n' + text + '\n```\n\n';
    }
    case 'rule':
      return '\n---\n\n';
    case 'hardBreak':
      return '  \n';
    case 'mention':
      return `@${node.attrs?.text || node.attrs?.displayName || node.attrs?.id || ''}`;
    case 'inlineCard':
    case 'blockCard':
      return node.attrs?.url ? `[${node.attrs.url}](${node.attrs.url})\n\n` : '';
    case 'mediaSingle':
    case 'media':
    case 'mediaGroup':
      return '_(media omitted)_\n\n';
    case 'table':
      return renderTable(node) + '\n';
    case 'tableRow':
    case 'tableHeader':
    case 'tableCell':
      // handled by renderTable
      return childrenBlocks(node);
    case 'panel':
      return childrenBlocks(node);
    default:
      // Fallback: render children
      return childrenBlocks(node);
  }
}

function renderTable(table) {
  const rows = (table.content || []).filter(r => r.type === 'tableRow');
  if (!rows.length) return '';
  const cells = rows.map(row =>
    (row.content || []).map(cell =>
      (cell.content || []).map(c => adfToMd(c).trim()).join(' ').replace(/\|/g, '\\|').replace(/\n+/g, ' ')
    )
  );
  if (!cells.length || !cells[0].length) return '';
  const colCount = Math.max(...cells.map(r => r.length));
  const out = [];
  out.push('| ' + cells[0].map(c => c || ' ').join(' | ') + ' |');
  out.push('| ' + Array(colCount).fill('---').join(' | ') + ' |');
  for (let i = 1; i < cells.length; i++) {
    out.push('| ' + cells[i].map(c => c || ' ').join(' | ') + ' |');
  }
  return out.join('\n') + '\n';
}

// ===== _releases.md parser =====

async function loadReleasesMap(repoRoot, projectFolder) {
  const path = join(repoRoot, 'docs/BA/specs', projectFolder, '_releases.md');
  if (!existsSync(path)) return null;
  const content = await readFile(path, 'utf-8');
  // Match table rows of the form: | `<folder>/...` | <release name> | ... |
  // Folder slug may contain slashes (e.g. released/5-4-...), strip trailing slash.
  const rows = [];
  const rowRe = /^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|/gm;
  let m;
  while ((m = rowRe.exec(content)) !== null) {
    const folder = m[1].replace(/\/+$/, '');           // strip trailing slash
    const releaseName = m[2].trim();
    if (folder && releaseName && !folder.startsWith('http')) {
      rows.push({ folder, releaseName });
    }
  }
  // Index by release name (exact match, what JIRA fixVersion will be)
  const map = new Map();
  for (const r of rows) map.set(r.releaseName, r.folder);
  return map;
}

function resolveReleaseSlug(releasesMap, fixVersionName) {
  if (!fixVersionName) return { slug: '_unscheduled', warning: 'no fixVersion on ticket' };
  if (!releasesMap) return { slug: '_unscheduled', warning: '_releases.md not found' };
  const folder = releasesMap.get(fixVersionName);
  if (folder) return { slug: folder, warning: null };
  return { slug: '_unscheduled', warning: `fixVersion "${fixVersionName}" not in _releases.md (refresh it or move the spec manually)` };
}

// ===== Spec scan: find existing imports =====

async function* walkSpecs(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      yield* walkSpecs(p);
    } else if (e.isFile() && e.name.endsWith('.md') && !e.name.startsWith('_') && e.name !== 'README.md') {
      yield p;
    }
  }
}

async function scanExistingImports(repoRoot) {
  // Returns Map<jira_ticket, path>
  const root = join(repoRoot, 'docs/BA/specs');
  const map = new Map();
  if (!existsSync(root)) return map;
  for await (const path of walkSpecs(root)) {
    try {
      const content = await readFile(path, 'utf-8');
      const { frontmatter } = parseFrontmatter(content);
      if (frontmatter.jira_ticket) {
        map.set(frontmatter.jira_ticket, path);
      }
    } catch {
      // skip unreadable
    }
  }
  return map;
}

// ===== Subcommand: list =====

async function cmdList(args) {
  const jqlIdx = args.indexOf('--jql');
  const jql = jqlIdx >= 0 ? args[jqlIdx + 1] : DEFAULT_JQL;
  const limitIdx = args.indexOf('--limit');
  const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : DEFAULT_LIMIT;

  const result = await jiraPost('/rest/api/3/search/jql', {
    jql,
    fields: ['summary', 'status', 'issuetype', 'fixVersions', 'project', 'assignee'],
    maxResults: limit
  });

  const repoRoot = process.cwd();
  const existing = await scanExistingImports(repoRoot);

  const tickets = result.issues.map(i => {
    const projKey = i.fields.project?.key || '';
    const projFolder = PROJECT_FOLDER[projKey] || projKey.toLowerCase();
    const fixVersion = i.fields.fixVersions[0]?.name || '';
    const summary = i.fields.summary || '';
    const slug = slugify(summary) || `untitled-${i.key.toLowerCase()}`;
    const alreadyImportedAt = existing.get(i.key) || null;
    return {
      key: i.key,
      project: projKey,
      summary,
      slug,
      status: i.fields.status?.name || '',
      issuetype: i.fields.issuetype?.name || '',
      fixVersions: i.fields.fixVersions.map(v => v.name),
      assignee: i.fields.assignee?.displayName || null,
      alreadyImported: !!alreadyImportedAt,
      alreadyImportedAt: alreadyImportedAt ? relative(repoRoot, alreadyImportedAt).replace(/\\/g, '/') : null
    };
  });

  console.log(JSON.stringify({ jql, count: tickets.length, tickets }, null, 2));
}

// ===== Subcommand: fetch =====

async function fetchOne(key, opts) {
  const { repoRoot, refresh, existing, releasesMaps } = opts;

  // 1. GET ticket
  const issue = await jiraGet(`/rest/api/3/issue/${key}?fields=summary,description,status,issuetype,fixVersions,project,assignee,priority`);
  const projKey = issue.fields.project?.key || '';
  const projFolder = PROJECT_FOLDER[projKey];
  if (!projFolder) {
    return { key, action: 'error', message: `Unknown project "${projKey}" (expected one of ${Object.keys(PROJECT_FOLDER).join(', ')} — pass --projects)` };
  }

  const summary = issue.fields.summary || '(no summary)';
  const status = issue.fields.status?.name || '';
  const issuetype = issue.fields.issuetype?.name || 'Task';
  const fixVersion = issue.fields.fixVersions?.[0]?.name || '';
  const assignee = issue.fields.assignee?.displayName || '';
  const slug = slugify(summary) || `untitled-${key.toLowerCase()}`;

  // 2. Resolve release slug
  const releasesMap = releasesMaps[projFolder] ?? await loadReleasesMap(repoRoot, projFolder);
  releasesMaps[projFolder] = releasesMap;
  const { slug: releaseSlug, warning: releaseWarning } = resolveReleaseSlug(releasesMap, fixVersion);

  // 3. Idempotency: did we already import this KEY?
  const existingPath = existing.get(key);

  // 4. Compute target path (used either for fresh-write or collision check)
  const targetPath = join(repoRoot, 'docs/BA/specs', projFolder, releaseSlug, `${slug}.md`);
  const relTarget = relative(repoRoot, targetPath).replace(/\\/g, '/');

  // 5. Render seeded content
  const seededSection = renderJiraSourceSection({
    key, status, issuetype, fixVersions: issue.fields.fixVersions || [], assignee,
    description: issue.fields.description, fetchedAt: TODAY
  });

  // === Path A: refresh existing import ===
  if (existingPath) {
    const relExisting = relative(repoRoot, existingPath).replace(/\\/g, '/');
    if (!refresh) {
      return { key, action: 'skipped-already-imported', path: relExisting };
    }
    const content = await readFile(existingPath, 'utf-8');
    const { frontmatter } = parseFrontmatter(content);
    // Refreshable = an untouched import: the legacy 'draft-from-jira' status, or a template-shaped
    // stub still at 'draft' with source 'jira-import'. Anything further along belongs to ba-spec.
    const refreshable = frontmatter.status === 'draft-from-jira'
      || (frontmatter.status === 'draft' && frontmatter.source === 'jira-import');
    if (!refreshable) {
      return { key, action: 'skipped-not-refreshable', path: relExisting, message: `status is "${frontmatter.status}" — refresh only operates on untouched imports (status draft + source jira-import)` };
    }
    // Update frontmatter, then replace the JIRA Source section in body
    const fmUpdated = rewriteFrontmatter(content, { fetched_at: TODAY, jira_status: status }) ?? content;
    const fmMatch = fmUpdated.match(/^(---\r?\n[\s\S]*?\r?\n---\r?\n?)([\s\S]*)$/);
    const fmPart = fmMatch ? fmMatch[1] : '';
    const bodyPart = fmMatch ? fmMatch[2] : fmUpdated;
    const newBody = replaceJiraSourceSection(bodyPart, seededSection);
    await writeFile(existingPath, fmPart + newBody, 'utf-8');
    return { key, action: 'refreshed', path: relExisting };
  }

  // === Path B: collision check before fresh write ===
  if (existsSync(targetPath)) {
    // File exists at target path but no jira_ticket match in scan → either has a different
    // jira_ticket, or no jira_ticket at all → collision.
    const content = await readFile(targetPath, 'utf-8');
    const { frontmatter } = parseFrontmatter(content);
    return {
      key,
      action: 'collision',
      path: relTarget,
      message: frontmatter.jira_ticket
        ? `target path occupied by spec for ${frontmatter.jira_ticket}`
        : 'target path occupied by spec without jira_ticket frontmatter'
    };
  }

  // === Path C: fresh write ===
  await mkdir(join(targetPath, '..'), { recursive: true });
  // Header follows the approved spec template (docs/BA/specs/_template.md). Fields the import
  // cannot know stay blank for ba-spec step 1 to set (id, size, covers).
  const RAW = v => ({ raw: v });
  const fm = renderFrontmatter({
    id: '-',
    product: PROJECT_FOLDER[projKey],
    title: summary,
    status: 'draft',
    status_reason: '',
    size: '',
    owner: '',
    decider: '',
    opened: TODAY,
    needed_by: '-',
    last_touched: TODAY,
    downstream: RAW('[prd:next]'),
    covers: RAW('[]'),
    depends_on: RAW('[]'),
    jira_project: projKey,
    jira_issuetype: issuetype,
    jira_fixversion: fixVersion,
    jira_priority: issue.fields.priority?.name || '',
    jira_ticket: key,
    jira_status: status,
    source_intake: '',
    triage_ref: '',
    handoff_branch: '-',
    accepted_risks: RAW('[]'),
    source: 'jira-import',
    fetched_at: TODAY
  });
  const content = `${fm}\n# ${summary}\n\n${seededSection}\n<!-- Imported from JIRA. Run the ba-spec skill on this file (re-create path: the ticket already exists) to write it in the approved template, pass the ready gate and update the ticket. -->\n`;
  await writeFile(targetPath, content, 'utf-8');

  return {
    key,
    action: 'written',
    path: relTarget,
    ...(releaseWarning ? { warning: releaseWarning } : {})
  };
}

function renderFrontmatter(fields) {
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    lines.push(`${k}: ${v && typeof v === 'object' && 'raw' in v ? v.raw : quote(v)}`);
  }
  lines.push('---');
  return lines.join('\n');
}

function renderJiraSourceSection({ key, status, issuetype, fixVersions, assignee, description, fetchedAt }) {
  const fvText = fixVersions?.length ? fixVersions.map(v => v.name).join(', ') : '(none)';
  const assigneeText = assignee || '(unassigned)';
  const browseUrl = `${BASE.replace(/\/$/, '')}/browse/${key}`;
  const descMd = description ? adfToMd(description).trim() : '_(empty)_';
  return [
    '## JIRA Source',
    '',
    `> Imported from JIRA ticket [${key}](${browseUrl}) on ${fetchedAt}.`,
    `> The \`ba-spec\` skill reads this section as raw input when it writes the spec in the approved template.`,
    `> When the spec is written, this section is removed and the ticket description is replaced by the short form (summary + spec link).`,
    '',
    `**Status:** ${status}`,
    `**Issue type:** ${issuetype}`,
    `**Fix Version:** ${fvText}`,
    `**Assignee:** ${assigneeText}`,
    '',
    '### Description',
    '',
    descMd,
    ''
  ].join('\n');
}

function replaceJiraSourceSection(body, newSection) {
  // Split body at H2 boundaries, swap the JIRA Source section, rejoin.
  const sections = body.split(/(?=^## )/m);
  let replaced = false;
  const out = sections.map(s => {
    if (/^##\s+JIRA\s+Source\b/i.test(s)) {
      replaced = true;
      // Ensure exactly one trailing newline before the next section
      return newSection.replace(/\n*$/, '\n');
    }
    return s;
  });
  if (replaced) return out.join('');
  return body.trimEnd() + '\n\n' + newSection;
}

function rewriteFrontmatter(content, updates) {
  const m = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!m) return null;
  let block = m[1];
  for (const [k, v] of Object.entries(updates)) {
    const re = new RegExp(`^${k}\\s*:.*$`, 'm');
    if (re.test(block)) {
      block = block.replace(re, `${k}: ${quote(v)}`);
    } else {
      block += `\n${k}: ${quote(v)}`;
    }
  }
  return content.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, `---\n${block}\n---\n`);
}

async function cmdFetch(args) {
  const refresh = args.includes('--refresh');
  const positional = args.filter(a => !a.startsWith('--'));
  if (!positional.length) {
    throw new Error('Usage: fetch <KEY>[,<KEY2>,...] [--refresh]');
  }
  const keys = positional.flatMap(p => p.split(',')).map(s => s.trim()).filter(Boolean);

  const repoRoot = process.cwd();
  const existing = await scanExistingImports(repoRoot);
  const releasesMaps = {}; // cache per project folder

  const results = [];
  for (const key of keys) {
    try {
      const r = await fetchOne(key, { repoRoot, refresh, existing, releasesMaps });
      // Update existing map so a duplicate key in the same call short-circuits
      if (r.action === 'written' || r.action === 'refreshed') {
        existing.set(key, join(repoRoot, r.path));
      }
      results.push(r);
    } catch (e) {
      results.push({ key, action: 'error', message: e.message });
    }
  }

  const summary = {
    total: results.length,
    written: results.filter(r => r.action === 'written').length,
    refreshed: results.filter(r => r.action === 'refreshed').length,
    skippedAlreadyImported: results.filter(r => r.action === 'skipped-already-imported').length,
    collisions: results.filter(r => r.action === 'collision').length,
    errors: results.filter(r => r.action === 'error').length,
    warnings: results.filter(r => r.warning).length
  };

  console.log(JSON.stringify({ summary, results }, null, 2));
}

// ===== Dispatcher =====

const SUBCOMMANDS = { list: cmdList, fetch: cmdFetch };

const [, , sub, ...rest] = process.argv;
if (!sub || !SUBCOMMANDS[sub]) {
  console.error('Usage: fetch.mjs <subcommand> [args]');
  console.error('Subcommands: list, fetch');
  process.exit(1);
}
if (!Object.keys(PROJECT_FOLDER).length) {
  console.error('Pass --projects KEY=folder,… built from products[] in the project profile.');
  process.exit(1);
}
try {
  await SUBCOMMANDS[sub](rest);
} catch (e) {
  console.error(`Error in ${sub}: ${e.message}`);
  process.exit(1);
}
