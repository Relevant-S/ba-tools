---
name: fetch-fireflies
description: Pull recent meeting transcripts from Fireflies via the GraphQL API and write them as intake files at docs/BA/intake/YYYY-MM-DD-fireflies-<slug>.md for the /intake-and-triage skill to process. Use when the BA needs new intake from a recent client call. Companion to /intake-and-triage — that skill suggests this one when its intake folder is empty.
---

# Fetch Fireflies

Fetches meeting transcripts and summaries from the Fireflies GraphQL API (`api.fireflies.ai/graphql`) and writes them as properly-formatted intake files for `/intake-and-triage` to ingest.

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Take `tools.client_emails.include` and `.exclude` and pass them to `list` as `--clients <a,b,@domain>` and `--exclude <…>`, so only this project's client calls are listed. If `include` is empty, say so and list everything.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Prerequisites

Two env vars:

| Var | Purpose |
|---|---|
| `FIREFLIES_API_KEY` | Fireflies developer API key |
| `FIREFLIES_USER_EMAIL` | Your work email as Fireflies knows it — used to filter `list` to meetings where you were a participant |

**Recommended setup** — add to `~/.claude/settings.json` (user-global) or `.claude/settings.local.json` (project-only) under `env`:

```json
{
  "env": {
    "FIREFLIES_API_KEY": "your-fireflies-api-key-here",
    "FIREFLIES_USER_EMAIL": "you@yourcompany.com"
  }
}
```

Get the key from Fireflies at **app.fireflies.ai → Settings → Developer Settings → API key**. The user email is the one Fireflies registered you as on the workspace (the same address that shows up in `participants` on your meetings). Start a new session after adding (New session in the desktop app): a session reads the keys only when it starts. `ba-setup me` adds these lines for you.

## Workflow

1. **Verify API key.** Run a `node -e "console.log(!!process.env.FIREFLIES_API_KEY)"` quick check. If `false`, tell the user how to set it (per Prerequisites above) and stop — do not proceed without a key.

2. **List recent meetings.** Default behaviour: list meetings from the **last 14 days** where `FIREFLIES_USER_EMAIL` was a participant. Run:

   ```bash
   node "<skills>/fetch-fireflies/scripts/fetch.mjs" list
   ```

   **Override flags** (use only when the BA explicitly asks for a different window):

   | Flag | Effect | Example |
   |---|---|---|
   | `--days N` | Last N days from today | `--days 30` |
   | `--since YYYY-MM-DD` | Explicit start date (overrides `--days`) | `--since 2026-03-01` |
   | `--limit N` | Max results returned (default 20) | `--limit 50` |
   | `--email <addr>` | Override the participant email for one call | `--email someone@x.com` |

   Output JSON shape: `{meetings: [{id, title, date, duration_min, participants, organizer}, ...]}` — compact JSON, no pretty-printing. Empty `meetings` array means nothing matched the filter (most likely cause: window too narrow or `FIREFLIES_USER_EMAIL` doesn't match the email Fireflies has on file).

3. **Show the list to the user**, numbered. Ask which to fetch:

   ```
   Found N meetings in the last 14 days where you were a participant:
     1. 2026-04-30 — Weekly client sync (47 min) — alice@..., bob@...
     2. 2026-04-29 — Discovery call (62 min)     — bob@..., charlie@...
     3. 2026-04-25 — Backlog grooming (33 min)   — alice@..., team@...

   Which to fetch? [all / 1,3 / number(s) comma-separated / n to cancel]
   ```

   Wait for the user's answer. On `n` or empty answer: stop. If they ask for a different window ("show me last 30 days"), re-run `list` with `--days 30` (or whatever they specify) before re-prompting.

4. **Fetch each selected meeting.** For each ID, run:

   ```bash
   node "<skills>/fetch-fireflies/scripts/fetch.mjs" fetch <id> --out "<project>/docs/BA/intake/{date}-fireflies-{slug}.md"
   ```

   The `{date}` and `{slug}` placeholders are filled in by the script based on the transcript's date and title. `<project>` is the current project root (e.g., `<project root>`). Output is JSON: `{id, title, date, path, size_bytes, sentences}`.

   **Optional: `--summary-only` flag.** Drops the `sentences { ... }` field from the GraphQL query and omits the "Full transcript" section from the written file. Resulting file is ~85% smaller (a 40-min call goes from ~43 KB to ~6 KB). Use when triage only needs the summary block and verbatim quotes from the transcript aren't required. Trade-off: candidates can't cite exact spoken phrases, only summary lines.

5. **Summarize and offer to chain into triage.** After all fetches succeed, list the written files and ask the user whether to run `/intake-and-triage` immediately:

   ```
   Wrote N intake files:
     - docs/BA/intake/2026-04-30-fireflies-weekly-client-sync.md
     - docs/BA/intake/2026-04-25-fireflies-backlog-grooming.md

   Run /intake-and-triage now? [Y/n]
   ```

   On `Y` / `y` / empty answer: invoke the `/intake-and-triage` skill in the same turn. On `n`: stop and leave the files for the user to triage later. Skip the prompt entirely if zero files were written (nothing to triage).

## Output format

Each fetched intake file has this shape:

```markdown
---
source: fireflies
date: 2026-04-30
channel: "Weekly client sync"
meeting_id: 01JBKGS6TGFJDX...
meeting_link: https://app.fireflies.ai/view/...
organizer: alice@example.com
host: alice@example.com
participants:
  - alice@example.com
  - bob@example.com
processed: false
---

# Weekly client sync

**Date:** 2026-04-30
**Duration:** 47 min
**Participants:** alice@example.com, bob@example.com

## Summary
<Fireflies overview>

## Outline
<sectioned outline if Fireflies provides one>

## Key points
<bullet gist>

## Action items
<action items>

## Keywords
<comma-separated>

## Full transcript
**Speaker A:** ...
**Speaker B:** ...
```

The `/intake-and-triage` skill reads `docs/BA/intake/*.md` and ingests each as a candidate intake.

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `FIREFLIES_API_KEY not set` | Env var missing | Add to `~/.claude/settings.json` env block, then start a new session |
| `Fireflies API 401` | Invalid or expired API key | Generate a new one at app.fireflies.ai → Settings → Developer |
| `Fireflies API 429` | Rate limited | Wait ~1 min and retry |
| `transcript <id> not found` | ID deleted or wrong | Re-run `list` to get current IDs |
| `GraphQL errors` | Schema mismatch (Fireflies API change) | Open the script and adjust the query |

## Future fetchers

Same pattern will be used for `/fetch-gmail` and `/fetch-slack`. Each fetcher writes to `docs/BA/intake/YYYY-MM-DD-<source>-<slug>.md` with `source:` frontmatter set accordingly. Triage doesn't care about the source — it ingests whatever's in the folder.
