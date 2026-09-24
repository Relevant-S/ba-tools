#!/usr/bin/env node
// fetch-gmail skill — pulls labeled Gmail threads as intake files.
//
// Subcommands:
//   init-auth                              OAuth2 consent flow → ~/.claude/skills/fetch-gmail/state/token.json
//   init-project [--reinit]                Per-project setup: tracked senders + window + Gmail label
//   list [--window <dur>] [--include-imported]
//   fetch <thread-id>[,<id>...] [--refresh]
//   unlabel <thread-id>[,<id>...]
//   config-show
//
// Plain fetch, no npm deps. Run from project root for non-init-auth subcommands
// (cwd is used to resolve docs/BA/intake/, docs/BA/.fetch-gmail-config.yaml, _bmad/*/config.yaml).

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// The sign-in is personal: it lives in ~/.claude/ba-tools/state/, never inside a skill folder that a
// project repo commits. The old location inside the skill is still read if it exists.
const STATE_DIR = join(homedir(), '.claude', 'ba-tools', 'state');
const OLD_TOKEN_PATH = [join(__dirname, '..', 'state', 'token.json'),
  join(homedir(), '.claude', 'skills', 'fetch-gmail', 'state', 'token.json')].find(p => existsSync(p)) || '';
const TOKEN_PATH = existsSync(join(STATE_DIR, 'gmail-token.json')) || !OLD_TOKEN_PATH
  ? join(STATE_DIR, 'gmail-token.json') : OLD_TOKEN_PATH;

const CLIENT_ID = process.env.GMAIL_OAUTH_CLIENT_ID;
const CLIENT_SECRET = process.env.GMAIL_OAUTH_CLIENT_SECRET;
const SCOPE = 'https://www.googleapis.com/auth/gmail.modify';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const GMAIL_BASE = 'https://gmail.googleapis.com/gmail/v1/users/me';

const TODAY = new Date().toISOString().slice(0, 10);

// ===== utils =====

function log(msg) { console.error(msg); } // human-readable to stderr; JSON results to stdout

function abort(msg, code = 1) {
  log(`Error: ${msg}`);
  if (typeof closeReadline === 'function') closeReadline();
  process.exit(code);
}

async function ensureDir(d) { await mkdir(d, { recursive: true }); }

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf-8'));
}

async function writeJson(path, obj) {
  await ensureDir(dirname(path));
  await writeFile(path, JSON.stringify(obj, null, 2), 'utf-8');
}

let _rl = null;
let _stdinQueue = null; // populated when stdin is non-TTY: array of pre-read lines
let _stdinQueueLoaded = false;

async function loadStdinQueueIfPiped() {
  if (_stdinQueueLoaded) return;
  _stdinQueueLoaded = true;
  if (input.isTTY) return; // interactive — use readline
  // Non-TTY: read all stdin upfront, split into lines
  const chunks = [];
  for await (const chunk of input) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString('utf-8');
  _stdinQueue = text.split(/\r?\n/);
  // Drop trailing empty string from final newline
  if (_stdinQueue.length && _stdinQueue[_stdinQueue.length - 1] === '') _stdinQueue.pop();
}

function getReadline() {
  if (!_rl) _rl = createInterface({ input, output });
  return _rl;
}
function closeReadline() {
  if (_rl) { _rl.close(); _rl = null; }
}
async function ask(question) {
  await loadStdinQueueIfPiped();
  if (_stdinQueue) {
    // Echo prompt to stderr so logs show what was asked, return queued answer
    process.stderr.write(question);
    const answer = _stdinQueue.shift() ?? '';
    process.stderr.write(answer + '\n');
    return answer.trim();
  }
  const answer = await getReadline().question(question);
  return answer.trim();
}

// Minimal YAML for our flat config (key: scalar, key: [list], key: 'string'). Not a general parser.
function yamlStringify(obj) {
  const lines = [];
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) {
      lines.push(`${k}:`);
      for (const item of v) lines.push(`  - ${quoteScalar(item)}`);
    } else {
      lines.push(`${k}: ${quoteScalar(v)}`);
    }
  }
  return lines.join('\n') + '\n';
}

function quoteScalar(v) {
  if (v === null || v === undefined) return "''";
  const s = String(v);
  if (/^[A-Za-z0-9_./@:-]+$/.test(s) && !/^\d/.test(s)) return s; // bareword OK if non-numeric-leading
  return `'${s.replace(/'/g, "''")}'`;
}

function yamlParse(text) {
  // Flat parser: key: scalar | key: \n  - item lines.
  const out = {};
  const lines = text.split(/\r?\n/);
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line || /^\s*#/.test(line)) { i++; continue; }
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$/);
    if (!m) { i++; continue; }
    const key = m[1];
    const rest = m[2].trim();
    if (rest === '') {
      // List or block
      const items = [];
      let j = i + 1;
      while (j < lines.length && /^\s+-\s+/.test(lines[j])) {
        items.push(unquoteScalar(lines[j].replace(/^\s+-\s+/, '').trim()));
        j++;
      }
      out[key] = items;
      i = j;
    } else {
      out[key] = unquoteScalar(rest);
      i++;
    }
  }
  return out;
}

function unquoteScalar(s) {
  if ((s.startsWith("'") && s.endsWith("'")) || (s.startsWith('"') && s.endsWith('"'))) {
    return s.slice(1, -1).replace(/''/g, "'");
  }
  return s;
}

// ===== OAuth helpers =====

let _accessTokenCache = { token: null, expiresAt: 0 };

async function getAccessToken() {
  if (_accessTokenCache.token && Date.now() < _accessTokenCache.expiresAt - 60000) {
    return _accessTokenCache.token;
  }
  if (!CLIENT_ID || !CLIENT_SECRET) {
    abort('GMAIL_OAUTH_CLIENT_ID / GMAIL_OAUTH_CLIENT_SECRET not set. Add to ~/.claude/settings.json env block, restart session.');
  }
  if (!existsSync(TOKEN_PATH)) {
    abort(`Refresh token not found at ${TOKEN_PATH}. Run: node fetch.mjs init-auth`);
  }
  const { refresh_token } = await readJson(TOKEN_PATH);
  const r = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: CLIENT_ID, client_secret: CLIENT_SECRET,
      refresh_token, grant_type: 'refresh_token'
    })
  });
  if (!r.ok) abort(`Gmail token refresh failed: ${r.status} ${await r.text()}. Re-run init-auth if invalid_grant.`);
  const data = await r.json();
  _accessTokenCache = {
    token: data.access_token,
    expiresAt: Date.now() + (data.expires_in || 3600) * 1000
  };
  return data.access_token;
}

async function gmailGet(path) {
  const token = await getAccessToken();
  const r = await fetch(GMAIL_BASE + path, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

async function gmailPost(path, body) {
  const token = await getAccessToken();
  const r = await fetch(GMAIL_BASE + path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status} ${await r.text()}`);
  return r.json();
}

// ===== init-auth: loopback OAuth flow =====

async function cmdInitAuth() {
  if (!CLIENT_ID || !CLIENT_SECRET) {
    abort('GMAIL_OAUTH_CLIENT_ID / GMAIL_OAUTH_CLIENT_SECRET not set in env. See SKILL.md "One-time Google Cloud setup".');
  }

  const state = Math.random().toString(36).slice(2);
  let resolveCode, rejectCode;
  const codePromise = new Promise((res, rej) => { resolveCode = res; rejectCode = rej; });

  const server = createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const code = url.searchParams.get('code');
    const err = url.searchParams.get('error');
    const recvState = url.searchParams.get('state');
    if (err) {
      res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`<h1>Auth failed</h1><pre>${err}</pre>You can close this tab.`);
      rejectCode(new Error(`OAuth error: ${err}`));
      return;
    }
    if (recvState !== state) {
      res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('State mismatch — possible CSRF. Close this tab and try again.');
      rejectCode(new Error('OAuth state mismatch'));
      return;
    }
    if (code) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end('<h1>fetch-gmail authorized.</h1><p>You can close this tab and return to your terminal.</p>');
      resolveCode(code);
    } else {
      res.writeHead(400);
      res.end('Missing code.');
      rejectCode(new Error('No code in callback'));
    }
  });

  await new Promise(res => server.listen(0, '127.0.0.1', res));
  const { port } = server.address();
  const redirectUri = `http://127.0.0.1:${port}/`;

  const authUrl = `${AUTH_URL}?` + new URLSearchParams({
    client_id: CLIENT_ID,
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: SCOPE,
    access_type: 'offline',
    prompt: 'consent',
    state
  }).toString();

  log('');
  log('=== fetch-gmail OAuth setup ===');
  log('');
  log('Open this URL in your browser, sign in, and approve the consent screen:');
  log('');
  log(authUrl);
  log('');
  log('After approval, your browser will redirect to a localhost page — that\'s the loopback callback.');
  log('Waiting for redirect...');

  let code;
  try {
    code = await codePromise;
  } finally {
    server.close();
  }

  log('Received auth code; exchanging for refresh token...');

  const r = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      redirect_uri: redirectUri,
      grant_type: 'authorization_code'
    })
  });
  if (!r.ok) abort(`Token exchange failed: ${r.status} ${await r.text()}`);
  const data = await r.json();

  if (!data.refresh_token) {
    abort('No refresh_token returned. Revoke prior consent at myaccount.google.com/permissions and re-run init-auth.');
  }

  await ensureDir(STATE_DIR);
  await writeJson(TOKEN_PATH, { refresh_token: data.refresh_token, scope: data.scope, created: TODAY });
  log(`Saved refresh token to ${TOKEN_PATH}.`);
  console.log(JSON.stringify({ ok: true, tokenPath: TOKEN_PATH }, null, 2));
}

// ===== Project config =====

const PROJECT_CONFIG_PATH = 'docs/BA/.fetch-gmail-config.yaml';

async function readProjectConfig() {
  const cwd = process.cwd();
  const p = join(cwd, PROJECT_CONFIG_PATH);
  if (!existsSync(p)) return null;
  return yamlParse(await readFile(p, 'utf-8'));
}

async function writeProjectConfig(cfg) {
  const cwd = process.cwd();
  const p = join(cwd, PROJECT_CONFIG_PATH);
  await ensureDir(dirname(p));
  await writeFile(p, yamlStringify(cfg), 'utf-8');
  return p;
}

async function readProjectSlugFromBmad() {
  // Glob _bmad/*/config.yaml for project_slug:
  const cwd = process.cwd();
  const bmadRoot = join(cwd, '_bmad');
  if (!existsSync(bmadRoot)) return null;
  const modules = await readdir(bmadRoot, { withFileTypes: true });
  const matches = [];
  for (const m of modules) {
    if (!m.isDirectory()) continue;
    const cfgPath = join(bmadRoot, m.name, 'config.yaml');
    if (!existsSync(cfgPath)) continue;
    try {
      const parsed = yamlParse(await readFile(cfgPath, 'utf-8'));
      if (parsed.project_slug) matches.push({ module: m.name, slug: parsed.project_slug, path: cfgPath });
    } catch { /* skip */ }
  }
  if (matches.length === 0) return null;
  if (matches.length > 1) {
    log(`Multiple BMAD modules with project_slug found:`);
    for (const m of matches) log(`  - ${m.module}: ${m.slug} (${m.path})`);
    log(`Using first: ${matches[0].module}/${matches[0].slug}`);
  }
  return matches[0].slug;
}

// ===== Label helpers =====

async function findOrCreateLabel(labelName) {
  const labels = await gmailGet('/labels');
  const existing = labels.labels.find(l => l.name === labelName);
  if (existing) return existing.id;
  const created = await gmailPost('/labels', {
    name: labelName,
    labelListVisibility: 'labelShow',
    messageListVisibility: 'show'
  });
  return created.id;
}

// ===== Gmail thread helpers =====

async function listThreads({ query, maxResults = 50, pageToken = null }) {
  const params = new URLSearchParams({ q: query, maxResults: String(maxResults) });
  if (pageToken) params.set('pageToken', pageToken);
  return gmailGet(`/threads?${params.toString()}`);
}

async function getThreadMetadata(threadId) {
  return gmailGet(`/threads/${threadId}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Cc&metadataHeaders=Date`);
}

async function getThreadFull(threadId) {
  return gmailGet(`/threads/${threadId}?format=full`);
}

function getHeader(message, name) {
  const h = (message.payload?.headers || []).find(h => h.name.toLowerCase() === name.toLowerCase());
  return h ? h.value : '';
}

function parseEmailAddrList(value) {
  if (!value) return [];
  return value.split(',').map(s => {
    const m = s.match(/<([^>]+)>/);
    return (m ? m[1] : s).trim();
  }).filter(Boolean);
}

function summarizeThread(thread) {
  const messages = thread.messages || [];
  if (!messages.length) return null;
  const first = messages[0];
  const last = messages[messages.length - 1];
  const subject = getHeader(first, 'Subject') || '(no subject)';
  const fromFirst = parseEmailAddrList(getHeader(first, 'From'))[0] || '(unknown)';
  const allParticipants = new Set();
  for (const m of messages) {
    parseEmailAddrList(getHeader(m, 'From')).forEach(a => allParticipants.add(a));
    parseEmailAddrList(getHeader(m, 'To')).forEach(a => allParticipants.add(a));
    parseEmailAddrList(getHeader(m, 'Cc')).forEach(a => allParticipants.add(a));
  }
  const lastDate = parseDate(getHeader(last, 'Date'));
  const firstDate = parseDate(getHeader(first, 'Date'));
  return {
    id: thread.id,
    subject,
    snippet: thread.snippet || '',
    fromFirst,
    participants: [...allParticipants],
    messageCount: messages.length,
    firstDate,
    lastDate,
    labels: messages.flatMap(m => m.labelIds || []).filter((v, i, a) => a.indexOf(v) === i)
  };
}

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

// ===== Body extraction =====

function decodeBase64Url(s) {
  if (!s) return '';
  return Buffer.from(s, 'base64url').toString('utf-8');
}

function extractTextAndAttachments(payload) {
  // Walk MIME tree. Prefer text/plain; fall back to text/html stripped. Collect attachments.
  let textBody = '';
  let htmlBody = '';
  const attachments = [];

  function walk(part) {
    if (!part) return;
    const mime = part.mimeType || '';
    const filename = part.filename || '';
    const body = part.body || {};
    if (filename && body.attachmentId) {
      attachments.push({
        name: filename,
        size_bytes: body.size || 0,
        mimetype: mime || 'application/octet-stream'
      });
      return;
    }
    if (mime === 'text/plain' && body.data) {
      textBody += decodeBase64Url(body.data);
    } else if (mime === 'text/html' && body.data) {
      htmlBody += decodeBase64Url(body.data);
    }
    if (Array.isArray(part.parts)) part.parts.forEach(walk);
  }
  walk(payload);

  let body = textBody;
  if (!body && htmlBody) body = stripHtml(htmlBody);
  return { body: body.trim(), attachments };
}

function stripHtml(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function stripQuotedReply(body) {
  // Best-effort: strip lines starting with > and "On <date> ... wrote:" blocks at end.
  const lines = body.split('\n');
  // Find a "On ... wrote:" line near the end that introduces quoted history; cut from there.
  for (let i = 0; i < lines.length; i++) {
    if (/^On\b.*\bwrote:\s*$/.test(lines[i].trim()) || /^From:\s/.test(lines[i].trim())) {
      // Heuristic: only treat as quoted if at least 30% of remaining lines start with >
      const remaining = lines.slice(i + 1);
      const quotedCount = remaining.filter(l => /^>/.test(l)).length;
      if (remaining.length === 0 || quotedCount / remaining.length > 0.3) {
        return lines.slice(0, i).join('\n').trim();
      }
    }
  }
  // Drop trailing > lines
  while (lines.length && /^>/.test(lines[lines.length - 1])) lines.pop();
  return lines.join('\n').trim();
}

// ===== Slug for filenames =====

function slugFromSubject(subject, threadId) {
  const base = subject
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/^(re|fwd|fw):\s*/i, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 60);
  const idFrag = threadId.slice(-8);
  return base ? `${base}-${idFrag}` : idFrag;
}

// ===== init-project =====

async function cmdInitProject(args) {
  const reinit = args.includes('--reinit');
  const existingCfg = await readProjectConfig();
  if (existingCfg && !reinit) {
    log(`Project already initialized: senders=${(existingCfg.senders || []).join(', ')}, label=${existingCfg.label}, window=${existingCfg.window}`);
    log('Pass --reinit to overwrite.');
    return;
  }

  // Resolve project_slug
  let projectSlug = existingCfg?.project_slug;
  if (!projectSlug) projectSlug = await readProjectSlugFromBmad();
  if (!projectSlug) {
    abort('project_slug not found. Add `project_slug: <slug>` to a _bmad/<module>/config.yaml file (e.g. _bmad/acme-agents/config.yaml), then re-run init-project.');
  }
  const labelName = `BA-intake/${projectSlug}`;

  log(`\n=== /fetch-gmail init-project (slug: ${projectSlug}) ===\n`);

  // Prompt senders
  const sendersInput = await ask(
    `Which email addresses should I track? (comma-separated; e.g. "alice@clientco.com, bob@clientco.com")\n> `
  );
  const senders = sendersInput.split(',').map(s => s.trim()).filter(Boolean);
  if (!senders.length) abort('No senders provided.');

  // Prompt window
  const windowInput = await ask(
    `Default time window? (e.g. 7d, 14d, 30d) [default: 14d]\n> `
  );
  const window = windowInput || '14d';

  // Build query
  const fromClause = senders.map(s => `from:${s}`).join(' OR ');
  const query = `(${fromClause}) newer_than:${window} -label:"${labelName}"`;
  log(`\nGmail query: ${query}\n`);

  // Find/create label
  log(`Resolving label "${labelName}"...`);
  const labelId = await findOrCreateLabel(labelName);
  log(`Label id: ${labelId}\n`);

  // Fetch threads (paginated, cap 50 per page)
  log(`Fetching matching threads...`);
  const list = await listThreads({ query, maxResults: 50 });
  const threadIds = (list.threads || []).map(t => t.id);
  if (!threadIds.length) {
    log(`No matching threads. Either adjust senders/window or come back later.`);
    // Still save config so subsequent runs don't re-prompt
    await writeProjectConfig({
      project_slug: projectSlug,
      label: labelName,
      label_id: labelId,
      senders,
      window
    });
    log(`\nSaved config to ${PROJECT_CONFIG_PATH}.`);
    return;
  }

  log(`Fetching thread metadata for ${threadIds.length} threads...`);
  const summaries = [];
  for (const id of threadIds) {
    try {
      const t = await getThreadMetadata(id);
      const s = summarizeThread(t);
      if (s) summaries.push(s);
    } catch (e) {
      log(`  warn: thread ${id} metadata fetch failed: ${e.message}`);
    }
  }
  // Sort by lastDate desc
  summaries.sort((a, b) => (b.lastDate || '').localeCompare(a.lastDate || ''));

  log('\nMatched threads:\n');
  summaries.forEach((s, i) => {
    const dateStr = (s.lastDate || '').slice(0, 10);
    log(`  ${i + 1}. ${dateStr}  "${s.subject}"  ${s.fromFirst}  (${s.messageCount} msgs)`);
  });

  log('');
  const pickInput = await ask(
    `Which to label? (numbers comma-separated, "1-${summaries.length}", "all", or "n" to cancel)\n> `
  );
  const picks = parsePicks(pickInput, summaries.length);
  if (!picks.length) {
    log('No threads picked. Saving config without labeling.');
    await writeProjectConfig({
      project_slug: projectSlug, label: labelName, label_id: labelId,
      senders, window
    });
    log(`Saved config to ${PROJECT_CONFIG_PATH}.`);
    return;
  }

  log(`\nAbout to apply label "${labelName}" to ${picks.length} threads:`);
  picks.forEach(i => log(`  ${i + 1}. ${(summaries[i].lastDate || '').slice(0, 10)}  "${summaries[i].subject}"`));
  const confirm = await ask(`\nProceed? [Y/n]\n> `);
  if (confirm && !/^y/i.test(confirm)) {
    log('Cancelled.');
    return;
  }

  log(`\nApplying label...`);
  for (const i of picks) {
    const tid = summaries[i].id;
    try {
      await gmailPost(`/threads/${tid}/modify`, { addLabelIds: [labelId] });
      log(`  ✓ ${tid} ("${summaries[i].subject}")`);
    } catch (e) {
      log(`  ✗ ${tid}: ${e.message}`);
    }
  }

  await writeProjectConfig({
    project_slug: projectSlug,
    label: labelName,
    label_id: labelId,
    senders,
    window
  });
  log(`\nSaved config to ${PROJECT_CONFIG_PATH}.`);
  console.log(JSON.stringify({
    ok: true,
    project_slug: projectSlug,
    label: labelName,
    senders,
    window,
    labeled: picks.length
  }, null, 2));
}

function parsePicks(input, max) {
  input = input.trim().toLowerCase();
  if (!input || input === 'n') return [];
  if (input === 'all') return Array.from({ length: max }, (_, i) => i);
  const out = new Set();
  for (const part of input.split(',')) {
    const p = part.trim();
    const range = p.match(/^(\d+)-(\d+)$/);
    if (range) {
      const a = parseInt(range[1], 10) - 1;
      const b = parseInt(range[2], 10) - 1;
      for (let i = a; i <= b; i++) if (i >= 0 && i < max) out.add(i);
    } else {
      const n = parseInt(p, 10) - 1;
      if (!isNaN(n) && n >= 0 && n < max) out.add(n);
    }
  }
  return [...out].sort((a, b) => a - b);
}

// ===== list =====

async function cmdList(args) {
  // Two ways to pick threads:
  //   --clients a@x.com,@client.com [--exclude help@client.com]  — straight from the project profile's
  //       tools.client_emails; no label and no saved config needed (the ba-tools way).
  //   no --clients — the older label mode: label:BA-intake/<slug> from docs/BA/.fetch-gmail-config.yaml.
  const opt = n => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
  const splitList = v => (v || '').split(',').map(x => x.trim()).filter(Boolean);
  const clients = splitList(opt('--clients'));
  const excluded = splitList(opt('--exclude'));
  const cfg = clients.length ? null : await readProjectConfig();
  if (!clients.length && !cfg) abort(`Pass --clients (from the profile's tools.client_emails), or run: node fetch.mjs init-project`);
  const window = opt('--window') || cfg?.window || '14d';
  const includeImported = args.includes('--include-imported');

  const query = clients.length
    ? `from:(${clients.join(' OR ')})${excluded.length ? ` -from:(${excluded.join(' OR ')})` : ''} newer_than:${window}`
    : `label:"${cfg.label}" newer_than:${window}`;
  const list = await listThreads({ query, maxResults: 100 });
  const threadIds = (list.threads || []).map(t => t.id);
  const summaries = [];
  for (const id of threadIds) {
    try {
      const t = await getThreadMetadata(id);
      const s = summarizeThread(t);
      if (s) summaries.push(s);
    } catch (e) { /* skip */ }
  }
  summaries.sort((a, b) => (b.lastDate || '').localeCompare(a.lastDate || ''));

  // Idempotency: check intake folder for existing files
  const cwd = process.cwd();
  const intakeDir = join(cwd, 'docs/BA/intake');
  let existingFiles = [];
  if (existsSync(intakeDir)) {
    existingFiles = (await readdir(intakeDir)).filter(f => f.endsWith('.md'));
  }
  for (const s of summaries) {
    const idFrag = s.id.slice(-8);
    s.alreadyImported = existingFiles.some(f => f.includes(`gmail-`) && f.includes(idFrag));
    s.intakePath = s.alreadyImported
      ? `docs/BA/intake/${existingFiles.find(f => f.includes(idFrag))}`
      : null;
  }

  const filtered = includeImported ? summaries : summaries.filter(s => !s.alreadyImported);

  console.log(JSON.stringify({
    mode: clients.length ? 'clients' : 'label', query, label: cfg?.label || null, window, count: filtered.length,
    countAlreadyImported: summaries.length - filtered.length,
    threads: filtered.map(s => ({
      id: s.id,
      subject: s.subject,
      from: s.fromFirst,
      participants: s.participants,
      lastDate: s.lastDate,
      messageCount: s.messageCount,
      alreadyImported: s.alreadyImported,
      intakePath: s.intakePath
    }))
  }, null, 2));
}

// ===== fetch =====

async function cmdFetch(args) {
  const cfg = await readProjectConfig();
  if (!cfg) abort(`${PROJECT_CONFIG_PATH} not found. Run: node fetch.mjs init-project`);

  const refresh = args.includes('--refresh');
  const positional = args.filter(a => !a.startsWith('--'));
  if (!positional.length) abort('Usage: fetch <thread-id>[,<id>...] [--refresh]');
  const ids = positional.flatMap(p => p.split(',')).map(s => s.trim()).filter(Boolean);

  const cwd = process.cwd();
  const intakeDir = join(cwd, 'docs/BA/intake');
  await ensureDir(intakeDir);

  const results = [];
  for (const id of ids) {
    try {
      const r = await fetchOneThread(id, { cfg, intakeDir, refresh });
      results.push(r);
    } catch (e) {
      results.push({ id, action: 'error', message: e.message });
    }
  }
  console.log(JSON.stringify({
    summary: {
      total: results.length,
      written: results.filter(r => r.action === 'written').length,
      refreshed: results.filter(r => r.action === 'refreshed').length,
      skipped: results.filter(r => r.action === 'skipped-already-imported').length,
      errors: results.filter(r => r.action === 'error').length
    },
    results
  }, null, 2));
}

async function fetchOneThread(threadId, opts) {
  const { cfg, intakeDir, refresh } = opts;
  const thread = await getThreadFull(threadId);
  const summary = summarizeThread(thread);
  if (!summary) return { id: threadId, action: 'error', message: 'empty thread' };

  const slug = slugFromSubject(summary.subject, threadId);
  const dateStr = (summary.lastDate || TODAY).slice(0, 10);
  const filename = `${dateStr}-gmail-${slug}.md`;
  const fullPath = join(intakeDir, filename);
  const relPath = `docs/BA/intake/${filename}`;

  if (existsSync(fullPath) && !refresh) {
    return { id: threadId, action: 'skipped-already-imported', path: relPath };
  }

  // Render messages
  const messageBlocks = [];
  const attachmentSet = new Map(); // dedupe by name
  thread.messages.forEach((msg, idx) => {
    const from = parseEmailAddrList(getHeader(msg, 'From'))[0] || '(unknown)';
    const date = parseDate(getHeader(msg, 'Date')) || '';
    const dt = date ? date.replace('T', ' ').slice(0, 16) + ' UTC' : '(no date)';
    const { body, attachments } = extractTextAndAttachments(msg.payload);
    const cleaned = stripQuotedReply(body) || '_(empty)_';
    messageBlocks.push(`### Message ${idx + 1} — ${from} — ${dt}\n\n${cleaned}\n`);
    for (const a of attachments) attachmentSet.set(a.name, a);
  });

  const fm = renderFrontmatter({
    source: 'gmail',
    date: dateStr,
    thread_id: threadId,
    subject: summary.subject,
    participants: summary.participants,
    message_count: summary.messageCount,
    first_message: summary.firstDate,
    last_message: summary.lastDate,
    labels: summary.labels,
    attachments: [...attachmentSet.values()],
    processed: false
  });

  const attachmentsSection = attachmentSet.size
    ? '\n## Attachments referenced\n\n' + [...attachmentSet.values()]
        .map(a => `- \`${a.name}\` — ${formatBytes(a.size_bytes)}, ${a.mimetype} — _not downloaded; pull manually from Gmail if needed_`)
        .join('\n') + '\n'
    : '';

  const content = `${fm}
# ${summary.subject}

**Subject:** ${summary.subject}
**Participants:** ${summary.participants.join(', ')}
**Started:** ${(summary.firstDate || '').replace('T', ' ').slice(0, 16)} UTC
**Last activity:** ${(summary.lastDate || '').replace('T', ' ').slice(0, 16)} UTC
**Messages:** ${summary.messageCount}
**Labels:** ${summary.labels.join(', ')}

## Messages

${messageBlocks.join('\n')}${attachmentsSection}`;

  await writeFile(fullPath, content, 'utf-8');
  return {
    id: threadId,
    action: existsSync(fullPath) && refresh ? 'refreshed' : 'written',
    path: relPath,
    subject: summary.subject,
    messageCount: summary.messageCount
  };
}

function renderFrontmatter(obj) {
  const lines = ['---'];
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) {
      if (v.length === 0) {
        lines.push(`${k}: []`);
      } else if (v.every(item => typeof item === 'string')) {
        lines.push(`${k}:`);
        for (const item of v) lines.push(`  - ${quoteScalar(item)}`);
      } else {
        // List of objects
        lines.push(`${k}:`);
        for (const item of v) {
          const fields = Object.entries(item).map(([k2, v2]) => `${k2}: ${quoteScalar(v2)}`).join(', ');
          lines.push(`  - { ${fields} }`);
        }
      }
    } else if (typeof v === 'boolean' || typeof v === 'number') {
      lines.push(`${k}: ${v}`);
    } else {
      lines.push(`${k}: ${quoteScalar(v)}`);
    }
  }
  lines.push('---');
  return lines.join('\n');
}

function formatBytes(n) {
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// ===== unlabel =====

async function cmdUnlabel(args) {
  const cfg = await readProjectConfig();
  if (!cfg) abort(`${PROJECT_CONFIG_PATH} not found.`);
  const ids = args.flatMap(a => a.split(',')).map(s => s.trim()).filter(Boolean);
  if (!ids.length) abort('Usage: unlabel <thread-id>[,<id>...]');
  const labelId = cfg.label_id || await findOrCreateLabel(cfg.label);

  const results = [];
  for (const id of ids) {
    try {
      await gmailPost(`/threads/${id}/modify`, { removeLabelIds: [labelId] });
      results.push({ id, action: 'unlabeled' });
    } catch (e) {
      results.push({ id, action: 'error', message: e.message });
    }
  }
  console.log(JSON.stringify({ label: cfg.label, results }, null, 2));
}

// ===== config-show =====

async function cmdConfigShow() {
  const cfg = await readProjectConfig();
  if (!cfg) {
    console.log(JSON.stringify({ initialized: false, hint: 'Run: node fetch.mjs init-project' }, null, 2));
    return;
  }
  console.log(JSON.stringify({ initialized: true, ...cfg }, null, 2));
}

// ===== Dispatcher =====

const SUBCOMMANDS = {
  'init-auth': cmdInitAuth,
  'init-project': cmdInitProject,
  'list': cmdList,
  'fetch': cmdFetch,
  'unlabel': cmdUnlabel,
  'config-show': cmdConfigShow
};

const [, , sub, ...rest] = process.argv;
if (!sub || !SUBCOMMANDS[sub]) {
  console.error('Usage: fetch.mjs <subcommand> [args]');
  console.error('Subcommands: init-auth, init-project, list, fetch, unlabel, config-show');
  process.exit(1);
}
try {
  await SUBCOMMANDS[sub](rest);
  closeReadline();
} catch (e) {
  closeReadline();
  console.error(`Error in ${sub}: ${e.message}`);
  process.exit(1);
}
