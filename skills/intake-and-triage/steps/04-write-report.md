---
name: 04-write-report
description: Render the triage report at docs/BA/triage/YYYY-MM-DD-triage-report.md with sections for contradictions, borderline cases, items by lane (each carrying a proposed_action block), duplicates/shipped, and a state comparison summary. The report is the only file the skill writes during step 4 — carrying out the proposed_action blocks happens in step 1 §0.5 on the next invocation, after the BA flips status to approved.
---

# Step 4 — Write Triage Report

## Output path

`docs/BA/triage/YYYY-MM-DD-triage-report.md` where `YYYY-MM-DD` is today's date (or the date of the most recent intake processed if running `--at-commit`).

If a triage report already exists for that date: **append a new dated section** at the end (e.g. `## Run 2 — 14:32`) rather than overwriting. The BA may have iterated already.

## Frontmatter

```yaml
---
date: 2026-05-01
mode: dry-run                         # dry-run | live (always dry-run in MVP)
at_commit:                            # SHA if --at-commit, else empty
intake_files_processed:
  - docs/BA/intake/2026-04-30-fireflies-weekly-call.md
mcp_jira_available: true              # false if Atlassian MCP was unavailable
mcp_jira_note:                        # populated when false ("MCP timeout", "auth failed", etc.)
bmad_artefact_paths:                  # found by step 1 §2–§5; "(not found)" if missing
  prd: docs/prd.md
  architecture: docs/architecture.md
  epics: (not found)
  implementation_artifacts_dir: docs/implementation-artifacts/
  sprint_status: (not found)
  ba_specs_dir: docs/business-requirements/
  release_notes_dir: (not found)
bootstrap_actions:                    # populated only when step 1 §0 created folders
  - created: docs/BA/intake/
  - created: docs/BA/triage/
status: pending-ba-review             # pending-ba-review | approved | partially-actioned | actioned
                                      # Lifecycle: agent writes pending-ba-review.
                                      # BA reviews each `proposed_action:` block — leaves
                                      # to confirm, demotes type to "note" to defer, or
                                      # deletes the block entirely to dismiss. Then edits
                                      # frontmatter to "approved".
                                      # On next /intake-and-triage invocation, agent
                                      # carries out remaining proposed_action blocks
                                      # (write spec stubs, post JIRA edits, append
                                      # dashboard items, log notes), moves intake files
                                      # to .processed/, and flips status to "actioned"
                                      # (or "partially-actioned" if any edit aborted because
                                      # the JIRA field changed since — see step 1 §0.5).
actioned_at:                          # set by step 1 §0.5 when status flips to actioned
actioned_log:                         # set by step 1 §0.5 — what was carried out
  specs_materialized: []              # paths written
  edits_posted: []                    # JIRA-KEY:field pairs successfully patched
  edits_aborted: []                   # JIRA-KEY:field pairs where the change-check fired
  dashboard_items_written: []         # zone:title pairs appended
  notes_logged: []                    # candidate ids logged as todos
---
```

## Citing JIRA tickets

**Every JIRA ID rendered in the report or chat summary must be a markdown link to the JIRA browse URL AND include the ticket summary alongside it on first mention.** Bare IDs are unreadable and unclickable — the BA reads reports as decision aids and needs both the human-readable title and the click-through to JIRA.

- **Link format:** `[ACME-1640]({JIRA_BASE_URL}/browse/ACME-1640)` — the `JIRA_BASE_URL` is read from the project's JIRA env var. For Acme, that's `https://example.atlassian.net`. The full pattern is `https://example.atlassian.net/browse/{KEY}`.
- **In prose (first mention):** `[ACME-1640](https://example.atlassian.net/browse/ACME-1640) *(Update CreditCo report generation approach)*` — linked ID, italicised title in parens.
- **In tables / one-liners / chat summary:** `[ACME-1640](https://example.atlassian.net/browse/ACME-1640) (Update CreditCo report generation approach)` — title in parens (no italics inside table cells), trim to ~50 chars on long titles.
- **In `proposed_action: edit` blocks (YAML):** YAML inline links don't render in raw view. Keep the title as a YAML comment beside `jira_key:` (`jira_key: BOND-873   # Share certificate details - Display the list of all transactions`) and put the link in the surrounding markdown prose introducing the block.
- **Subsequent mentions in the same paragraph:** bare ID acceptable (link still preferred if easy).

When the JIRA MCP is unavailable (`mcp_jira_available: false`), prefix the bare ID with `(JIRA unreachable — title not loaded)` once per item.

## Body — sections in this order

### 1. 🔴 Contradictions (hard-block)

If any candidates carry `flags: 🔴 contradiction`, **list them first.** The report **must not be carried out downstream** until the BA resolves each one.

For each:

```markdown
#### {Candidate title}
- **Source:** {intake file}, *"{quote}"*
- **Conflicts with:** {official file + path + the conflicting statement}
- **Resolution required:** {one-line description of what the BA needs to decide}
```

If none: a single line — *"No contradictions detected this run."*

### 2. 🟡 Borderline — BA judgement

For each candidate with `flags: 🟡 ba_judgement`:

```markdown
#### {Candidate title}
- **Source:** {intake file} — *"{quote}"*
- **Detection signature:** {which rule(s) partially matched, why uncertain}
- **Prior similar decisions:** {cite from docs/BA/triage/.processed/ if any — link + outcome}
- **Skill's tentative read:** {standard / scope-change / hotfix} — 1 sentence reason
```

### 3. Items by lane

Three subsections, in this order: **scope-change → standard → hotfix**.

Each candidate carries a `proposed_action:` YAML block — the BA confirms by leaving it, demotes to `note` to defer, or deletes to dismiss. The block is the contract step 1 §0.5 reads on the next run to carry out the action. See §3.X "proposed_action templates" below.

#### 3a. Scope-change (CR — needs client re-approval checkpoint)

For each `lane: scope-change`:

```markdown
#### {Candidate title}
- **Source:** {intake file} — *"{quote}"*
- **CR rules fired:** ① ② … (with brief justification per rule)
- **Affected official files:** {paths to PRD section / Architecture / Epic / spec}
- **State comparison:** {new / duplicate / in_flight / already_shipped}

```yaml
proposed_action:
  type: note                          # CRs default to note — never auto-draft a spec under a CR;
                                      # BA hand-authors after client re-approval checkpoint
  todo: Hand-author CR spec at docs/BA/specs/{project}/{release_slug}/{slug}.md after client re-approval. Use bmad-correct-course if this modifies in-flight scope.
```
```

#### 3b. Standard (story-equivalent)

```markdown
#### {Candidate title}
- **Source:** {intake file} — *"{quote}"*
- **Lane reason:** No CR rules fired; fits existing approved scope.
- **Closest existing official file:** {epic / story / spec — path + 1-line summary}
- **State comparison:** {new / duplicate / in_flight / already_shipped}

{proposed_action: block — pick one template per §3.X}
```

#### 3c. Hotfix

```markdown
#### {Candidate title}
- **Source:** {intake file} — *"{quote}"*
- **Lane reason:** Single-field / cosmetic / quick fix — no CR ceremony.

{proposed_action: block — pick one template per §3.X}
```

### 3.X `proposed_action:` templates

Render exactly the type chosen in step 03 §E. **One block per candidate.** Field values come from the candidate's classification fields and the pre-flight pickers in step 03 §E.

**`spec` — new spec stub, in the approved template, for `ba-spec` to pick up:**

```yaml
proposed_action:
  type: spec
  path: docs/BA/specs/{project}/{release_slug}/{slug}.md
  jira_project: ACME                 # or BOND
  jira_issuetype: Task                # or Bug
  jira_fixversion: Backlog            # or release slug
  title: {Long-form sentence-case title}
  slug: {kebab-case}
  user_problem_seed: |
    {2-4 sentences synthesised from intake quote — pain, not solution}
```

**`edit` — field-level patch on an existing JIRA ticket:**

```yaml
proposed_action:
  type: edit
  jira_key: ACME-1640
  field: description                  # or summary | acceptance_criteria | fixVersion | priority
  change_kind: append                  # or replace | prepend
  current_excerpt: |
    {~300-char excerpt of the live field — input for the change-check}
  proposed_value: |
    {Append/prepend: just the new text. Replace: full new value.}
  rationale: {1 sentence — why this edit captures the intake signal}
```

**`dashboard` — append a block to a named zone.** Block shape varies by zone — see step 03 §E "Block shape per zone" for the full per-zone templates. Three forms in active use:

- **`awaiting-external-input`** — H3 with structured sub-bullets, leading H3 carries `{auto_number}` placeholder which step 1 §0.5 substitutes with `max(existing ### N.) + 1`. Sub-bullets: **Blocked on:** / **Origin:** / **Where the answer lands:** / **Source:** / **Owner:**.
- **`open-todos`** / **`next-meeting-agenda-candidates`** (plain bullet form) — single-line bullet `- **<Title>** — <description>. Source: \`<path>\`. Owner: <who>.`
- **`next-meeting-agenda-candidates`** (carry-over form) — `- **<Title>** — <description>. Reference: *<zone heading>* §<N>.` (no Source/Owner — the referenced item carries those).

```yaml
proposed_action:
  type: dashboard
  zone: awaiting-external-input        # or open-todos | next-meeting-agenda-candidates | <fresh-slug>
  block: |
    <markdown block per the per-zone template>
```

Zone slugs come from the project's `docs/BA/dashboard.md` H2 headings (slugified). Step 1 §0.5 wraps any matching H2 section in AUTO-STATUS markers on first write so later appends are safe to re-run.

**`note` — pass-through todo, no file:**

```yaml
proposed_action:
  type: note
  todo: {1 sentence describing what BA needs to clarify or who they need to ask}
```

### 4. Duplicates / in-flight / already-shipped

These candidates also carry `proposed_action:` blocks — typically `edit` (when matched to an existing JIRA ticket) or `note` (when there's nothing to write). Render with the same per-item template as §3b, but skip the lane-specific framing:

```markdown
#### {Candidate title}
- **Source:** {intake file} — *"{quote}"*
- **State comparison:** {duplicate / in_flight / already_shipped}
- **Closest existing item:** {path or JIRA ID + 1-line summary}

{proposed_action: block — usually `edit` or `note`}
```

### 5. Notes (intake content not extracted as candidates)

Pass-through items (parking-lot, out-of-scope, info-only) — short list with source and 1-line description. Captures things the BA may want to reference later without giving them ticket-track ceremony.

### 6. Summary of changes vs. project state

```markdown
- Total intake files processed: {N}
- Candidates extracted: {N}
- By lane: scope-change={N}, standard={N}, hotfix={N}, 🟡 unresolved={N}
- 🔴 Contradictions: {N}
- New: {N} · In-flight: {N} · Already shipped: {N} · Duplicates: {N}
- Proposed actions: spec={N}, edit={N}, dashboard={N}, note={N}
- Missing BMad official files: {list any of PRD / Architecture / Epics / sprint-status that weren't found}
- JIRA MCP available: {true|false}
```

## Write rules (step 4 only — report write)

Step 4 itself only writes the triage report at the path above. **No other paths are changed during step 4.**

Carrying out `proposed_action:` blocks (spec stubs, JIRA edits, dashboard appends) happens in step 1 §0.5 on the *next* invocation, after the BA flips `status: approved`. That keeps the BA's review loop separate from the writes — the report is the contract, and the contract is reviewable before any output lands.

In `--dry-run` mode (Phase A / B), step 1 §0.5 is also skipped — the report is the only output, end to end.

## Hand-off to step 5

After the report is written, **immediately invoke step 5** (`steps/05-review-and-materialize.md`) — unless `--dry-run` / `--non-interactive` / `--at-commit` is set, in which case stop here.

Step 5 is responsible for printing the structured chat summary AND walking the BA through per-block decisions. The two are unified — the chat summary doubles as the "1..N indexed list of pending blocks" that the BA picks from when entering decisions.

The chat summary format step 5 prints:

```
Triage report written: docs/BA/triage/2026-05-02-triage-report.md
N candidates · X 🔴 · Y 🟡 · proposed: spec=A, edit=B, dashboard=C, note=D

🔴 Contradictions (hard-block):
1. {Title} — {1-line: what conflicts with what}
(or: "None this run.")

📝 Spec drafts (new asks — run ba-spec on each):
2. {Title} → docs/BA/specs/{project}/{release_slug}/{slug}.md · {ACME|BOND}/{Task|Bug}/{fixVersion}
3. ...

✏️ JIRA edits (existing tickets):
4. {Title} → {JIRA-KEY}.{field} ({append|replace|prepend}) — {1-line reason}
5. ...

📌 Dashboard items:
6. {Title} → {zone} — {1-line}
7. ...

📋 Notes (todos, parked, pass-through):
8. {Title} — {1-line: what the BA needs to clarify or who to ask}
9. ...

Cross-cutting: {1-2 sentences flagging clusters or sequencing risks — only when present, otherwise skip}
```

**Rules for the summary (unchanged):**

- **Group by `proposed_action.type`** so the BA sees at a glance what files / tickets / dashboard entries will land if they approve as-is.
- **Each `spec` line shows the four pre-flight values** (path, project, issuetype, fixVersion) so the BA can spot a mis-routing without opening the report.
- **Each `edit` line shows JIRA-KEY.field and change_kind** so the BA knows the scope of impact before reading the diff.
- **Quote nothing**; the report has the quotes. The summary is a decision aid, not a recap.
- **Block indices are stable** — the number prefix is the index step 5 uses for batch decisions (`1-4 ok, 3 dismiss`). Numbering sweeps the report top-to-bottom across all sections.
- **Cross-cutting line is optional** — include only when there's a real cluster or sequencing concern (e.g. "items 1+2 share an external blocker; resolve in order").
- **Skip empty groups** — don't render a section with "None this run" except for 🔴 (contradictions warrant the explicit "clear" signal).
- **Total length: under ~25 lines** so it fits on one screen.

After the summary, step 5 prints the decision prompt (see `steps/05-review-and-materialize.md` for the prompt format and parser).

If the BA prefers offline review: they type `stop` at the prompt, edit the report file, flip `status: approved` by hand, and re-run — step 5's "Backwards-compat batch approval" branch picks it up.
