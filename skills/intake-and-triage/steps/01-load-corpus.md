---
name: 01-load-corpus
description: Load active intake files plus the project context (BMad PRD/Architecture/Epics, sprint-status, BA specs, release notes, JIRA backlog) for the triage run.
---

# Step 1 — Load Project Context

## 0. Set up folders (safe to re-run)

On every invocation, make sure these output paths exist (create if missing, leave alone if present). Each newly created directory gets a `.gitkeep` so the structure survives `git checkout` on a fresh clone:

- `docs/BA/intake/`
- `docs/BA/intake/.processed/`
- `docs/BA/triage/`
- `docs/BA/triage/.processed/`

Do **not** create:
- `docs/BA/specs/` — BA hand-authors first (D-47 owns spec creation; the directory appears when the BA writes the first spec)
- `docs/BA/releases/` — populated only when a release ships
- `_bmad-output/...` — input paths the skill *reads*, not output paths it owns; if the project keeps BMad files elsewhere, the search in §2–§3 finds them

This setup step is safe to re-run — running it on a project that already has the structure does nothing.

## 0.4. Freshness check on reports still in progress (run before §0.5)

Triaged work doesn't always wait for the report to be approved — the BA may hand-author a spec, file a JIRA ticket, edit a description, or update the dashboard between report-write and the next `/intake-and-triage` run. When that happens, the proposed_action block in the still-pending report becomes out of date: re-running the carry-out step would either redundantly write a stub over a fully-written spec, or surprise the BA with a "this is already done" outcome buried in `actioned_log`.

Run a freshness check on every report whose status is **not** finished — `pending-ba-review` or `partially-actioned`. Do **not** modify the reports themselves; this is a console-only signal so the BA sees what's been completed elsewhere before they review or re-approve.

For each report still in progress, parse every `proposed_action:` block and probe what's happened elsewhere:

- **`type: spec`** — read frontmatter at `proposed_action.path`. If the file exists with `status: ready`, `filed`, `parked` or `buried` (the template's statuses past `draft` / `eliciting`), it has been completed elsewhere. Capture `status`, `jira_ticket` (if present), and any `workflow_completed_at` timestamp. **Note:** `status: draft-from-jira` is a legacy state from older `/fetch-jira-backlog` runs (new runs write `status: draft`) — treat it as equivalent to `draft` (still waiting for `ba-spec`), not as post-draft. If a triage `type: spec` block's `proposed_action.path` collides with a `draft-from-jira` stub, surface it as a duplicate-detection signal: the JIRA fetcher and triage independently saw the same work.
- **`type: edit`** — call `node <skills>/jira/scripts/jira.mjs get-field <jira_key> <field> --max 1000`. If `proposed_value` (first ~200 chars, normalized whitespace) is already a text fragment of the live field, the edit is already applied. If the live field has changed since `current_excerpt` was captured, surface as changed-since (the BA may have applied an alternative).
- **`type: dashboard`** — read `docs/BA/dashboard.yaml` (the `ba-dashboard` skill's data). If an item with the same title is already in `proposed_action.list`, the dashboard item has been added elsewhere.
- **`type: note`** — nothing to check externally; skip.

Print a single section per report still in progress. Format:

```
Freshness check on docs/BA/triage/<report>.md (status: pending-ba-review):
  §3a CreditCo Risk-Review spec    — completed elsewhere (spec status: filed, JIRA: ACME-1647)
  §3a IP unified Transactions   — already applied to BOND-873.description (proposed_value text fragment present)
  §3a IP pivot fields           — note (nothing to check externally)
  §3c Salary-deduction Top-up   — note (nothing to check externally)
  §2 CreditCo subcodes              — note (nothing to check externally)
```

If nothing has shifted elsewhere, print `No external updates since report was written.` and move on.

This signal lets the BA decide whether to delete blocks (work is done elsewhere) or demote them to `note` before flipping the report to `approved`. Don't auto-edit the report — the BA owns that decision.

If `--at-commit {sha}` mode: skip §0.4 — retrospective runs reason about a frozen tree, not live external state.

## 0.5. Carry out approved reports (run before §1)

**Hand off to step 5 first.** Scan `docs/BA/triage/*.md` (excluding `.processed/`) for any report with `proposed_action:` blocks in `state: pending-decision`. If found, hand off to **step 05 (review-and-act)** — that step owns the interactive review loop, batch decision parsing, and per-block carry-out for the new flow. Step 05 returns control once it's done with that report (or the BA typed `stop`).

The rest of this section (§0.5 below) is the **batch carry-out path** — runs only when step 05 hasn't taken over. Specifically, this path fires when:
- A report has `status: approved` AND every block is in `state: pending-decision` (BA reviewed offline by editing the file directly, then flipped status), or
- A report has `status: approved` AND some blocks are in a `state: approved` interim state set by external tooling.

Both cases collapse to the same logic: process every `proposed_action:` block remaining in the report.

Scan `docs/BA/triage/*.md` for reports with frontmatter `status: approved`. For each one:

1. **Parse the report body** to collect every `proposed_action:` YAML block remaining (BA may have deleted blocks to dismiss, demoted any to `type: note` to defer, or edited inline). Preserve the order they appear in. Each surviving block is a contract the BA has approved.

2. **Carry out each block** by type. Track outcomes for the `actioned_log:` frontmatter.

   **After each block is processed**, update the block's `state:` and `decided_at:` fields in the report file, per this mapping:
   - Success / safe-to-re-run skip / already-applied → `state: materialized`, `decided_at: <today>`
   - Changed-since abort / placeholder abort → `state: aborted-drift`, `decided_at: <today>`
   - (`note` / `dismiss` outcomes only happen via step 05's interactive loop, not this batch path.)

   ### `type: spec`
   - **Skip if the file at `proposed_action.path` already exists.** Don't overwrite. Read the existing spec's frontmatter and log informatively against `actioned_log.specs_materialized`:
     - If `status: filed` and `jira_ticket: <KEY>` present → log `<path> (already filed externally — JIRA: <KEY>)`.
     - If `status: draft` (or any non-`filed` state) → log `<path> (already exists, status: <status>)`.
     - If frontmatter unparseable → log `<path> (already exists)`.
   - Otherwise, make sure the parent directory exists (`docs/BA/specs/{project}/{release_slug}/`); create with `mkdir -p` if missing.
   - Write the spec stub with frontmatter:
     The header follows the approved template (`docs/BA/specs/_template.md`). Fill only what
     triage knows; leave the rest as shown — `ba-spec` step 1 sets them.
     ```yaml
     ---
     id: '-'                 # ba-spec step 1 decides: FRnnn from docs/BA/specs/fr-register.md for a new capability, '-' for a change
     product: <acme|bond-portal>
     title: <title>
     status: draft
     status_reason:
     size:                   # ba-spec step 1
     owner: <BA name>
     decider: <client person from the intake, or ->
     opened: <today>
     needed_by: -
     last_touched: <today>
     downstream: [prd:next]
     covers: []              # ba-spec step 1
     depends_on: []
     jira_project: <the product's jira_project from the profile, or - when downstream has no jira>
     jira_issuetype: <Task|Bug>
     jira_fixversion: <fixVersion>
     jira_priority:          # ba-spec step 9
     jira_ticket: -
     source_intake: <comma-separated intake file paths from the report's intake_files_processed:>
     triage_ref: docs/BA/triage/<this-report>.md
     handoff_branch: -
     accepted_risks: []
     sources:
       - '<intake date> <source> — <one line on what it contributed>'
     ---

     # <title>

     ## 1. Need

     **Problem.** <user_problem_seed>

     <!-- Draft from triage. Run the ba-spec skill on this file to fill the remaining sections (template docs/BA/specs/_template.md), pass the section 16 ready gate and file it. -->
     ```
   - Append `<path>` to `actioned_log.specs_materialized`.

   ### `type: edit`
   - **Placeholder check (run first).** If `current_excerpt` is empty, looks like a TODO marker, or starts/contains the text `[verify`, `[TODO`, `[pull live`, `[paste`, or `[fill in`: **abort this edit** before any JIRA call — append `<jira_key>:<field> (placeholder excerpt)` to `actioned_log.edits_aborted` and continue. Step 03 §E is responsible for autofilling real content via `node <skills>/jira/scripts/jira.mjs get-field`; placeholders are a bug, not an acceptable input.
   - **Read live field.** Call `node <skills>/jira/scripts/jira.mjs get-field <key> <field> --max 1000` to fetch the current live value. Used by both the freshness check and the change-check.
   - **Already-applied check.** If a substantial text fragment of `proposed_value` (first ~200 normalized chars) is already present in the live field, the edit was applied elsewhere between report write and now. **Skip the PATCH** — append `<jira_key>:<field> (already applied externally)` to `actioned_log.edits_already_applied` and continue.
   - **Change-check (the "drift guard").** Compare the live value against `proposed_action.current_excerpt`. If the live value no longer contains the excerpt (text-fragment match; truncation tolerance: ±50 chars), **abort this edit** — append `<jira_key>:<field> (drift)` to `actioned_log.edits_aborted` and continue.
   - Otherwise, PATCH the ticket: `node <skills>/jira/scripts/jira.mjs update-field <key> <field> --change-kind <append|prepend|replace> --value-file <tmp>` (write `proposed_value` to a temp file first to handle multi-line content cleanly). The script re-reads the live ADF doc and merges at the content-array level so existing formatting survives. On success, append `<jira_key>:<field>` to `actioned_log.edits_posted`. On non-zero exit, append `<jira_key>:<field> (api_error: <stderr>)` to `actioned_log.edits_aborted`.

   ### `type: dashboard`
   - Write `proposed_action.item` to a temporary YAML file and run
     `uv run --with pyyaml python <skills>/ba-dashboard/scripts/dashboard.py add <list> --item <file>`,
     where `<list>` is `proposed_action.list` (`awaiting`, `todos` or `agenda`).
   - The script skips an item whose title is already in that list — log it as
     `<list>:<title> (already present)`; otherwise log `<list>:<title>` in
     `actioned_log.dashboard_items_written`. An `awaiting` item gets the next number automatically.
   - No `docs/BA/dashboard.yaml` yet: log `(no dashboard)`, keep the block, and tell the BA once at
     the end that the project has no dashboard (the `ba-dashboard` skill starts one).
   - **Do not build or publish after each item** — once, at the end of the run (see SKILL.md,
     *The dashboard page*).
   - Projects that still keep items in `docs/BA/dashboard.md` only: that file is retired once the
     project has a `dashboard.yaml`; do not write to both.

   ### `type: note`
   - No file written. Append `<candidate_id>: <todo>` to `actioned_log.notes_logged`. The note is preserved in the report itself for retrospective searchability.

3. **Move intake files.** Read `intake_files_processed:` from the frontmatter; move each listed file from `docs/BA/intake/` to `docs/BA/intake/.processed/`. If a listed file is missing, record `(already gone)` against that path and continue — don't abort.

4. **Flip the report status, then archive when finished.**
   - All blocks carried out cleanly (no `edits_aborted`) → `status: actioned`, set `actioned_at: <today>`, write the populated `actioned_log:`. Then **move the report file** from `docs/BA/triage/<report>.md` to `docs/BA/triage/.processed/<report>.md` — finished reports don't clutter the active folder. (The BA can still find them by path; the move is reversible if needed.)
   - Any `edits_aborted` entries → `status: partially-actioned`, set `actioned_at: <today>`, write the populated `actioned_log:`. **Leave the file in `docs/BA/triage/`** — the BA may re-flip status to `approved` after fixing the upstream change; on re-run, the report is re-scanned and only the still-aborted edits are retried.
   - `edits_already_applied` entries do **not** count as aborts — they're successful skips. A report with only `edits_posted` + `edits_already_applied` (no `edits_aborted`) flips to `actioned` and gets archived.

5. **Cleanup pass for legacy actioned reports.** After processing all currently-approved reports, scan `docs/BA/triage/*.md` once more for any report with `status: actioned` still in the active folder (e.g. from a prior run before this rule existed). Move each to `docs/BA/triage/.processed/`. Safe to re-run.

6. **Tell the user** what was carried out — one line per report:
   > *"Actioned report 2026-05-02-triage-report.md — wrote 3 spec stubs, posted 1 JIRA edit, appended 2 dashboard items, logged 4 notes; moved 2 intake files + report to .processed/."*
   >
   > *"Partially actioned report 2026-05-02-triage-report.md — 1 JIRA edit aborted because the field changed since (ACME-1640.description). Re-run after resolving (report stays in active folder)."*
   >
   > *"Actioned report 2026-05-02-triage-report.md — 1 spec already filed externally (JIRA: ACME-1647), 1 JIRA edit already applied externally; 0 fresh writes. Report archived."*

Do **not** carry out reports with any other status (`pending-ba-review`, `partially-actioned`, `actioned`). Approval is the single trigger.

If `--at-commit {sha}` mode: skip §0.5 — historical retrospective runs are read-only with respect to the working tree.

If `--dry-run` mode: skip §0.5 — `--dry-run` produces a report and stops; never change anything.

## 1. List unprocessed intake — propose, don't auto-process

After §0 setup and §0.5 archival, list all `*.md` files directly under `docs/BA/intake/` (**excluding** `docs/BA/intake/.processed/`).

**If the list is empty:**

Tell the BA in a short message:

> No unprocessed intake. Drop a file at `docs/BA/intake/<source>.md` to triage manually, or invoke a fetcher skill to pull from an external source:
> - `/fetch-fireflies` — pull recent meeting transcripts via the Fireflies API
> - `/fetch-gmail` — pull email threads via the Gmail API
> - `/fetch-slack` — pull threaded Slack messages from configured channels
> - `/fetch-portal` — pull the Client's Answers from the Relevant Clients Portal (only on projects whose profile has `tools.portal`)
>
> All of them write to `docs/BA/intake/` and feed this triage flow.
>
> **Different flow** — if you want to retrofit existing JIRA tickets with proper Business Requirements (rather than triage new client signals), use `/fetch-jira-backlog`. That writes template-shaped spec stubs to `docs/BA/specs/{project}/{release_slug}/` for the `ba-spec` skill to complete. It bypasses triage entirely — JIRA tickets aren't intake.

Then **stop** — write nothing else, no report, no further context loading.

**If the list is non-empty:**

For each file, parse frontmatter (`source`, `date`, `channel`, `participants`, etc.) and present a one-line summary:

```
Found N unprocessed intake files in docs/BA/intake/:
  1. 2026-04-30-fireflies-weekly-call.md  — fireflies, 2026-04-30, "Weekly client sync"
  2. 2026-04-29-slack-thread-billing.md   — slack, 2026-04-29, billing thread w/ Marcus

Triage these N files? [y/N]
```

**Wait for the BA's response.** On `n` or any non-`y` answer: stop, change nothing. On `y`: proceed to §2-§5 context loading and the rest of the workflow.

If `--at-commit {sha}` mode: use `git show {sha}:docs/BA/intake/<file>` to read the historical snapshot rather than the current working tree, and skip the `[y/N]` prompt — `--at-commit` is non-interactive Phase A retrospective testing.

## 2. BMad approved state — find, then walk whole-or-sharded

Projects vary in BMad-file layout. For each of PRD / Architecture / Epics, find the file by walking this **search order** and using the first match:

1. `_bmad-output/planning-artifacts/{name}.md` (BMad standard)
2. `_bmad-output/{name}.md`
3. `docs/_bmad/planning-artifacts/{name}.md`
4. `docs/planning-artifacts/{name}.md`
5. `docs/{name}.md`
6. **Broad search fallback:** `**/{name}.md` excluding `node_modules/`, `.git/`, `_bmad/` (the BMAD framework dir, not output), `dist/`, `build/`, `.next/`, `target/`, `vendor/`, `.archive/`. On multiple matches: pick the most-recently-modified path and record the choice in the report.

Where `{name}` is `prd`, `architecture`, `epics`. For each, also check the **sharded form** (`{name}/index.md`) at the same search-order levels — if both whole and sharded forms exist at the same level, prefer whole.

Record each found path in the project context and report frontmatter under `bmad_artefact_paths:`. If a file is **not found anywhere**, record `(not found)` and proceed — D-21 rules that depend on it (① / ② / ③ for PRD; ④ partly for Architecture) become partial. Greenfield-in-progress (PRD/Architecture/Epics partially authored) is a normal state.

## 3. BMad implementation state

**Find the implementation-artifacts directory** using the same search order as §2 (looking for a directory named `implementation-artifacts/`):

1. `_bmad-output/implementation-artifacts/`
2. `docs/_bmad/implementation-artifacts/`
3. `docs/implementation-artifacts/`
4. **Broad search fallback:** any directory named `implementation-artifacts/` outside the excluded paths (same exclusion list as §2).

From the resolved directory:

- Load **all** `*.md` files. **Do not enforce the `{epic_num}-{story_num}-{title}.md` naming** — projects use varied conventions (`tech-spec-*`, `customer-draft-*`, `{epic}-{story}-*`, etc.). For each file: capture title from frontmatter `title:` if present, else first H1, else filename stem. Capture `epic_num` / `story_num` from frontmatter or filename when the strict pattern matches; otherwise leave them null and treat the file as a generic implementation file for state-comparison purposes.
- **Sprint status:** look for `sprint-status.yaml` in the resolved implementation-artifacts directory **and** its parent. If found, parse for per-story status (`complete`, `in-progress`, `backlog`, etc.) — the **primary shipped/in-flight signal** (per D-46). If absent, record `sprint_status: (not found)` in the report header and downgrade D-46-dependent state-comparison to "based on file presence + JIRA only" — the run still produces a usable report, just with thinner shipped/in-flight detection.

## 4. BA specs

Find the BA specs directory using this search order:

1. `docs/BA/specs/` — preferred location for new projects
2. `docs/business-requirements/` — alternative layout used by some projects (treat each `business-requirement-*.md` as a spec)
3. **Broad search fallback:** any directory whose name matches `specs/` or `business-requirements/` outside the excluded paths.

Walk all `*.md` under the resolved directory (or `--at-commit` snapshot via `git ls-tree {sha} -r`).

For each spec: parse frontmatter — capture `title`, `product`, `status`, the release folder and `jira_ticket`. **A spec counts as approved** (for the "modifies approved content" and "removes a committed feature" rules in step 3) **when its `status` is `ready` or `filed`** — the approved template's statuses. Older specs that still carry an `approval:` block with `status: approved` count too. Every other spec (`draft`, `eliciting`, `parked`, `buried`) is not approved, but still counts for duplicate detection.

## 5. Release notes

Find via search order:

1. `docs/BA/releases/*-notes.md`
2. `docs/releases/*-notes.md`
3. **Broad search fallback:** any `*-notes.md` under a directory named `releases/` outside the excluded paths.

Secondary signal — `sprint-status.yaml` is primary. Release notes are the client-readable per-release summary; absent = no signal, not a problem.

## 6. JIRA backlog (read-only)

Only when the profile's `downstream` includes `jira`. Use `<skills>/jira/scripts/jira.mjs search "project in (<products' jira_project>) …"`, or the Atlassian connector's `searchJiraIssuesUsingJql`. Pull tickets in states: Backlog, In Progress, Done.

Capture per ticket: ID, summary, status, labels (especially the D-36 vocabulary: `approved`, `pending-approval`, `unconfirmed`, `cr`, `hotfix`, `contradiction-open`, `client-blocked`), Fix Version.

If MCP is unavailable or call fails, **note it in the report header** (`mcp_jira_available: false`) and proceed without — JIRA-side state-comparison will be partial but the BMad-approved-state and BA-spec signals still work.

## Output

A single in-memory project context the next steps will query. Pass to `steps/02-extract-candidates.md`.

## Edge cases

For unusual cases (a spec at two paths, sharded and whole BMad files side by side, `--at-commit` against a commit before the BMad folder existed): do not improvise routing — list the case in the report's 🟡 section and let the BA decide.
