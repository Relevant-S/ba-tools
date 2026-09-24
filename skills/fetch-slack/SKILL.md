---
name: fetch-slack
description: Pull recent threaded messages from a configured allowlist of Slack channels via the Slack Web API and write them as intake files at docs/BA/intake/YYYY-MM-DD-slack-<slug>.md for the /intake-and-triage skill to process. Channel-allowlist signal model — BA configures which channels carry client signal, skill pulls threaded conversations from those channels in a window. Companion to /fetch-fireflies and /fetch-gmail — same target folder, same intake-file shape, different source (`source: slack`).
---

# Fetch Slack

Pulls threaded messages from a configured allowlist of Slack channels and writes them as intake files for `/intake-and-triage` to ingest. Companion to `/fetch-fireflies` (meetings) and `/fetch-gmail` (email) — same target folder, same intake-file shape, different source (`source: slack`).

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Take `tools.slack.channels` and pass them to both `list` and `fetch` as `--channels <a,b>`. If `tools.slack` is `{}`, stop: this project has no client Slack channel.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Why channel-allowlist?

A BA's Slack workspace is mostly noise. Pulling "all channels" is unusable. Instead:

1. **Initiation (per project, one-time)**: BA configures a list of channels that carry signal (typically client-facing channels). Stored in `docs/BA/.fetch-slack-config.yaml`.
2. **Subsequent runs**: skill scans only those channels, returning **threaded** messages (top-level messages that have at least one reply) in the window. Drive-by single messages are filtered out by default — threading itself is the signal that something needed discussion.

## Per-project namespacing

The allowlist lives at `docs/BA/.fetch-slack-config.yaml` (project-scoped, git-trackable). The `project_slug` is read from `_bmad/<module>/config.yaml` and stored alongside the channels for traceability. One BA on multiple projects gets one config file per repo — zero cross-contamination.

## Prerequisites

### One-time Slack app setup (~10 min, plus admin approval)

1. **Create a Slack app** at [api.slack.com/apps](https://api.slack.com/apps) → "From scratch" → name it (e.g. "BA Intake") → pick your workspace.
2. **Add User Token Scopes** under OAuth & Permissions → User Token Scopes (NOT Bot Token Scopes):
   - `groups:history`, `groups:read` (private channels — required for client channels)
   - `users:read` (resolve user IDs to names — required, the script needs this)
   - Optional: `channels:history` + `channels:read` if any tracked channels are public
   - Optional: `im:history` + `im:read` for DMs
   - Optional: `mpim:history` + `mpim:read` for group DMs
3. **Install to workspace** → workspace owner/admin approves the request.
4. After approval, the OAuth & Permissions page shows a **User OAuth Token** (`xoxp-...`). Copy it.
5. **Add to `~/.claude/settings.json`** under the `env` block:

   ```json
   {
     "env": {
       "SLACK_USER_TOKEN": "xoxp-..."
     }
   }
   ```

6. **Restart the Claude Code session** so the env var propagates.

### Channel membership

Your token operates as **you**. For private channels the app/token must be a member — typically this means **you** must be in the channel (the User OAuth Token inherits your membership). For public channels, no membership needed; the token sees them automatically.

If `init-project` says "channel not found" for a channel you're sure exists, the most likely cause is that you're not a member of that private channel.

### Per-project initiation

After auth is set up, in the project root run:

```bash
node "<skills>/fetch-slack/scripts/fetch.mjs" init-project
```

The script:
- Reads `project_slug` from `_bmad/*/config.yaml` (errors clearly if missing).
- Asks: "Which Slack channels should I track? (comma-separated; channel names without #)"
- Asks: "Default time window? (7d, 14d, 30d, default 14d)"
- Resolves channel names → IDs via `conversations.list`. Reports any channels that couldn't be resolved (typically private channels you're not a member of).
- Saves `docs/BA/.fetch-slack-config.yaml` with `project_slug:`, `window:`, `channel_names:`, `channel_ids:`.

Re-run with `--reinit` to reconfigure.

## Workflow (subsequent runs)

1. **Verify token + project init.** Quick check: `echo $SLACK_USER_TOKEN`-style env probe (or `node -e "console.log(!!process.env.SLACK_USER_TOKEN)"`). Check that `docs/BA/.fetch-slack-config.yaml` exists; if not, run `init-project` first.

2. **List threaded messages.**

   ```bash
   node "<skills>/fetch-slack/scripts/fetch.mjs" list
   ```

   Default behaviour: scans configured channels in `config.window` window, returns thread metadata for top-level messages **with at least one reply**, written by **non-bot** users. Output JSON: `{window, channels, count, countAlreadyImported, threads: [{key, channel_name, channel_id, thread_ts, first_text_snippet, author, reply_count, last_activity_iso, alreadyImported, intakePath}, ...]}`.

   `key` is `<channel_id>:<thread_ts>` — pass to `fetch`.

   Override flags:

   | Flag | Effect |
   |---|---|
   | `--window <duration>` | Override config window (e.g. `--window 7d`) |
   | `--include-imported` | Don't filter out threads already written to `docs/BA/intake/` (useful with `--refresh`) |
   | `--include-bots` | Include messages authored by bot users (GitHub, Linear, etc. integrations) |
   | `--include-non-threaded` | Include drive-by single messages with zero replies |

3. **Show the list to the BA**, numbered, with already-imported flagged:

   ```
   Found 5 threads across 2 channels in last 14 days:

     1. 2026-05-08  #client-acme  alice (4 replies)  "Hey, we're seeing CreditCo retries fail..."
     2. 2026-05-07  #client-acme  bob (2 replies)    "Q2 roadmap follow-up — can we..." [already imported]
     3. 2026-05-05  #project-bondtrad   carol (6 replies)  "Salary deduction edge case from CreditCo..."
     ...

   Which to fetch? [all / 1,3 / numbers comma-separated / n to cancel]
   ```

   On `n` or empty: stop. On numeric pick: proceed.

4. **Fetch each picked thread.**

   ```bash
   node "<skills>/fetch-slack/scripts/fetch.mjs" fetch <channel_id>:<thread_ts>[,<channel_id>:<thread_ts>...]
   ```

   Per thread: GETs `conversations.replies` (parent + replies), resolves user IDs → display names, GETs a permalink for the parent, renders markdown, writes to `docs/BA/intake/{date}-slack-{channel-slug}-{subject-slug}-{ts-fragment}.md`. Idempotent: if file exists and `--refresh` not passed, skipped with a note.

5. **Summarize and offer to chain into triage.**

   ```
   Wrote N intake files:
     - docs/BA/intake/2026-05-08-slack-client-acme-creditco-retries-fail-23123456.md (4 msgs)
     - docs/BA/intake/2026-05-05-slack-project-bondtrad-salary-deduction-edge-case-87654321.md (6 msgs)
   Skipped 1 (already imported, use --refresh):
     - C123:1730000000.123456 → docs/BA/intake/2026-05-07-slack-client-acme-q2-roadmap-...md

   Run /intake-and-triage now? [Y/n]
   ```

   On `Y`: invoke `/intake-and-triage`. On `n`: stop.

## Output format

Each fetched intake file:

```markdown
---
source: slack
date: 2026-05-08
channel: '#client-acme'
channel_id: C0123456
thread_ts: '1730000000.123456'
permalink: 'https://yourworkspace.slack.com/archives/C0123456/p1730000000123456'
participants:
  - 'alice (U0001)'
  - 'bob (U0002)'
  - 'vadim (U0003)'
message_count: 5
first_message: '2026-05-05T14:23:00.000Z'
last_message: '2026-05-08T09:11:00.000Z'
processed: false
---

# Hey, we're seeing CreditCo retries fail when... (slack thread)

**Channel:** #client-acme
**Started:** 2026-05-05 14:23 UTC
**Last activity:** 2026-05-08 09:11 UTC
**Messages:** 5
**Permalink:** https://yourworkspace.slack.com/archives/C0123456/p1730000000123456

## Messages

### alice — 2026-05-05 14:23 UTC

Hey, we're seeing CreditCo retries fail when the upstream times out. Reproducible on staging — happens about 1 in 5 calls. @vadim any thoughts on the retry config?

### vadim — 2026-05-05 16:40 UTC

Looking now. The retry timeout is set to 30s but the upstream is taking 45s on slow paths. We should bump it.

### alice — 2026-05-08 08:55 UTC
[…]

### bob — 2026-05-08 09:11 UTC
[…]
```

`<@USERID>` mentions are rewritten as `@displayname` if the user was resolvable. Triage doesn't care about the source — it ingests whatever's in `docs/BA/intake/`.

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `SLACK_USER_TOKEN not set` | Env var missing | Add to `~/.claude/settings.json` env block, restart session |
| `Slack X error: invalid_auth` | Token invalid or revoked | Reinstall the Slack app, copy a fresh User OAuth Token |
| `Slack X error: missing_scope (needed scope: groups:history)` | Token lacks a required scope | Add the scope under User Token Scopes, reinstall the app, copy the fresh token |
| `Slack X error: not_in_channel` | Token's user isn't a member of the private channel | Join the channel in Slack and retry |
| `Slack X error: rate_limited` | Tier 3/4 rate limit hit (rare; ~50 req/min) | Wait ~1 min and retry |
| `channel not found` (during init-project) | Name doesn't match any visible channel | Check spelling; for private channels, ensure your token's user is a member |
| `project_slug not found in _bmad/*/config.yaml` | BMAD config missing the field | Add `project_slug: <slug>` to the config |
| `.fetch-slack-config.yaml not found and init-project not run` | Project not initialized | Run `init-project` |

## Notes for colleagues sharing this skill

- The skill is installed per project from ba-tools; the token is personal (in `~/.claude/settings.json`).
- The auth token is **user-level** (in `~/.claude/settings.json` env), tied to a single workspace + a single Slack identity.
- The project config (`docs/BA/.fetch-slack-config.yaml`) is **per-project** and git-trackable. Channel allowlist + window are project-specific.
- For multi-workspace BAs: only one workspace at a time per Slack app. To switch, re-install the app to the other workspace and update the token.
- Setup per BA: ~10 min Slack app + admin approval wait. Per project: ~1 min `init-project` (pick channels, set window).
