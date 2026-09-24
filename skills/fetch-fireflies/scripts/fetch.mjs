#!/usr/bin/env node
// fetch.mjs — Fireflies GraphQL fetch helper for the /fetch-fireflies skill.
//
// Usage:
//   node fetch.mjs list [--limit N] [--days N | --since YYYY-MM-DD] [--email <addr>]
//   node fetch.mjs fetch <id> --out <path-template> [--summary-only]
//
// The --out path supports {date} and {slug} placeholders, filled in from the
// transcript's date and a slugified title.
//
// --summary-only: skip the GraphQL `sentences` field and omit the "Full
// transcript" section from the written markdown. ~85% smaller files; useful
// when triage only needs the summary block (overview, key points, action items).
//
// `list` defaults to the last 14 days, filtered to meetings where
// FIREFLIES_USER_EMAIL was a participant. Override:
//   --days N            last N days from today
//   --since YYYY-MM-DD  explicit start date
//   --email <addr>      override the user email for one call
//
// Requires:
//   FIREFLIES_API_KEY    — get at app.fireflies.ai → Settings → Developer
//   FIREFLIES_USER_EMAIL — the email to filter participant on (your work email
//                          as Fireflies knows it)

import fs from 'node:fs';
import path from 'node:path';

const API = 'https://api.fireflies.ai/graphql';
const KEY = process.env.FIREFLIES_API_KEY;
const USER_EMAIL = process.env.FIREFLIES_USER_EMAIL;

function die(msg, code = 1) {
  process.stderr.write(`error: ${msg}\n`);
  process.exit(code);
}

if (!KEY) {
  die('FIREFLIES_API_KEY not set. Add it to ~/.claude/settings.json under "env": {} or set it in your shell profile.');
}

const args = process.argv.slice(2);
const cmd = args[0];

function flag(name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
}

async function gql(query, variables) {
  const res = await fetch(API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${KEY}`,
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) {
    const body = await res.text();
    die(`Fireflies API ${res.status}: ${body}`);
  }
  const json = await res.json();
  if (json.errors) {
    die(`GraphQL errors: ${JSON.stringify(json.errors, null, 2)}`);
  }
  return json.data;
}

function fmtDate(ms) {
  if (!ms) return '';
  return new Date(Number(ms)).toISOString().slice(0, 10);
}

function slugify(s) {
  return (s || 'meeting')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'meeting';
}

function quoteYaml(s) {
  if (s == null) return '""';
  const str = String(s);
  return `"${str.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

if (cmd === 'list') {
  const limit = parseInt(flag('--limit', flag('--clients') ? '50' : '20'), 10);  // fetch more when filtering by client
  const since = flag('--since');
  const days = flag('--days');
  const email = flag('--email', USER_EMAIL);

  if (!email) {
    die('No participant email. Set FIREFLIES_USER_EMAIL in env or pass --email <addr>.');
  }

  let fromDate;
  if (since) {
    fromDate = `${since}T00:00:00.000Z`;
  } else {
    const daysBack = days ? parseInt(days, 10) : 14;
    fromDate = new Date(Date.now() - daysBack * 86400 * 1000).toISOString();
  }

  const variables = { limit, fromDate, participantEmail: email };

  const data = await gql(`
    query Transcripts($limit: Int, $fromDate: DateTime, $participantEmail: String) {
      transcripts(limit: $limit, fromDate: $fromDate, participant_email: $participantEmail) {
        id
        title
        date
        duration
        participants
        organizer_email
      }
    }
  `, variables);

  // --clients / --exclude: keep only calls with at least one client participant (the project's
  // tools.client_emails). An entry starting with "@" matches a whole domain.
  const splitList = v => (v || '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
  const clients = splitList(flag('--clients'));
  const excluded = splitList(flag('--exclude'));
  const matches = (addr, list) => list.some(e => e.startsWith('@') ? addr.endsWith(e) : addr === e);
  const isClientCall = t => (t.participants || []).map(p => String(p).toLowerCase().trim())
    .some(p => matches(p, clients) && !matches(p, excluded));
  const all = data.transcripts || [];
  const transcripts = clients.length ? all.filter(isClientCall) : all;
  const out = {
    filteredOut: all.length - transcripts.length,
    meetings: transcripts.map(t => ({
      id: t.id,
      title: t.title || '(untitled)',
      date: fmtDate(t.date),
      duration_min: Math.round(t.duration || 0),
      participants: t.participants || [],
      organizer: t.organizer_email || '',
    })),
  };
  process.stdout.write(JSON.stringify(out) + '\n');
}
else if (cmd === 'fetch') {
  const id = args[1];
  if (!id || id.startsWith('--')) die('fetch requires <id> as the first positional arg');
  const outTemplate = flag('--out');
  if (!outTemplate) die('fetch requires --out <path>');
  const summaryOnly = args.includes('--summary-only');

  const sentencesField = summaryOnly ? '' : `
        sentences {
          speaker_name
          text
        }`;

  const data = await gql(`
    query Transcript($id: String!) {
      transcript(id: $id) {
        id
        title
        date
        duration
        participants
        meeting_link
        host_email
        organizer_email
        summary {
          overview
          short_summary
          shorthand_bullet
          bullet_gist
          outline
          action_items
          keywords
        }${sentencesField}
      }
    }
  `, { id });

  const t = data.transcript;
  if (!t) die(`transcript ${id} not found`);

  const dateStr = fmtDate(t.date);
  const slug = slugify(t.title);
  const finalPath = outTemplate
    .replace(/\{date\}/g, dateStr)
    .replace(/\{slug\}/g, slug);

  const sum = t.summary || {};
  const participants = t.participants || [];

  const frontmatterLines = [
    '---',
    'source: fireflies',
    `date: ${dateStr}`,
    `channel: ${quoteYaml(t.title || 'untitled')}`,
    `meeting_id: ${t.id}`,
    `meeting_link: ${quoteYaml(t.meeting_link || '')}`,
    `organizer: ${quoteYaml(t.organizer_email || '')}`,
    `host: ${quoteYaml(t.host_email || '')}`,
    'participants:',
    ...participants.map(p => `  - ${quoteYaml(p)}`),
    'processed: false',
    '---',
    '',
  ];

  const bodyLines = [
    `# ${t.title || 'Untitled meeting'}`,
    '',
    `**Date:** ${dateStr}  `,
    `**Duration:** ${Math.round(t.duration || 0)} min  `,
    `**Participants:** ${participants.join(', ') || '(none listed)'}  `,
  ];
  if (t.meeting_link) bodyLines.push(`**Meeting link:** ${t.meeting_link}  `);
  bodyLines.push('');

  const overview = sum.overview || sum.short_summary;
  if (overview) {
    bodyLines.push('## Summary', '', overview, '');
  }
  if (sum.outline) {
    bodyLines.push('## Outline', '', sum.outline, '');
  }
  if (sum.bullet_gist) {
    bodyLines.push('## Key points', '', sum.bullet_gist, '');
  }
  if (sum.shorthand_bullet && !sum.bullet_gist) {
    bodyLines.push('## Key points', '', sum.shorthand_bullet, '');
  }
  if (sum.action_items) {
    bodyLines.push('## Action items', '', sum.action_items, '');
  }
  if (sum.keywords && sum.keywords.length) {
    bodyLines.push('## Keywords', '', sum.keywords.join(', '), '');
  }

  if (!summaryOnly) {
    bodyLines.push('## Full transcript', '');
    for (const s of (t.sentences || [])) {
      bodyLines.push(`**${s.speaker_name || 'Unknown'}:** ${s.text || ''}`);
    }
    bodyLines.push('');
  }

  const content = frontmatterLines.join('\n') + bodyLines.join('\n');
  fs.mkdirSync(path.dirname(finalPath), { recursive: true });
  fs.writeFileSync(finalPath, content, 'utf-8');

  process.stdout.write(JSON.stringify({
    id: t.id,
    title: t.title,
    date: dateStr,
    path: finalPath,
    size_bytes: Buffer.byteLength(content, 'utf-8'),
    sentences: (t.sentences || []).length,
  }, null, 2) + '\n');
}
else {
  die('usage:\n  fetch.mjs list [--limit N] [--since YYYY-MM-DD]\n  fetch.mjs fetch <id> --out <path-template> [--summary-only]\n\n  --out supports {date} and {slug} placeholders.\n  --summary-only skips the full transcript (~85% smaller files).');
}
