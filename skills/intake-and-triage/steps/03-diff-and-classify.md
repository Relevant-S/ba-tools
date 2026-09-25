---
name: 03-diff-and-classify
description: For each candidate, compare against the project's approved state, apply the D-21 threshold rules to determine lane (hotfix / standard / scope-change), and flag contradictions and borderline cases for BA judgement.
---

# Step 3 — Compare and Classify

For each candidate from Step 2, perform A → B → C → D in order. Output is a structured classification each candidate carries forward to the report.

## A. State comparison (run first; informs classification)

| Check | How to detect | Output flag |
|---|---|---|
| **Already shipped** | candidate target/title matches a story file with `status: complete` in `sprint-status.yaml`, **or** appears in any `release-notes` | `state_diff: already_shipped` |
| **In flight** | matches a story `in-progress` in `sprint-status.yaml`, or a JIRA ticket with status `In Progress` | `state_diff: in_flight` |
| **In backlog** | matches an epic / story / spec / JIRA backlog item not yet started | `state_diff: duplicate` (update existing; don't create new) |
| **Contradicts approved official state** | candidate verb is `remove` or `modify` **and** target matches a feature that is approved (see §D) in PRD / Architecture / Epic / spec frontmatter | `flags: 🔴 contradiction` (hard-block on actioning report) |
| **None of the above** | nothing matched | `state_diff: new` |

## B. Lane classification — D-21 threshold rules

A candidate is **`scope-change`** (CR-equivalent, needs client re-approval checkpoint) if **any one** of ① – ⑥ fires:

| # | Rule | How to detect |
|---|---|---|
| ① | Modifies content in approved official state | candidate target appears in PRD / Architecture / Epic / spec that is approved (see §D) (D-22) |
| ② | Wholly net-new scope | target has **no match anywhere** in project context (PRD / Architecture / Epics / specs / release-notes / JIRA) |
| ③ | Removes / rolls back a previously committed feature | verb=`remove` and target matches an `approved` feature |
| ④ | Crosses architectural boundary | candidate body or title matches keyword list (D-24, growable): `auth`, `OAuth`, `integration`, `schema`, `migration`, `infrastructure`, `third-party` |
| ⑤ | Materially impacts release capacity / pushes a deadline | **defer to BA** — flag 🟡, don't decide |
| ⑥ | Changes regulatory / compliance / security posture | keyword match: `GDPR`, `CCPA`, `SOC 2`, `HIPAA`, `PCI`, `audit`, `pen-test`, etc. — defer to BA when matched (🟡) |

If **none** of ① – ⑥ fire:

| Verb pattern | Target surface | Lane |
|---|---|---|
| `fix` | single field / label / copy / color / single screen | `hotfix` |
| `add` / `modify` / `remove` / `clarify` / `decide` | anything else, scope fits existing approved frame | `standard` |

## C. Borderline cases (D-25)

If detection is uncertain, **flag 🟡 BA-judgement** with reasoning attached. Cases:

- Rule ④ keyword matched but appears in passing context (e.g. *"like our auth flow"* — analogy, not actual auth change).
- Rule ⑥ regulatory keyword matched in passing context.
- Rule ⑤ effort impact unknown (skill cannot estimate effort accurately).
- Verb is `clarify` or `decide` — not really a change request, but may turn into one.
- Multiple weak signals across rules but no single strong fire.

**Do not auto-route** when 🟡 — record `lane: ?` and let BA decide.

When flagging 🟡, **search prior triage reports** in `docs/BA/triage/.processed/` for similar prior BA decisions and cite the one(s) that match the detection signature (per D-25). Stops the BA from re-arguing the same boundary every week.

## D. Approval status for BMad official files

Rules ① and ③ only fire against content that is approved:

For BMad PRD / Architecture / Epics, the equivalent marker is to be decided when the first BMad PRD lands on this project. **MVP rule: treat any committed BMad official file as approved** for D-21 ① / ③ purposes (i.e. anything in `_bmad-output/planning-artifacts/` is official-with-an-implicit-approval). When the explicit-approval convention is decided, update D-22 in the design doc and this section.

For BA specs (`docs/BA/specs/`): **approved = `status: ready` or `status: filed`** (the approved template's statuses), or an older spec's `approval.status: approved` block. Nothing else counts.

## E. Draft a `proposed_action` per candidate

Each candidate gets one `proposed_action` block — what the BA can confirm or override on review. Pick the type from `state_diff` + `flags` + verb shape:

| Candidate shape | `proposed_action.type` | Reason |
|---|---|---|
| `state_diff: new` AND `lane != ?` AND no 🔴 / 🟡 | **`spec`** | Net-new ask, lane decided — draft a template-shaped stub for `ba-spec` to complete. |
| `state_diff: in_flight` (matched JIRA key or in-progress story) | **`edit`** | Existing ticket is being worked; capture the new signal as a field-level edit instead of a duplicate spec. |
| Candidate is parked on a third party (Sam / compliance officer / vendor / customer / a named teammate) — next move belongs to someone outside the BA | **`dashboard`** list `awaiting` | Surface every time the BA opens the dashboard so the pending counter-party stays visible between runs. |
| Candidate is a concrete BA-owned next-step (sample prep, list compilation, follow-up ping) without yet a spec or JIRA ticket | **`dashboard`** list `todos` | Tracked todo on the BA's main page. Promote to `spec` / `edit` once concrete enough. |
| Candidate is parked behind a window (after refactoring, after release N+1) and should resurface at the next recurring meeting | **`dashboard`** list `agenda` | Avoids losing the item between runs; lets the BA stage the meeting agenda. |
| `state_diff: duplicate` (matched a backlog item not yet started) | **`edit`** if a JIRA ID is matched, else **`note`** | Update the existing item rather than spawning a new one. |
| `flags: 🔴 contradiction` | **`note`** | Hard-block — needs BA resolution before any output decision; never auto-draft a spec under contradiction. |
| `flags: 🟡 ba_judgement`, lane `?`, BA needs to decide | **`dashboard`** list `todos` | The decision needs a main-page entry so it doesn't slip between runs. |
| Anything else (pure FYI, half-formed idea, info-only with no main-page value) | **`note`** | Pass-through — log only. |

**`dashboard` is the default for anything parked, awaiting, or BA-todo-shaped — not just operational signals on already-shipped features.** Reserve `note` for items that are purely informational and won't matter between runs.

### Per-type draft contents

Every drafted block carries a `state:` field — initially `pending-decision`. Step 05 (review-and-act) walks each pending block with the BA, transitioning the state to `materialized` / `noted` / `dismissed` / `aborted-drift` per the BA's decision.

**`spec`** — fields the carry-out step needs to write the stub:

```yaml
proposed_action:
  state: pending-decision     # set by step 04; resolved by step 05
  type: spec
  path: docs/BA/specs/{project}/{release_slug}/{slug}.md   # Step 1 §4 + §3 conventions
  jira_project: ACME | BOND                                 # acme → ACME, bond-portal → BOND
  jira_issuetype: Task | Bug                                # default Task; Bug only if verb=fix AND target is an existing shipped feature regression
  jira_fixversion: Backlog | <release slug if intake names one explicitly>
  title: <Candidate title — long-form, sentence case>
  slug: <kebab-case from title>
  user_problem_seed: <2-4 sentences synthesised from the intake quote — captures the pain, not the solution>
```

Pick the product (and with it `jira_project`) from the profile's `products[]`, by the surface the
candidate touches — for Acme Lending: loans, applications, OldCRM, verification → `acme` / ACME;
Bond Portal, bond-portal-app → `bond-portal` / BOND. When `downstream` has no `jira`, write
`jira_project: -`. If unclear: leave as `(needs BA decision)` and downgrade to `note`.

Pick `jira_fixversion`:
- Default to `Backlog` for new asks.
- Only set a release slug when the intake explicitly names a target release (*"this needs to land in 5.5"*).

**`edit`** — fields the carry-out step needs to call JIRA REST:

```yaml
proposed_action:
  state: pending-decision
  type: edit
  jira_key: ACME-1640
  field: description | summary | acceptance_criteria | fixVersion | priority   # one field per block; multiple edits = multiple blocks
  change_kind: append | replace | prepend
  current_excerpt: <the existing field value, autofilled from JIRA — see below; used for the change-check>
  proposed_value: |
    <The new content. For append/prepend: just the new text.
     For replace: the full new value.>
  rationale: <1 sentence — why the intake signal warrants this edit>
```

**Autofill `current_excerpt` at draft time** — never leave it as a placeholder. Run:

```sh
node <skills>/jira/scripts/jira.mjs get-field <jira_key> <field> --max 300
```

Paste the returned `excerpt` value verbatim into `current_excerpt`. The carry-out step compares this against the live ticket before applying — if the live field has changed since the report was drafted, abort that edit and re-surface in a partially-actioned report.

**Hard rule:** `current_excerpt` must contain real ticket content. Drafting an `edit` block with a placeholder (e.g. `[verify before applying]`, `[TODO: pull live]`) is forbidden — the BA can't review a diff against a placeholder, and the carry-out step will reject it. If `get-field` is unavailable (JIRA MCP / script down): downgrade the block to `proposed_action: note` with a todo for the BA to re-run when JIRA is back, rather than emitting a placeholder edit.

**`dashboard`** — one item for the project dashboard (`docs/BA/dashboard.yaml`, the `ba-dashboard`
skill). Pick the list by who has the next move:

| Candidate shape | `list` |
|---|---|
| Parked on a third party — the next move is someone else's | `awaiting` |
| A concrete next step on the BA, with no spec or ticket yet | `todos` |
| To raise or chase on the next client call | `agenda` |

```yaml
proposed_action:
  state: pending-decision
  type: dashboard
  list: awaiting            # awaiting | todos | agenda
  item:
    prod: <a product name from the dashboard's products list, or Both>
    who: <who has the next move — a person's name, or the BA>
    since: <YYYY-MM-DD — the date of the intake it came from>
    t: <title — what it is, in plain words, no codes>
    s: <1–3 sentences: the situation, and what exactly is owed>
    l: <where the answer lands — a spec, a ticket edit, or the dashboard closing it>
    hot: false              # true only for a real deadline
```

The item's `s` names its source (the intake file and date) in plain words. Never paste a quote
longer than one sentence — the report holds the quotes.

**`note`** — pass-through:

```yaml
proposed_action:
  state: pending-decision
  type: note
  todo: <1 sentence describing what the BA still needs to clarify or who they need to ask>
```

### What does NOT go in `proposed_action`

- Anything that requires invoking another skill or agent (`ba-spec`, correct-course, create-story) — those stay BA-driven downstream of the report. The `spec` action only writes a template-shaped stub for `ba-spec` to pick up; it does **not** run `ba-spec`.
- Anything that changes approved scope — that route stays via 🔴 contradiction resolution + scope-change lane + manual CR drafting.

## Output per candidate

Each candidate now carries:

| Field | Values |
|---|---|
| `lane` | `hotfix` / `standard` / `scope-change` / `?` (when 🟡) |
| `cr_rules_fired` | array of rule numbers (e.g. `[②, ④]`) — empty if not scope-change |
| `state_diff` | `new` / `duplicate` / `in_flight` / `already_shipped` |
| `flags` | array — `🔴 contradiction`, `🟡 ba_judgement`, both, or empty |
| `reasoning` | 1–2 sentences per flag and per `cr_rules_fired` entry — explicit, citable in the report |
| `closest_canonical` | path(s) to the closest matching official file (epic / story / spec / JIRA ID), or null if `state_diff: new` |
| `proposed_action` | one block per §E — `spec` / `edit` / `dashboard` / `note` with the type-specific fields |

Proceed to `steps/04-write-report.md`.
