#!/usr/bin/env node
// JIRA skill — files BA specs, posts comments, refreshes release folders.
// Subcommands: file-spec, comment, refresh-specs, versions, search, get-field, update-field.

import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

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

async function jiraGet(path) {
  const r = await fetch(BASE + path, { headers });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

async function jiraPost(path, body) {
  const r = await fetch(BASE + path, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

async function jiraPut(path, body) {
  const r = await fetch(BASE + path, { method: 'PUT', headers, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`PUT ${path} failed: ${r.status} ${await r.text()}`);
  // PUT to /issue/{key} returns 204 No Content on success
  return r.status === 204 ? { ok: true } : await r.json();
}

// ===== ADF builders =====
const adf = {
  doc: (content) => ({ type: 'doc', version: 1, content }),
  para: (content) => ({ type: 'paragraph', content: Array.isArray(content) ? content : [content] }),
  text: (text, marks) => marks ? { type: 'text', text, marks } : { type: 'text', text },
  heading: (level, content) => ({ type: 'heading', attrs: { level }, content: Array.isArray(content) ? content : [content] }),
  bulletList: (items) => ({ type: 'bulletList', content: items.map(i => ({ type: 'listItem', content: [adf.para(i)] })) }),
  orderedList: (items) => ({ type: 'orderedList', content: items.map(i => ({ type: 'listItem', content: [adf.para(i)] })) }),
  blockquote: (content) => ({ type: 'blockquote', content: [adf.para(content)] }),
  codeBlock: (text, lang) => ({ type: 'codeBlock', attrs: lang ? { language: lang } : {}, content: text ? [adf.text(text)] : [] })
};

// ===== Inline markdown -> ADF text nodes =====
function parseInline(text) {
  if (!text) return [adf.text('')];
  const out = [];
  let cursor = 0;
  while (cursor < text.length) {
    const rest = text.slice(cursor);
    let m;
    // Code: `...`
    if ((m = rest.match(/^`([^`]+)`/))) {
      out.push(adf.text(m[1], [{ type: 'code' }]));
      cursor += m[0].length;
      continue;
    }
    // Link: [text](url)
    if ((m = rest.match(/^\[([^\]]+)\]\(([^)]+)\)/))) {
      out.push(adf.text(m[1], [{ type: 'link', attrs: { href: m[2] } }]));
      cursor += m[0].length;
      continue;
    }
    // Bold: **...**
    if ((m = rest.match(/^\*\*([^*]+)\*\*/))) {
      out.push(adf.text(m[1], [{ type: 'strong' }]));
      cursor += m[0].length;
      continue;
    }
    // Italic: *...* (single star)
    if ((m = rest.match(/^\*([^*\n]+)\*/))) {
      out.push(adf.text(m[1], [{ type: 'em' }]));
      cursor += m[0].length;
      continue;
    }
    // Plain text up to next inline marker
    const nextIdx = rest.slice(1).search(/[`\[*]/);
    const chunk = nextIdx === -1 ? rest : rest.slice(0, 1 + nextIdx);
    out.push(adf.text(chunk));
    cursor += chunk.length;
  }
  return out.length ? out : [adf.text(text)];
}

// ===== Block-level markdown -> ADF doc =====
function mdToAdf(markdown) {
  const lines = markdown.split('\n');
  const blocks = [];
  let i = 0;

  const isBlockStart = (l) => /^(#{1,6}\s|```|>|\s*[-*]\s|\s*\d+\.\s)/.test(l);

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    // Heading
    let m = line.match(/^(#{1,6})\s+(.+)$/);
    if (m) {
      blocks.push(adf.heading(m[1].length, parseInline(m[2])));
      i++;
      continue;
    }

    // Code block
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // consume closing fence
      blocks.push(adf.codeBlock(codeLines.join('\n'), lang));
      continue;
    }

    // Bullet list
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(parseInline(lines[i].replace(/^\s*[-*]\s+/, '')));
        i++;
      }
      blocks.push(adf.bulletList(items));
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(parseInline(lines[i].replace(/^\s*\d+\.\s+/, '')));
        i++;
      }
      blocks.push(adf.orderedList(items));
      continue;
    }

    // Blockquote (> ... over consecutive lines)
    if (line.startsWith('>')) {
      const quoteLines = [];
      while (i < lines.length && lines[i].startsWith('>')) {
        quoteLines.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      blocks.push(adf.blockquote(parseInline(quoteLines.join(' '))));
      continue;
    }

    // Paragraph: collect consecutive non-empty non-block lines
    const paraLines = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push(adf.para(parseInline(paraLines.join(' '))));
  }

  return adf.doc(blocks.length ? blocks : [adf.para([adf.text('')])]);
}

// ===== Frontmatter parsing (preserves key order) =====
function parseFrontmatter(content) {
  const m = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { frontmatter: {}, fmKeys: [], body: content };
  const [, yaml, body] = m;
  const fm = {};
  const keys = [];
  for (const line of yaml.split(/\r?\n/)) {
    const km = line.match(/^([\w_]+):\s*(.*)$/);
    if (km) {
      let val = km[2].trim();
      // Strip surrounding YAML single or double quotes so downstream consumers
      // (e.g. URL builders, JIRA payloads) get the raw value, not the quoted form.
      if (val.length >= 2 && ((val.startsWith("'") && val.endsWith("'")) || (val.startsWith('"') && val.endsWith('"')))) {
        val = val.slice(1, -1);
      }
      fm[km[1]] = val;
      keys.push(km[1]);
    }
  }
  return { frontmatter: fm, fmKeys: keys, body };
}

function serializeFrontmatter(fm, keys) {
  return '---\n' + keys.map(k => `${k}: ${fm[k]}`).join('\n') + '\n---';
}

function stripSpecBoilerplate(body) {
  let b = body.replace(/^\s+/, '');
  b = b.replace(/^#\s+[^\n]+\n+/, ''); // strip H1
  b = b.replace(/\n##\s+Suggested JIRA filing[\s\S]*$/, '\n'); // strip BA-only metadata section
  return b.trim();
}

// ===== Subcommand: versions =====
async function listVersions(args) {
  const [project] = args;
  if (!project) throw new Error('Usage: versions <project-key>');
  const versions = await jiraGet(`/rest/api/3/project/${project}/versions`);
  const filtered = versions
    .filter(v => !v.archived)
    .map(v => ({ name: v.name, released: v.released, releaseDate: v.releaseDate || null }));
  console.log(JSON.stringify({ project, count: filtered.length, versions: filtered }, null, 2));
}

// ===== ADF -> plain text walker (for drift-guard excerpts) =====
function adfToPlainText(node) {
  if (!node) return '';
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(adfToPlainText).join('');
  if (node.type === 'text') return node.text || '';
  if (node.type === 'hardBreak') return '\n';
  // Block-level nodes — separate with newlines
  const blockTypes = new Set(['paragraph', 'heading', 'codeBlock', 'blockquote', 'listItem', 'bulletList', 'orderedList']);
  const inner = node.content ? adfToPlainText(node.content) : '';
  return blockTypes.has(node.type) ? inner + '\n' : inner;
}

// ===== Subcommand: get-field =====
// Fetch a single field's plain-text value from a JIRA issue.
// Used by /intake-and-triage step 03 §E to populate `current_excerpt` in proposed_action: edit blocks.
async function getField(args) {
  const [issueKey, field, ...rest] = args;
  if (!issueKey || !field) throw new Error('Usage: get-field <issue-key> <field> [--max <chars>]');
  const maxIdx = rest.indexOf('--max');
  const max = maxIdx >= 0 ? parseInt(rest[maxIdx + 1], 10) : 300;

  const result = await jiraGet(`/rest/api/3/issue/${issueKey}?fields=${encodeURIComponent(field)}`);
  const raw = result.fields?.[field];
  if (raw === undefined || raw === null) {
    throw new Error(`Field "${field}" not present on ${issueKey} (or you don't have permission to read it).`);
  }

  // ADF object → plain text; primitives stringify directly
  let text;
  if (typeof raw === 'object' && raw.type === 'doc') {
    text = adfToPlainText(raw).replace(/\n{3,}/g, '\n\n').trim();
  } else if (typeof raw === 'string') {
    text = raw;
  } else if (Array.isArray(raw)) {
    text = raw.map(v => v?.name || v?.value || JSON.stringify(v)).join(', ');
  } else if (typeof raw === 'object') {
    text = raw.name || raw.value || JSON.stringify(raw);
  } else {
    text = String(raw);
  }

  const excerpt = text.length > max ? text.slice(0, max) : text;

  console.log(JSON.stringify({
    issueKey,
    field,
    fullLength: text.length,
    excerptLength: excerpt.length,
    excerpt
  }, null, 2));
}

// ===== Subcommand: update-field =====
// PATCH a single field on a JIRA issue with append / prepend / replace semantics.
// Used by /intake-and-triage step 0.5 to materialize `proposed_action: type: edit` blocks
// after the agent has run the placeholder + drift guards via get-field.
//
// Usage: update-field <issue-key> <field> --change-kind <append|prepend|replace>
//                     --value <text> | --value-file <path>
//
// For ADF fields (e.g. description) we re-read the current ADF doc and concatenate at the
// content-array level so existing formatting (headings, lists, marks) is preserved.
// For string fields we concatenate raw strings with a blank-line separator.
async function updateField(args) {
  const [issueKey, field, ...rest] = args;
  if (!issueKey || !field) {
    throw new Error('Usage: update-field <issue-key> <field> --change-kind <append|prepend|replace> --value <text>|--value-file <path>');
  }

  const kindIdx = rest.indexOf('--change-kind');
  if (kindIdx === -1) throw new Error('Missing --change-kind <append|prepend|replace>');
  const changeKind = rest[kindIdx + 1];
  if (!['append', 'prepend', 'replace'].includes(changeKind)) {
    throw new Error(`Invalid --change-kind "${changeKind}". Must be append, prepend, or replace.`);
  }

  let value;
  const valueIdx = rest.indexOf('--value');
  const fileIdx = rest.indexOf('--value-file');
  if (valueIdx !== -1) {
    value = rest[valueIdx + 1];
    if (value === undefined) throw new Error('Missing argument after --value');
  } else if (fileIdx !== -1) {
    const path = rest[fileIdx + 1];
    if (!path) throw new Error('Missing path after --value-file');
    value = await readFile(resolve(path), 'utf-8');
  } else {
    throw new Error('Provide either --value <text> or --value-file <path>');
  }

  // Probe current value to detect ADF vs string and (for non-replace kinds) merge correctly.
  const probe = await jiraGet(`/rest/api/3/issue/${issueKey}?fields=${encodeURIComponent(field)}`);
  const raw = probe.fields?.[field];
  const isAdf = raw && typeof raw === 'object' && raw.type === 'doc';

  let newValue;
  if (isAdf) {
    const incoming = mdToAdf(value);
    if (changeKind === 'replace') {
      newValue = incoming;
    } else if (changeKind === 'append') {
      newValue = { ...raw, content: [...(raw.content || []), ...incoming.content] };
    } else { // prepend
      newValue = { ...raw, content: [...incoming.content, ...(raw.content || [])] };
    }
  } else {
    const current = raw == null ? '' : (typeof raw === 'string' ? raw : String(raw));
    if (changeKind === 'replace') {
      newValue = value;
    } else if (changeKind === 'append') {
      newValue = current ? `${current}\n\n${value}` : value;
    } else { // prepend
      newValue = current ? `${value}\n\n${current}` : value;
    }
  }

  await jiraPut(`/rest/api/3/issue/${issueKey}`, { fields: { [field]: newValue } });

  console.log(JSON.stringify({
    ok: true,
    issueKey,
    field,
    changeKind,
    fieldShape: isAdf ? 'adf' : (raw == null ? 'empty' : typeof raw),
    bytesIn: value.length,
    url: `${BASE}/browse/${issueKey}`
  }, null, 2));
}

// ===== Subcommand: search =====
async function searchJql(args) {
  const jql = args.join(' ');
  if (!jql) throw new Error('Usage: search <jql>');
  const result = await jiraPost('/rest/api/3/search/jql', {
    jql,
    fields: ['summary', 'status', 'issuetype', 'fixVersions', 'assignee'],
    maxResults: 50
  });
  const issues = result.issues.map(i => ({
    key: i.key,
    type: i.fields.issuetype.name,
    status: i.fields.status.name,
    summary: i.fields.summary,
    fixVersions: i.fields.fixVersions.map(v => v.name),
    assignee: i.fields.assignee?.displayName || null
  }));
  console.log(JSON.stringify({ jql, count: issues.length, issues }, null, 2));
}

// ===== Subcommand: comment =====
async function comment(args) {
  const [issueKey, ...mdParts] = args;
  if (!issueKey || !mdParts.length) throw new Error('Usage: comment <issue-key> <markdown-text>');
  let md = mdParts.join(' ');
  if (md.startsWith('@')) {
    md = await readFile(md.slice(1), 'utf-8');
  }
  const body = mdToAdf(md);
  const result = await jiraPost(`/rest/api/3/issue/${issueKey}/comment`, { body });
  console.log(JSON.stringify({
    ok: true,
    issueKey,
    commentId: result.id,
    url: `${BASE}/browse/${issueKey}?focusedCommentId=${result.id}`
  }, null, 2));
}

// ===== Subcommand: file-spec =====
async function fileSpec(args) {
  const [specPath] = args;
  if (!specPath) throw new Error('Usage: file-spec <path>');
  const fullPath = resolve(specPath);
  const content = await readFile(fullPath, 'utf-8');
  const { frontmatter, fmKeys, body } = parseFrontmatter(content);

  // Validation per memory rules
  if (frontmatter.status !== 'approved') {
    throw new Error(`Spec status must be "approved" before filing. Current: "${frontmatter.status || '(none)'}". Get BA approval first; rule from memory feedback_spec_before_jira.md`);
  }
  if (!frontmatter.jira_fixversion) {
    throw new Error('Spec frontmatter missing jira_fixversion. Every JIRA ticket needs a fixVersion at creation; rule from memory feedback_jira_fixversion.md');
  }
  if (!frontmatter.jira_project) {
    throw new Error('Spec frontmatter missing jira_project (the Jira project key, e.g. APP).');
  }
  if (!frontmatter.title) {
    throw new Error('Spec frontmatter missing title (used as JIRA summary).');
  }

  const issuetype = frontmatter.jira_issuetype || 'Task';

  // Verify fixVersion exists and is not archived
  const versions = await jiraGet(`/rest/api/3/project/${frontmatter.jira_project}/versions`);
  const matched = versions.find(v => v.name === frontmatter.jira_fixversion && !v.archived);
  if (!matched) {
    throw new Error(`fixVersion "${frontmatter.jira_fixversion}" not found in project ${frontmatter.jira_project} (or is archived). Run "versions ${frontmatter.jira_project}" to see valid names.`);
  }

  // Build description from body
  const description = stripSpecBoilerplate(body);
  const adfDesc = mdToAdf(description);

  // POST to JIRA
  const created = await jiraPost('/rest/api/3/issue', {
    fields: {
      project: { key: frontmatter.jira_project },
      summary: frontmatter.title,
      issuetype: { name: issuetype },
      fixVersions: [{ name: frontmatter.jira_fixversion }],
      description: adfDesc
    }
  });

  // Update frontmatter
  const today = new Date().toISOString().slice(0, 10);
  const updates = {
    status: 'filed',
    jira_ticket: created.key,
    filed_at: today
  };
  if (!frontmatter.approved_at) updates.approved_at = today;

  const newFm = { ...frontmatter, ...updates };
  const newKeys = [...fmKeys];
  for (const k of Object.keys(updates)) {
    if (!newKeys.includes(k)) newKeys.push(k);
  }

  await writeFile(fullPath, serializeFrontmatter(newFm, newKeys) + '\n' + body);

  console.log(JSON.stringify({
    ok: true,
    issueKey: created.key,
    url: `${BASE}/browse/${created.key}`,
    project: frontmatter.jira_project,
    issuetype,
    fixVersion: frontmatter.jira_fixversion,
    spec: specPath
  }, null, 2));
}

// ===== Subcommand: refresh-specs =====
async function refreshSpecs(args) {
  const root = args[0] && !args[0].startsWith('--') ? resolve(args[0]) : process.cwd();
  const specsDir = join(root, 'docs/BA/specs');

  const slugify = (s) => s.toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  // --projects KEY=folder,KEY=folder — from the project profile (products[]). Required.
  const pi = args.indexOf('--projects');
  const projArg = pi >= 0 ? args[pi + 1] : '';
  const projects = projArg.split(',').map(p => p.split('=').map(x => x.trim())).filter(p => p[0] && p[1])
    .map(([key, folder]) => ({ key, folder, label: `${folder} (${key})` }));
  if (!projects.length) throw new Error('Pass --projects KEY=folder,… built from products[] in the project profile.');

  await mkdir(specsDir, { recursive: true });
  const summary = [];

  for (const proj of projects) {
    const versions = await jiraGet(`/rest/api/3/project/${proj.key}/versions`);
    const active = versions.filter(v => !v.archived && !v.released).sort((a, b) => a.name.localeCompare(b.name));
    const released = versions.filter(v => !v.archived && v.released).sort((a, b) => (b.releaseDate || '').localeCompare(a.releaseDate || ''));

    const projDir = join(specsDir, proj.folder);
    await mkdir(projDir, { recursive: true });
    const releasedDir = join(projDir, 'released');
    await mkdir(releasedDir, { recursive: true });
    if (!existsSync(join(releasedDir, '.gitkeep'))) {
      await writeFile(join(releasedDir, '.gitkeep'), '');
    }

    const idx = [];
    idx.push(`# ${proj.label} — Releases\n`);
    idx.push(`Folder per non-archived JIRA fixVersion in project \`${proj.key}\`. Active (unreleased) versions live at the top level of \`${proj.folder}/\`; once a version is shipped on JIRA, move its folder under \`${proj.folder}/released/\` to keep the active view clean. Specs land at \`{folder}/{spec-slug}.md\`.\n`);
    idx.push(`Last refreshed: ${new Date().toISOString().slice(0, 10)}\n`);

    idx.push(`## Unreleased — active (${active.length})\n`);
    idx.push('| Folder | Release name | Target date | JIRA filter |');
    idx.push('|---|---|---|---|');
    for (const v of active) {
      const slug = slugify(v.name);
      const subdir = join(projDir, slug);
      await mkdir(subdir, { recursive: true });
      if (!existsSync(join(subdir, '.gitkeep'))) await writeFile(join(subdir, '.gitkeep'), '');
      const url = `${BASE}/issues/?jql=${encodeURIComponent(`project = ${proj.key} AND fixVersion = "${v.name}"`)}`;
      idx.push(`| \`${slug}/\` | ${v.name} | ${v.releaseDate || '_unset_'} | [open](${url}) |`);
    }

    idx.push(`\n## Released — historical (${released.length})\n`);
    idx.push(`Folders live under \`${proj.folder}/released/\` so active releases stay uncluttered. Specs typically aren't added retroactively, but the folders are here for post-hoc decision/spec capture.\n`);
    idx.push('| Folder | Release name | Released | JIRA filter |');
    idx.push('|---|---|---|---|');
    for (const v of released) {
      const slug = slugify(v.name);
      const subdir = join(releasedDir, slug);
      await mkdir(subdir, { recursive: true });
      if (!existsSync(join(subdir, '.gitkeep'))) await writeFile(join(subdir, '.gitkeep'), '');
      const url = `${BASE}/issues/?jql=${encodeURIComponent(`project = ${proj.key} AND fixVersion = "${v.name}"`)}`;
      idx.push(`| \`released/${slug}/\` | ${v.name} | ${v.releaseDate || '_unknown_'} | [open](${url}) |`);
    }

    await writeFile(join(projDir, '_releases.md'), idx.join('\n') + '\n');
    summary.push({ project: proj.key, active: active.length, released: released.length });
  }

  console.log(JSON.stringify({ ok: true, refreshed: summary, root: specsDir }, null, 2));
}

// ===== Main dispatch =====
const COMMANDS = {
  // Retired 2026-09-24: it pasted the whole spec into the ticket and blanked lists in the spec header.
  // Tickets are filed by the ba-spec skill (step 9) as a short description + spec link.
  'file-spec': async () => { throw new Error('file-spec is retired — file tickets with the ba-spec skill (step 9).'); },
  'comment': comment,
  'refresh-specs': refreshSpecs,
  'versions': listVersions,
  'search': searchJql,
  'get-field': getField,
  'update-field': updateField
};

async function main() {
  const [cmd, ...args] = process.argv.slice(2);
  if (!cmd || !COMMANDS[cmd]) {
    console.error('Usage: jira <subcommand> [args]');
    console.error('Subcommands: ' + Object.keys(COMMANDS).join(', '));
    process.exit(1);
  }
  try {
    await COMMANDS[cmd](args);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

main();
