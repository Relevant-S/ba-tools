---
name: fetch-jira-backlog
description: Bulk-import existing JIRA tickets from ACME+BOND as spec stubs in the approved template's header shape at docs/BA/specs/{project}/{release_slug}/{slug}.md, ready for the ba-spec skill to write up (its re-create path — the ticket already exists). Different flow from /fetch-fireflies (which writes to docs/BA/intake/) — this writes specs/ directly. Use when the BA wants to retrofit pre-existing manually-written JIRA tickets with proper specs.
---

# Fetch JIRA Backlog

Pulls open JIRA tickets via the Atlassian REST API and writes one spec stub per ticket at `docs/BA/specs/{project}/{release_slug}/{slug}.md`, with the header of the approved template (`docs/BA/specs/_template.md`), `status: draft` and `source: jira-import`. The BA then runs the **`ba-spec`** skill on each stub (its *re-creating a spec that is already filed* path, since the ticket exists) to write the spec, pass the ready gate and — with approval — rewrite the ticket description from `ba-spec`'s `assets/ticket-template.md`.

This is a **different flow** from `/fetch-fireflies`:

| Skill | Writes to | Purpose |
|---|---|---|
| `/fetch-fireflies` | `docs/BA/intake/` | Raw client signals → `/intake-and-triage` digests them |
| `/fetch-jira-backlog` | `docs/BA/specs/` | Existing JIRA tickets → `ba-spec` writes them up in the approved template |

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Build `--projects KEY=folder,…` from `products[]` (`jira_project` = `key`) and pass it to `list` and `fetch`. If `downstream` has no `jira`, stop: this project does not file tickets.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Prerequisites

The same JIRA env vars used by the `/jira` skill:

| Var | Purpose |
|---|---|
| `JIRA_BASE_URL` | e.g. `https://example.atlassian.net` |
| `JIRA_EMAIL` | The email tied to the API token |
| `JIRA_API_TOKEN` | Token from id.atlassian.com → Account settings → Security |

If any are missing the script aborts with a clear message; add them to `~/.claude/settings.json` env block and restart the session.

## Workflow

1. **Verify env vars.** Quick check that `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` are set. If not, tell the user how to set them and stop.

2. **List tickets.** Default behaviour: list open tickets across ACME + BOND. Run from the **project root** (so the script can resolve `docs/BA/specs/`):

   ```bash
   node "<skills>/fetch-jira-backlog/scripts/fetch.mjs" list
   ```

   **Override flags** (use only when the BA explicitly asks):

   | Flag | Effect | Example |
   |---|---|---|
   | `--jql <query>` | Custom JQL (replaces default) | `--jql "project=ACME AND fixVersion=Refactoring"` |
   | `--limit N` | Max tickets returned (default 50) | `--limit 100` |

   Default JQL is `project in (ACME, BOND) AND statusCategory != Done ORDER BY updated DESC`.

   Output JSON shape: `{count, tickets: [{key, summary, status, issuetype, fixVersions, project, assignee, alreadyImported, targetPath}, ...]}`. The `alreadyImported` flag is `true` when a spec with matching `jira_ticket:` frontmatter exists somewhere under `docs/BA/specs/` — those tickets are flagged but not skipped from the listing.

3. **Show the list to the user**, numbered. Group by project; flag already-imported tickets so the BA can choose whether to skip or refresh:

   ```
   Found N open tickets in ACME + BOND:

   ACME (M):
     1. ACME-1647  Risk-Review multi-candidate spec      (Backlog, Task)         [already imported]
     2. ACME-1640  CreditCo outbound report retry            (To Do, Task)
     3. ACME-1612  Salary deduction top-up               (In Progress, Task)
     ...
   BOND (K):
     M+1. BOND-873   Unified Transactions view             (Backlog, Task)
     ...

   Which to fetch? [all / 1,3,5 / numbers comma-separated / keys (ACME-1640,BOND-873) / n to cancel]
   Append --refresh to re-pull JIRA Source on already-imported tickets (skips otherwise).
   ```

   Wait for the user's answer. On `n` or empty: stop. If the BA passes a JQL or other override, re-run `list` with that override before re-prompting.

4. **Fetch each selected ticket.** Run:

   ```bash
   node "<skills>/fetch-jira-backlog/scripts/fetch.mjs" fetch ACME-1640,BOND-873
   ```

   Or with refresh:

   ```bash
   node "<skills>/fetch-jira-backlog/scripts/fetch.mjs" fetch ACME-1647 --refresh
   ```

   Per ticket, the script:
   - Resolves project folder (`ACME → acme`, `BOND → bond-portal`).
   - Resolves `release_slug` by reading `docs/BA/specs/{project}/_releases.md` and matching the ticket's fixVersion to a row. Tickets without fixVersion → bucketed under `_unscheduled/` with a console warning. Tickets whose fixVersion isn't in `_releases.md` → also `_unscheduled/` with warning (BA can move later, or refresh `_releases.md`).
   - Computes slug as kebab-case of the ticket summary (lowercase, ASCII, hyphens, trimmed punctuation).
   - **Idempotency:** scans every `docs/BA/specs/**/*.md` for matching `jira_ticket: <KEY>` frontmatter. If found, skips (or refreshes the `## JIRA Source` section if `--refresh` is passed AND the existing spec is still an untouched import — `status: draft` with `source: jira-import`, or the legacy `draft-from-jira` — never refreshes a spec `ba-spec` has moved on).
   - **Collision guard:** if the target path already exists with a different (or absent) `jira_ticket:`, abort that ticket and add it to the collision list — the BA decides what to do.
   - Writes the stub (frontmatter + `# {summary}` + `## JIRA Source`) using ADF→Markdown rendering of the live description.

   Output JSON per ticket: `{key, action, path, message?}` where `action ∈ {written, skipped-already-imported, refreshed, collision, no-fixversion-warning}`.

5. **Summarize and offer to chain into `ba-spec`.** After all fetches finish, list the written and skipped paths and ask whether to start `ba-spec` on one of them:

   ```
   Summary:
     Wrote 3 new stubs:
       - docs/BA/specs/acme/refactoring/creditco-outbound-retry.md (ACME-1640)
       - docs/BA/specs/bond-portal/backlog/unified-transactions.md (BOND-873)
       - docs/BA/specs/acme/_unscheduled/legacy-cleanup.md (ACME-1599) — no fixVersion, bucketed under _unscheduled/
     Refreshed 1 stub:
       - docs/BA/specs/acme/backlog/risk-review-multi-candidate.md (ACME-1647)
     Skipped 2 already-imported (use --refresh to re-pull):
       - ACME-1612 → docs/BA/specs/acme/refactoring/salary-deduction-top-up.md
       - BOND-861   → docs/BA/specs/bond-portal/backlog/pivot-fields.md
     Collisions (none written, BA decides):
       - ACME-1605 — target docs/BA/specs/acme/backlog/widget-fix.md exists without jira_ticket: in frontmatter

   Run ba-spec now on one of these? [Y/n]
   ```

   On `Y` / `y` / empty: ask which stub, then invoke the `ba-spec` skill on it. On `n`: stop. Skip the prompt entirely if zero stubs were written or refreshed.

## Output format

Each fetched stub looks like:

```markdown
---
id: '-'                       # ba-spec step 1 decides (FRnnn for a new capability, '-' for a change)
product: '{acme|bond-portal}'
title: '{summary}'
status: 'draft'
status_reason: ''
size: ''                      # ba-spec step 1
owner: ''
decider: ''
opened: '{today}'
needed_by: '-'
last_touched: '{today}'
downstream: [prd:next]
covers: []                    # ba-spec step 1
depends_on: []
jira_project: '{ACME|BOND}'
jira_issuetype: '{Task|Bug|...}'
jira_fixversion: '{fixVersion or empty if unscheduled}'
jira_priority: '{priority from the ticket}'
jira_ticket: '{KEY}'
jira_status: '{To Do|In Progress|Backlog|...}'
source_intake: ''
triage_ref: ''
handoff_branch: '-'
accepted_risks: []
source: 'jira-import'
fetched_at: '{today}'
---

# {summary}

## JIRA Source

> Imported from JIRA ticket [{KEY}](https://example.atlassian.net/browse/{KEY}) on {fetched_at}.
> The `ba-spec` skill reads this section as raw input when it writes the spec in the approved template.
> When the spec is written, this section is removed and the ticket description is rewritten from `ba-spec`'s `assets/ticket-template.md` (summary, how to test, spec link).

**Status:** {jira_status}
**Issue type:** {jira_issuetype}
**Fix Version:** {fixVersions or "(none)"}
**Assignee:** {assignee or "(unassigned)"}

### Description

{ADF-rendered-as-markdown description, or "(empty)" if the ticket has no description}
```

The `## JIRA Source` section is the boundary marker — `ba-spec` step 1 reads it as raw input and the written spec drops it. A comment under it tells the BA to run `ba-spec`.

## Single-ticket mode

`fetch <KEY>` works for one ticket as well as comma-separated lists. Useful when the BA is about to spec a specific ticket — `node fetch.mjs fetch ACME-1234` and they're in.

## Refresh mode

`--refresh` re-pulls the JIRA description and replaces the `## JIRA Source` section in the existing stub. Constraints:
- Only operates on untouched imports: `status: draft` with `source: jira-import`, or the legacy `status: draft-from-jira` from older runs. Never touches a spec `ba-spec` has moved on (`eliciting`, `ready`, `filed`, …) — that is content the BA owns.
- Replaces only the `## JIRA Source` section; preserves anything else in the file.
- Updates `fetched_at:` in frontmatter.

If you want to refresh a `filed` spec, do not re-fetch it — run `ba-spec` on it instead (its re-create path re-reads the ticket).

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `JIRA env vars not set` | Missing `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | Add to `~/.claude/settings.json`, restart session |
| `JIRA API 401` | Invalid or expired token | Generate a new one at id.atlassian.com → Security |
| `JIRA API 404` (on a specific key) | Ticket key doesn't exist or you lack permission | Verify the key; check project permissions |
| `_releases.md not found at docs/BA/specs/{project}/` | Project folder missing or not initialized | Create the folder + `_releases.md` (use `node <skills>/jira/scripts/jira.mjs refresh-specs` if available) |
| `Collision: <path> exists with different jira_ticket` | Slug clash with a non-JIRA-import spec | BA renames one of them, or passes `--keep-going` (planned) to skip and continue |

## Future fetchers

Same pattern applies for any system with pre-existing tickets we want to retrofit (e.g. Linear, Asana). Each fetcher writes to `docs/BA/specs/{project}/{release_slug}/{slug}.md` with `source: <fetcher-id>`. `ba-spec` only needs `source: <something>` and the seeded `## <Source-Title>` section to adapt — adding a new fetcher is a script-level change.
