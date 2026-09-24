#!/usr/bin/env node
// fetch-slack skill — pulls recent threaded messages from configured Slack channels as intake files.
//
// Subcommands:
//   init-project [--reinit]                Per-project setup: pick channels + window, save config
//   list [--window <dur>] [--include-imported] [--include-bots] [--include-non-threaded]
//   fetch <thread-key>[,<thread-key>...] [--refresh]
//   config-show
//
// thread-key shape: "<channel_id>:<thread_ts>" (returned by `list`). Channel id required because
// thread_ts isn't unique across channels.
//
// Plain fetch, no npm deps. Run from project root for non-init subcommands.

import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline/promises';
import { stdin as input, stdout as output } from 'node:process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const TOKEN = process.env.SLACK_USER_TOKEN;
const SLACK_BASE = 'https://slack.com/api';

const PROJECT_CONFIG_PATH = 'docs/BA/.fetch-slack-config.yaml';
const INTAKE_DIR = 'docs/BA/intake';

// ===== utils (shared shape with fetch-gmail) =====

function log(msg) { console.error(msg); }

function abort(msg, code = 1) {
  log(`Error: ${msg}`);
  if (typeof closeReadline === 'function') closeReadline();
  process.exit(code);
}

async function ensureDir(d) { await mkdir(d, { recursive: true }); }

let _rl = null;
let _stdinQueue = null;
let _stdinQueueLoaded = false;

async function loadStdinQueueIfPiped() {
  if (_stdinQueueLoaded) return;
  _stdinQueueLoaded = true;
  if (input.isTTY) return;
  const chunks = [];
  for await (const chunk of input) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString('utf-8');
  _stdinQueue = text.split(/\r?\n/);
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
    process.stderr.write(question);
    const answer = _stdinQueue.shift() ?? '';
    process.stderr.write(answer + '\n');
    return answer.trim();
  }
  const answer = await getReadline().question(question);
  return answer.trim();
}

// ===== Minimal YAML (flat: scalars + string lists) =====

function yamlStringify(obj) {
  const lines = [];
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) {
      lines.push(`${k}:`);
      for (const item of v) lines.push(`  - ${quoteScalar(item)}`);
    } else if (v && typeof v === 'object') {
      lines.push(`${k}:`);
      for (const [k2, v2] of Object.entries(v)) lines.push(`  ${k2}: ${quoteScalar(v2)}`);
    } else {
      lines.push(`${k}: ${quoteScalar(v)}`);
    }
  }
  return lines.join('\n') + '\n';
}

function quoteScalar(v) {
  if (v === null || v === undefined) return "''";
  const s = String(v);
  if (/^[A-Za-z0-9_./@:#-]+$/.test(s) && !/^\d/.test(s)) return s;
  return `'${s.replace(/'/g, "''")}'`;
}

function yamlParse(text) {
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
      // List or nested object on subsequent indented lines
      const items = [];
      const nested = {};
      let isList = false, isObj = false;
      i++;
      while (i < lines.length && /^\s+/.test(lines[i])) {
        const li = lines[i];
        const lm = li.match(/^\s+-\s*(.*)$/);
        const om = li.match(/^\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$/);
        if (lm) { isList = true; items.push(unquoteScalar(lm[1].trim())); }
        else if (om) { isObj = true; nested[om[1]] = unquoteScalar(om[2].trim()); }
        i++;
      }
      out[key] = isList ? items : isObj ? nested : '';
    } else {
      out[key] = unquoteScalar(rest);
      i++;
    }
  }
  return out;
}

function unquoteScalar(s) {
  if (s === '' || s === "''" || s === '""') return '';
  if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1).replace(/''/g, "'");
  if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
  return s;
}

// ===== BMAD config (project_slug) =====

async function readProjectSlug() {
  const candidates = [];
  try {
    const modules = await readdir('_bmad', { withFileTypes: true });
    for (const m of modules) {
      if (!m.isDirectory()) continue;
      const cfg = join('_bmad', m.name, 'config.yaml');
      if (existsSync(cfg)) candidates.push(cfg);
    }
  } catch { /* no _bmad dir */ }
  for (const path of candidates) {
    try {
      const txt = await readFile(path, 'utf-8');
      const parsed = yamlParse(txt);
      if (parsed.project_slug) return parsed.project_slug;
    } catch { /* skip */ }
  }
  return null;
}

// ===== Config IO =====

async function readProjectConfig() {
  if (!existsSync(PROJECT_CONFIG_PATH)) return null;
  const txt = await readFile(PROJECT_CONFIG_PATH, 'utf-8');
  return yamlParse(txt);
}

async function writeProjectConfig(cfg) {
  await ensureDir(dirname(PROJECT_CONFIG_PATH));
  await writeFile(PROJECT_CONFIG_PATH, yamlStringify(cfg), 'utf-8');
}

// ===== Slack API =====

async function slackGet(method, params = {}) {
  if (!TOKEN) abort('SLACK_USER_TOKEN not set. Add to ~/.claude/settings.json env block and restart session.');
  const url = new URL(`${SLACK_BASE}/${method}`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!res.ok) throw new Error(`Slack ${method} HTTP ${res.status}`);
  const json = await res.json();
  if (!json.ok) throw new Error(`Slack ${method} error: ${json.error}${json.needed ? ` (needed scope: ${json.needed})` : ''}`);
  return json;
}

async function slackPaginated(method, params = {}, listKey) {
  const out = [];
  let cursor;
  do {
    const json = await slackGet(method, { ...params, ...(cursor ? { cursor } : {}), limit: params.limit ?? 200 });
    out.push(...(json[listKey] || []));
    cursor = json.response_metadata?.next_cursor;
  } while (cursor);
  return out;
}

// Channel + user caches (per-process)
let _channelCache = null;
async function listAllChannels({ types = 'public_channel,private_channel,mpim,im' } = {}) {
  if (_channelCache) return _channelCache;
  const channels = await slackPaginated('conversations.list', { types, exclude_archived: true }, 'channels');
  _channelCache = channels;
  return channels;
}

async function findChannelByName(name) {
  const norm = name.replace(/^#/, '').toLowerCase();
  const all = await listAllChannels();
  return all.find(c => (c.name || '').toLowerCase() === norm) || null;
}

const _userCache = new Map();
async function getUser(userId) {
  if (!userId) return null;
  if (_userCache.has(userId)) return _userCache.get(userId);
  try {
    const json = await slackGet('users.info', { user: userId });
    const u = {
      id: userId,
      name: json.user?.profile?.display_name_normalized || json.user?.profile?.real_name_normalized || json.user?.real_name || json.user?.name || userId,
      is_bot: !!json.user?.is_bot,
      email: json.user?.profile?.email || null
    };
    _userCache.set(userId, u);
    return u;
  } catch (e) {
    const fallback = { id: userId, name: userId, is_bot: false, email: null };
    _userCache.set(userId, fallback);
    return fallback;
  }
}

// ===== window parsing =====

function windowToOldestTs(window) {
  // window like "7d", "14d", "30d"
  const m = String(window).match(/^(\d+)d$/);
  if (!m) abort(`Unsupported window format: ${window}. Use Nd (e.g. 7d, 14d, 30d).`);
  const days = parseInt(m[1], 10);
  return Math.floor(Date.now() / 1000) - days * 86400;
}

// ===== init-project =====

async function cmdInitProject(args) {
  const reinit = args.includes('--reinit');
  const existingCfg = await readProjectConfig();
  if (existingCfg && !reinit) {
    log(`Project already initialized: channels=${(existingCfg.channels || []).join(', ')}, window=${existingCfg.window}`);
    log(`Re-run with --reinit to reconfigure.`);
    return;
  }

  const projectSlug = await readProjectSlug();
  if (!projectSlug) abort('project_slug not found in _bmad/*/config.yaml. Add it and re-run.');

  log(`\n=== /fetch-slack init-project (slug: ${projectSlug}) ===\n`);

  const channelsInput = await ask(
    `Which Slack channels should I track? (comma-separated; channel names without #, e.g. "client-acme, project-foo")\n> `
  );
  const channelNames = channelsInput.split(',').map(s => s.trim().replace(/^#/, '')).filter(Boolean);
  if (!channelNames.length) abort('No channels provided.');

  const windowInput = await ask(
    `Default time window? (e.g. 7d, 14d, 30d) [default: 14d]\n> `
  );
  const window = windowInput || '14d';

  log(`\nResolving channel names to IDs...`);
  const channels = [];
  for (const name of channelNames) {
    const ch = await findChannelByName(name);
    if (!ch) {
      log(`  ✗ #${name} — not found (check spelling, or your token isn't a member of this channel)`);
      continue;
    }
    log(`  ✓ #${ch.name} (${ch.id})${ch.is_private ? ' [private]' : ''}`);
    channels.push({ name: ch.name, id: ch.id, is_private: !!ch.is_private });
  }
  if (!channels.length) abort('No channels resolved. Check token scopes and channel membership.');

  await writeProjectConfig({
    project_slug: projectSlug,
    window,
    channel_names: channels.map(c => c.name),
    channel_ids: channels.map(c => c.id)
  });

  log(`\nSaved config to ${PROJECT_CONFIG_PATH}.`);
  console.log(JSON.stringify({
    ok: true,
    project_slug: projectSlug,
    window,
    channels: channels.map(c => ({ name: c.name, id: c.id, is_private: c.is_private }))
  }, null, 2));
}

// ===== list =====

function parseFlags(args) {
  const flags = {};
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--window') flags.window = args[++i];
    else if (a === '--include-imported') flags.includeImported = true;
    else if (a === '--include-bots') flags.includeBots = true;
    else if (a === '--include-non-threaded') flags.includeNonThreaded = true;
    else if (a === '--refresh') flags.refresh = true;
    else if (a === '--channels') flags.channels = args[++i];
  }
  return flags;
}

function tsToIso(ts) {
  if (!ts) return null;
  const ms = Math.floor(parseFloat(ts) * 1000);
  return new Date(ms).toISOString();
}

function tsToDateOnly(ts) {
  return tsToIso(ts)?.slice(0, 10);
}

async function intakeFileForThread(channelName, threadTs) {
  // List existing intake files; match by suffix to detect already-imported
  try {
    const files = await readdir(INTAKE_DIR);
    const tsFragment = threadTs.replace('.', '');
    const match = files.find(f => f.startsWith(`${tsToDateOnly(threadTs)}-slack-`) && f.includes(tsFragment.slice(-8)));
    return match ? join(INTAKE_DIR, match) : null;
  } catch { return null; }
}

// --channels a,b (the project profile's tools.slack.channels) replaces the saved config: names are
// resolved to ids on every run, so nothing has to be initialised first. Without it, the older
// docs/BA/.fetch-slack-config.yaml is used.
async function configFromFlagsOrFile(flags) {
  if (flags.channels) {
    const names = flags.channels.split(',').map(n => n.trim().replace(/^#/, '')).filter(Boolean);
    const ids = [], found = [], missing = [];
    for (const n of names) {
      const c = await findChannelByName(n);
      if (c) { ids.push(c.id); found.push(n); } else missing.push(n);
    }
    if (missing.length) log(`Not found (or you are not a member): ${missing.join(', ')}`);
    return { channel_ids: ids, channel_names: found, project_slug: '' };
  }
  const cfg = await readProjectConfig();
  if (!cfg) abort(`Pass --channels (from the profile's tools.slack.channels), or run: node fetch.mjs init-project`);
  return cfg;
}

async function cmdList(args) {
  const flags = parseFlags(args);
  const cfg = await configFromFlagsOrFile(flags);
  const window = flags.window || cfg.window || '14d';
  const oldest = windowToOldestTs(window);

  const channelIds = cfg.channel_ids || [];
  const channelNames = cfg.channel_names || [];
  if (!channelIds.length) abort('No channels in config. Re-run init-project.');

  const allThreads = [];
  for (let i = 0; i < channelIds.length; i++) {
    const id = channelIds[i];
    const name = channelNames[i] || id;
    let cursor;
    do {
      const json = await slackGet('conversations.history', {
        channel: id, oldest, limit: 200, ...(cursor ? { cursor } : {})
      });
      for (const msg of (json.messages || [])) {
        // Top-level only: ts equals thread_ts (or no thread_ts means a singleton message)
        const isThreadParent = !msg.thread_ts || msg.thread_ts === msg.ts;
        if (!isThreadParent) continue;
        const replyCount = msg.reply_count || 0;
        if (!flags.includeNonThreaded && replyCount === 0) continue;
        // Skip subtype 'channel_join' / 'bot_message' unless flagged
        if (msg.subtype === 'channel_join' || msg.subtype === 'channel_leave') continue;
        if (!flags.includeBots && (msg.bot_id || msg.subtype === 'bot_message')) continue;

        const author = await getUser(msg.user);
        if (!flags.includeBots && author?.is_bot) continue;

        const threadTs = msg.ts;
        const intakePath = await intakeFileForThread(name, threadTs);
        const alreadyImported = !!intakePath;
        if (alreadyImported && !flags.includeImported) continue;

        allThreads.push({
          key: `${id}:${threadTs}`,
          channel_id: id,
          channel_name: name,
          thread_ts: threadTs,
          first_text_snippet: (msg.text || '').slice(0, 120).replace(/\s+/g, ' '),
          author: author?.name || msg.user,
          reply_count: replyCount,
          last_activity_ts: msg.latest_reply || msg.ts,
          last_activity_iso: tsToIso(msg.latest_reply || msg.ts),
          alreadyImported,
          intakePath
        });
      }
      cursor = json.response_metadata?.next_cursor;
    } while (cursor);
  }

  // Sort by last_activity desc
  allThreads.sort((a, b) => parseFloat(b.last_activity_ts) - parseFloat(a.last_activity_ts));

  console.log(JSON.stringify({
    window,
    channels: channelNames,
    count: allThreads.length,
    countAlreadyImported: allThreads.filter(t => t.alreadyImported).length,
    threads: allThreads
  }, null, 2));
}

// ===== fetch =====

function slugify(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
}

async function fetchThread(channelId, threadTs) {
  const replies = await slackPaginated('conversations.replies', { channel: channelId, ts: threadTs, limit: 200 }, 'messages');
  // Resolve users
  for (const m of replies) {
    if (m.user) await getUser(m.user);
  }
  // Permalink for parent
  let permalink = null;
  try {
    const pl = await slackGet('chat.getPermalink', { channel: channelId, message_ts: threadTs });
    permalink = pl.permalink;
  } catch { /* optional */ }
  return { messages: replies, permalink };
}

function resolveMentions(text) {
  return String(text || '').replace(/<@(U[A-Z0-9]+)>/g, (_, uid) => {
    const usr = _userCache.get(uid);
    return usr ? `@${usr.name}` : `@${uid}`;
  });
}

function renderIntakeMarkdown({ channelName, channelId, thread, permalink, projectSlug }) {
  const parent = thread.messages[0];
  const lastTs = thread.messages[thread.messages.length - 1]?.ts || parent.ts;
  const participantsSet = new Map();
  for (const m of thread.messages) {
    const u = _userCache.get(m.user);
    if (u) participantsSet.set(u.id, u.name);
  }
  const participants = [...participantsSet.entries()].map(([id, name]) => `${name} (${id})`);

  const resolvedParentText = resolveMentions(parent.text || '');
  const subject = resolvedParentText.slice(0, 80).replace(/\s+/g, ' ').trim() || `slack thread in #${channelName}`;
  const fm = [
    '---',
    `source: slack`,
    `date: ${tsToDateOnly(parent.ts)}`,
    `channel: '#${channelName}'`,
    `channel_id: ${channelId}`,
    `thread_ts: '${parent.ts}'`,
    permalink ? `permalink: '${permalink}'` : null,
    `participants:`,
    ...participants.map(p => `  - ${quoteScalar(p)}`),
    `message_count: ${thread.messages.length}`,
    `first_message: '${tsToIso(parent.ts)}'`,
    `last_message: '${tsToIso(lastTs)}'`,
    `processed: false`,
    '---',
    '',
    ''
  ].join('\n');

  const headerLines = [
    `# ${subject} (slack thread)`,
    '',
    `**Channel:** #${channelName}`,
    `**Started:** ${tsToIso(parent.ts).replace('T', ' ').slice(0, 16)} UTC`,
    `**Last activity:** ${tsToIso(lastTs).replace('T', ' ').slice(0, 16)} UTC`,
    `**Messages:** ${thread.messages.length}`,
    permalink ? `**Permalink:** ${permalink}` : null,
    '',
    '## Messages',
    '',
    ''
  ].filter(l => l !== null);
  const header = headerLines.join('\n');

  const body = thread.messages.map(m => {
    const u = _userCache.get(m.user) || { name: m.user || 'unknown' };
    const when = tsToIso(m.ts).replace('T', ' ').slice(0, 16);
    const text = resolveMentions(m.text);
    return `### ${u.name} — ${when} UTC\n\n${text}\n`;
  }).join('\n');

  return `${fm}${header}${body}\n`;
}

async function cmdFetch(args) {
  const flags = parseFlags(args);
  const positional = args.filter(a => !a.startsWith('--'));
  if (!positional.length) abort('Usage: fetch <channel_id:thread_ts>[,<channel_id:thread_ts>...]');
  const cfg = await configFromFlagsOrFile(flags);

  const keys = positional.flatMap(s => s.split(',').map(k => k.trim()).filter(Boolean));
  const results = [];
  for (const key of keys) {
    const [channelId, threadTs] = key.split(':');
    if (!channelId || !threadTs) {
      results.push({ key, action: 'error', error: 'invalid key format (expected channel_id:thread_ts)' });
      continue;
    }
    const idx = (cfg.channel_ids || []).indexOf(channelId);
    const channelName = idx >= 0 ? cfg.channel_names[idx] : channelId;
    try {
      const existing = await intakeFileForThread(channelName, threadTs);
      if (existing && !flags.refresh) {
        results.push({ key, action: 'skipped', path: existing, reason: 'already imported (use --refresh)' });
        continue;
      }
      const thread = await fetchThread(channelId, threadTs);
      const md = renderIntakeMarkdown({
        channelName, channelId, thread,
        permalink: thread.permalink,
        projectSlug: cfg.project_slug
      });
      const tsFragment = threadTs.replace('.', '').slice(-8);
      const subjectSlug = slugify(resolveMentions((thread.messages[0]?.text || '')).slice(0, 60));
      const fname = `${tsToDateOnly(threadTs)}-slack-${slugify(channelName)}-${subjectSlug ? subjectSlug + '-' : ''}${tsFragment}.md`;
      const path = join(INTAKE_DIR, fname);
      await ensureDir(INTAKE_DIR);
      await writeFile(path, md, 'utf-8');
      results.push({
        key, action: existing ? 'refreshed' : 'written', path,
        channel: channelName, message_count: thread.messages.length
      });
    } catch (e) {
      results.push({ key, action: 'error', error: e.message });
    }
  }

  const summary = {
    total: results.length,
    written: results.filter(r => r.action === 'written').length,
    refreshed: results.filter(r => r.action === 'refreshed').length,
    skipped: results.filter(r => r.action === 'skipped').length,
    errors: results.filter(r => r.action === 'error').length
  };
  console.log(JSON.stringify({ summary, results }, null, 2));
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
  'init-project': cmdInitProject,
  'list': cmdList,
  'fetch': cmdFetch,
  'config-show': cmdConfigShow
};

const [, , sub, ...rest] = process.argv;
if (!sub || !SUBCOMMANDS[sub]) {
  console.error('Usage: fetch.mjs <subcommand> [args]');
  console.error('Subcommands: init-project, list, fetch, config-show');
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
