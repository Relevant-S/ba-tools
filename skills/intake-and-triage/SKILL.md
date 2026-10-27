---
name: intake-and-triage
description: Triage incoming client intakes (Fireflies summaries, Slack threads, emails dropped at docs/BA/intake/) against the project's approved state — BMad PRD/Architecture/Epics, sprint-status, existing BA specs, JIRA backlog — and produce a single triage report classifying each candidate by lane (hotfix / standard / scope-change) and drafting a `proposed_action:` block per candidate (`spec` / `edit` / `dashboard` / `note`). The BA reviews each block (leave / edit / demote / delete) and flips status to `approved`. The next invocation carries out surviving blocks: writes spec stubs, posts JIRA edits (with a check that the field hasn't changed since), appends dashboard items, archives intake. Invoke when new files have landed in docs/BA/intake/, or when running retrospective dry-runs against historical transcripts.
---

# Intake & Triage

A BA-side workflow skill that reads new client intake events, compares them against the project's approved state, and produces a triage report for the BA to review and act on. Sits *between* raw client input and BMad's planning chain — does **not** call BMad downstream itself; the BA invokes BMad agents manually after triage.

**This skill and its step files are the whole reference.** The original design document (47 numbered decisions, `bmad-workflow-improvements.md`) is no longer kept in any repo; the codes it used (D-21, D-22 …) survive as labels in the step files, and each is explained where it is used.

**How to run it:** when invoked, follow the step files in order — `steps/01-load-corpus.md` → `steps/02-extract-candidates.md` → `steps/03-diff-and-classify.md` → `steps/04-write-report.md` → `steps/05-review-and-materialize.md`.

Step 5 is the interactive review-and-act loop. After step 4 writes the report, step 5 prints a summary, walks the BA through each `proposed_action:` block (single-block or batch decisions), and acts on approved blocks immediately. You can stop and resume across runs.

**Status:** live — in weekly use since May 2026. `--dry-run` still changes nothing but the report.

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. It gives the products and their Jira projects (`products[]`), where specs go (`downstream`, `release_folders`), the client-review route (`client_review` — the clarification page) and the client sources (`tools`).
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Glossary (skill-specific names you'll see throughout)

These names appear in YAML frontmatter and state files — they're kept verbatim because the skill reads them back on later runs. Plain meaning in parens:

- `state: pending-decision` (block waiting for the BA to choose)
- `state: materialized` (block was approved and the action has been carried out — finished)
- `state: noted` (block demoted to a note — title logged, no file written — finished)
- `state: dismissed` (block deleted — title logged for the audit trail — finished)
- `state: aborted-drift` (a JIRA edit was skipped because the live ticket changed since the report was written; the BA needs to fix things upstream and re-approve)
- `status: pending-ba-review` (report waiting for BA review)
- `status: approved` (BA reviewed offline by editing the file and flipped this manually)
- `status: actioned` (every block reached a finished state; the report is moved to `.processed/`)
- `status: partially-actioned` (some blocks finished, but at least one was aborted because the JIRA field changed since; report stays in the active folder for re-run)
- *change-check / "drift guard"* — the pre-write check that compares the live JIRA field against the excerpt the report was based on; if they no longer match, the edit aborts.

## MVP scope

**In:** when invoked, **find what's there, propose outputs, and walk the BA through approving / dismissing each in chat — carrying out the approved ones eagerly**. The skill:

1. **Freshness check (§0.4):** scans reports still in progress for `proposed_action:` blocks whose work has been completed elsewhere since the report was written — spec written up and filed with `ba-spec`, JIRA edit applied through another channel, dashboard item added manually, etc. Prints a per-report summary so the BA sees what's already done before reviewing or re-approving. Doesn't modify the reports.
2. **Resume / batch carry-out (§0.5 + step 05):** §0.5 hands off to step 05 if any report has `state: pending-decision` blocks left → step 05 resumes the interactive loop. Otherwise §0.5 falls through to its batch carry-out path for `status: approved` reports (backwards-compat: BA reviewed offline by editing the report file + flipping status). Both paths use the same per-block rules — spec writes / Jira PATCH with pre-write checks / dashboard appends with auto-number + placeholder strip + duplicate-check / note logs. Intake files move to `.processed/`; reports flip to `actioned` (or `partially-actioned` if the JIRA field changed since) and archive.
3. Lists unprocessed intake files (any `*.md` directly under `docs/BA/intake/`, excluding `.processed/`); asks the BA `Triage these N files? [y/N]` and only proceeds on `y`.
4. On `y`: extract candidates → classify each by lane (`hotfix` / `standard` / `scope-change`) per the D-21 threshold rules → compare against the approved state (below) → **draft one `proposed_action:` block per candidate** (`spec` / `edit` / `dashboard` / `note`), each carrying `state: pending-decision` → flag duplicates, contradictions (🔴 hard-block), borderline calls (🟡 BA judgement), and shipped/in-flight matches → write a single triage report at `docs/BA/triage/YYYY-MM-DD-triage-report.md` with `status: pending-ba-review`.
5. **Review-and-act (step 05):** prints the chat summary with each block prefixed by a 1-based index, then prompts:
   ```
   N blocks pending decision. Decide:
     <selector> <verb>[, <selector> <verb>, …]
     Verbs: ok | edit | note | dismiss | skip
     Selectors: 3 | 1-4 | 1,3,5 | all | rest
   ```
   Examples: `1-4 ok, 3,7 dismiss` (approve 1, 2, 4 — the 3 was overridden — and dismiss 3, 7); `all ok`; `rest note`. Last input wins. On approval, the action runs immediately. On `stop`, state saves; resume on next invocation.
6. If no unprocessed intake files exist AND no resumable reports: tell the BA they can drop a file at `docs/BA/intake/<source>.md` or invoke a fetcher skill (`/fetch-fireflies`, `/fetch-gmail`, `/fetch-slack`, and `/fetch-portal` on projects whose profile has `tools.portal`).

**Proposed action types** (drafted in step 03, carried out in step 01 §0.5):

| Type | What carrying it out does |
|---|---|
| `spec` | Writes a stub at `docs/BA/specs/{project}/{release_slug}/{slug}.md` in the approved template (`docs/BA/specs/_template.md`) — the template's header + `# Title` + `## 1. Need` (the problem seed) only. Status `draft`. The BA then runs the `ba-spec` skill on the file to fill the remaining sections, pass the ready gate and file it. |
| `edit` | Patches a field on an existing JIRA ticket via `node <skills>/jira/scripts/jira.mjs update-field`. Three pre-write checks: placeholder (excerpt looks like `[TODO]`), already-applied (proposed_value text fragment already in the live field — skip cleanly), changed-since (`current_excerpt` no longer in the live field — abort and re-surface in a `partially-actioned` report). |
| `dashboard` | Adds one item to the project dashboard (`docs/BA/dashboard.yaml`) with the `ba-dashboard` script — to `awaiting` (parked on someone else), `todos` (on the BA) or `agenda` (for the next client call). A title already there is skipped. |
| `note` | No file written. Logged in the report's `actioned_log.notes_logged`. |

**BA review options per block** — at the step 05 prompt, decide each block via verb:

| Verb | Effect |
|---|---|
| `ok` (alias `y`, `approve`) | Carry out immediately (spec write / Jira PATCH / dashboard append / note log). Block transitions to `state: materialized`. |
| `edit` | Skill pauses; BA edits the block in the report file, types `done`, then is re-prompted for the new verb. |
| `note` | Demote to note — no file, block title logged in `actioned_log.notes_logged`. Block transitions to `state: noted`. |
| `dismiss` (alias `d`, `delete`) | Block deleted from report; title logged in `actioned_log.dismissed`. Block transitions to `state: dismissed`. |
| `skip` | Block stays `state: pending-decision` for next-run resume. |

Decisions can be **batched** in one input: `1-4 ok, 3,7 dismiss, rest note`. Last input wins. Skill prints a `Resolving: ...` summary and asks `Apply? [Y/n]` before acting.

**Per-block `state:` lifecycle:**

| `state:` | Set by | Meaning |
|---|---|---|
| `pending-decision` | Step 04 (initial draft) | Skill hasn't asked the BA yet, or BA said `skip`. |
| `materialized` | Step 05 / §0.5 | Approved + action carried out. Finished. |
| `noted` | Step 05 | Demoted — title logged, no file written. Finished. |
| `dismissed` | Step 05 | Deleted — title logged for the audit trail. Finished. |
| `aborted-drift` | Step 05 / §0.5 | Jira `edit` block was skipped because the live field changed since the report was written; needs upstream fix + re-approval. Re-runnable. |

**Top-level `status:` lifecycle:**

| Status | Set by | Meaning |
|---|---|---|
| `pending-ba-review` | Agent (on report write) | Initial — at least one block still `pending-decision`. |
| `approved` | BA (manual frontmatter edit) | Backwards-compat batch path — BA reviewed offline by editing the report file, flipped status. §0.5 treats every still-`pending-decision` block as `ok`. |
| `actioned` | Agent | All blocks reached a finished `state:` (`materialized` / `noted` / `dismissed`); intake files moved to `.processed/`; report auto-moved to `docs/BA/triage/.processed/`. |
| `partially-actioned` | Agent | Some blocks ended in `state: aborted-drift`; report stays in active `docs/BA/triage/` and is re-runnable after fixing things upstream and re-approving the still-pending blocks. |

**Out (deferred):** invoking downstream skills or agents (`ba-spec`, correct-course, create-story stay BA-driven); Confluence publishing; lane-specific automated routing.

## Inputs (project state read by the skill)

The skill **finds** BMad and BA files on each run rather than hard-coding paths — projects vary in layout. Found paths are recorded in the triage report frontmatter (`bmad_artefact_paths:`) so you can verify them. See `steps/01-load-corpus.md` §2–§5 for the search order and broad-search fallback.

| What | Default search | Purpose |
|---|---|---|
| Active intakes | `docs/BA/intake/*.md` (skip `.processed/`) | Items to triage |
| BMad PRD | `prd.md` / `prd/index.md` (whole or sharded) — found by search | Approved product scope — D-21 ① / ② / ③ |
| BMad Architecture | `architecture.md` / `architecture/index.md` — found by search | Architectural baseline — augments D-21 ④ |
| BMad Epics | `epics.md` / `epics/index.md` — found by search | Epic-level committed scope — duplicate detection for ② |
| BMad story files | All `*.md` under the resolved implementation-artifacts dir | Story-level committed scope |
| Sprint status | `sprint-status.yaml` next to implementation-artifacts (handled gracefully if absent) | Shipped / in-flight / backlog state |
| BA specs | `docs/BA/specs/**/*.md`, fallback `docs/business-requirements/*.md` | In-flight BA specs not yet picked up by BMad |
| Release notes | `docs/BA/releases/*-notes.md`, fallback `docs/releases/*-notes.md` | Per-release client-readable summary (secondary) |
| JIRA backlog | `<skills>/jira/scripts/jira.mjs search` (or the Atlassian connector's `searchJiraIssuesUsingJql`), read-only — only when `downstream` has `jira` | Tickets without specs yet |

For BMad sharded docs: prefer the whole-file form when both exist; otherwise walk `{doc}/index.md` + all shards.

The skill **sets up** `docs/BA/intake/`, `docs/BA/triage/`, and their `.processed/` subfolders (with `.gitkeep` placeholders) on first invocation if they don't exist — see step 1 §0. It does not create `docs/BA/specs/` or `_bmad-output/` directories; specs are BA-hand-authored (D-47), and BMad output paths are read inputs the skill finds, not output paths it owns.

## Outputs

**On every run (step 4):**

| What | Where |
|---|---|
| Triage report | `docs/BA/triage/YYYY-MM-DD-triage-report.md` |

Report sections: items grouped by lane (each carrying a `proposed_action:` block), 🔴 contradictions (hard-block until resolved), 🟡 borderline / BA-judgement, duplicates / already-shipped findings, summary of changes vs. project state.

**On approval (step 05 interactive `ok`, or step 1 §0.5 batch path — never under `--dry-run` / `--non-interactive` / `--at-commit`):**

| What | Where |
|---|---|
| Spec stubs (per `type: spec`) | `docs/BA/specs/{project}/{release_slug}/{slug}.md` (status `draft`) — skipped if file already exists (logged with externally-filed JIRA key when applicable) |
| JIRA field edits (per `type: edit`) | Live ticket patched via `node <skills>/jira/scripts/jira.mjs update-field` — checked against placeholder, already-applied, and changed-since |
| Dashboard items (per `type: dashboard`) | `docs/BA/dashboard.yaml` via `ba-dashboard add`; the page is rebuilt and republished once at the end of the run |
| Intake archive moves | `docs/BA/intake/<file>` → `docs/BA/intake/.processed/<file>` |
| Report status flip | `pending-ba-review` → `actioned` (or `partially-actioned` if any field changed since) |
| Finished-report archive | `actioned` reports auto-move from `docs/BA/triage/<report>.md` → `docs/BA/triage/.processed/<report>.md` |

## Modes

- `--dry-run` — process intake, produce triage report, **change nothing else** (no archive moves, no JIRA writes, no spec writes). Safe to re-run. Required for Phase A and Phase B.
- `--at-commit {sha}` — reason about project state at a past commit. Required for Phase A retrospective testing on historical Fireflies transcripts.

## Calibration (historical — how the skill was tested before go-live, May 2026)

- **Phase A** — `--dry-run --at-commit` against 5–10 historical transcripts spanning the request variance. Outputs to `_bmad-output/skill-tests/YYYY-MM-DD-phase-a-{set}.md`.
- **Phase B** — shadow mode on live intake in `--dry-run` alongside the BA's manual triage. 2–4 weeks; weekly disagreement diff.
- **Phase C** — live with batch-confirm checkpoints (D-19) — real writes, no auto-actions; BA approves each batch.

**Hard zeros for go-live:** no hallucinated items, no missed contradictions, no catastrophic CR/Story misroute (must be 🟡 BA-judgement when uncertain). Soft thresholds in §10.

## Downstream (BA manually invokes these after triage)

- **`ba-spec`** — on every spec stub this skill writes (thin spec first, then the full spec).
- **The clarification page** (`client_review` in the profile) — for items that need the client's answer.
- `bmad-correct-course` — when a triaged item changes approved scope in the middle of a sprint.
- `bmad-prd` (update) — on a phase project (`downstream: prd`), when ready specs are grouped into the next phase PRD.

**The dashboard page.** After the last approved action of a run, rebuild and republish the dashboard
once (`ba-dashboard` → *Publish*: check the YAML, build the map page, publish it to
`tools.dashboard.url`). A project without a dashboard yet: offer to start one (`ba-dashboard` →
*Starting one*).
