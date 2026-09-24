---
name: 05-review-and-materialize
description: Interactive review-and-act loop. After step 4 writes the report, walk the BA through each pending block in chat, accept single or batched decisions, and carry out approved blocks immediately. You can stop and resume across runs.
---

# Step 5 — Review & Carry Out

Runs at the end of step 4 (right after the report file is written) and on re-entry from step 1 §0.5 when any report has `pending-decision` blocks. One in-progress report at a time.

## When to skip

| Mode | Behaviour |
|---|---|
| `--dry-run` | Skip the loop entirely. Report is the only output, every block stays `state: pending-decision`. |
| `--non-interactive` | Skip the prompt loop. Carry out any block already in `state: approved` (e.g. set by an external batch tool) and stop. |
| `--at-commit` | Skip — retrospective runs are read-only. |

## Picking a report

Scan `docs/BA/triage/*.md` (excluding `.processed/`). Pick the first match in this priority order:

1. **Resume** — top-level `status: pending-ba-review` (or no `status:`) AND at least one block in `state: pending-decision`. Most-recently-written wins on ties.
2. **Backwards-compat batch approval** — top-level `status: approved` AND every block still in `state: pending-decision`. Treat as "all ok" — carry out all blocks without prompting (the BA reviewed offline by deleting/editing blocks in the file, then flipped status).
3. **Mixed** — `status: approved` AND some blocks decided. Carry out blocks already in `state: approved`; leave any `pending-decision` blocks for the next interactive run.

If nothing qualifies → return.

## Block indexing

Number blocks `1..N` in document order, sweeping the report top-to-bottom across all sections (§1 contradictions → §2 borderline → §3a / §3b / §3c → §4 duplicates / in-flight / already-shipped → §5 notes). Indices are **stable across runs** — block 3 stays block 3 even after blocks 1, 2 are decided. This means resume sessions can refer to the same block numbers as the original prompt.

## The prompt

Print the chat summary (same shape as step 4 §"Hand-off to user") with each pending block prefixed by its 1-based index. Then:

```
N blocks pending decision. Decide:
  Format: <selector> <verb>[, <selector> <verb>, …]
  Verbs:    ok | edit | note | dismiss | skip
  Aliases:  y=ok, d=dismiss
  Selectors: 3 | 1-4 | 1,3,5 | all | rest
  Commands: ? (help) | list (re-show blocks) | stop (save & exit)
Decision?
```

## Parser

- Top level: split input on `, ` (comma-space) into chunks.
- Each chunk: `<selector_token> <verb_token>` separated by whitespace.
- Selector token grammar:
  - `<int>` — single block index
  - `<int>-<int>` — inclusive range
  - `<int>,<int>,...` — explicit list, **no spaces** inside
  - `all` — every block in the report
  - `rest` — every block currently in `state: pending-decision`
- Verb token: one of `ok` (alias `y`, `approve`) / `edit` / `note` / `dismiss` (alias `d`, `delete`) / `skip`.
- **Last input wins.** Walk chunks left-to-right, building a decision map. Later writes override earlier writes for the same block index. So `all ok, 3,7 dismiss` resolves to: {1,2,4,5,6,8,9 → ok; 3,7 → dismiss}.
- **Validation.** Out-of-range indices, references to already-`materialized` blocks, unknown verbs → reprompt with a one-line error. Do not partially apply.
- **Confirmation pre-apply:**
  ```
  Resolving:
    1, 2, 4, 5, 6, 8, 9 → ok
    3, 7 → dismiss
  Apply? [Y/n]
  ```
  On `Y` (or empty answer): apply. On `n`: reprompt.

## Applying decisions (Option A — act immediately)

For each decided block, in original index order:

| Verb | Effect |
|---|---|
| `ok` | Run the same carry-out logic as step 1 §0.5 for that block — spec write / Jira PATCH (with placeholder + already-applied + change-since checks) / dashboard append (with `{auto_number}` substitution + placeholder strip + duplicate-check + marker insertion on first write) / note log. On success, set `state: materialized` and `decided_at: <today>`. On Jira change-check abort, set `state: aborted-drift` and continue with the next block. |
| `edit` | Pause the loop. Print: *"Edit block N in `docs/BA/triage/<file>`, save, then type `done`."* Wait for `done`. On resume: re-read the block from disk, validate the YAML is well-formed, then prompt for the new verb (`ok` / `note` / `dismiss`) and continue. |
| `note` | Set `state: noted` + `decided_at`. Append `<block title>` to `actioned_log.notes_logged` (or the block's `todo:` field if richer text is wanted). The block stays in the report for the audit trail but no file is written. |
| `dismiss` | Remove the block from the report file. Append `<block title>` to `actioned_log.dismissed:` for the audit trail. |
| `skip` | No state change — block stays `state: pending-decision`. Will be re-prompted on the next run. |

**Saving progress:** update the report file after each batch resolves (or after each individual decision if running in safe-mode). Each block's `state:` and `decided_at:` plus the report's `actioned_log:` are kept in sync — a crash mid-loop loses at most the last batch.

## Wrap-up

When **all blocks** reach a finished state (`materialized` / `noted` / `dismissed` / `aborted-drift`):

- Flip top-level `status: actioned` (or `partially-actioned` if any `aborted-drift`).
- Set `actioned_at: <today>`.
- Move listed `intake_files_processed:` to `docs/BA/intake/.processed/`.
- Move `actioned` reports to `docs/BA/triage/.processed/`. Leave `partially-actioned` in active `docs/BA/triage/` for re-run after fixing the upstream change.

Print a 1-line summary per affected report:

> *"Actioned report 2026-05-06-triage-report.md — 5 ok (3 specs, 1 edit, 1 dashboard), 2 noted, 2 dismissed; moved 2 intake files + report to .processed/."*

## `stop` command

Skill saves current state (per-block `state:` + `decided_at:` already saved) and exits:

> *"Saved progress: Y of N decided. Run /intake-and-triage again to resume."*

No status flip — top-level `status:` stays `pending-ba-review` if any block is still `pending-decision`.

## Resume sessions

When entered with a mid-review report:

1. Print: *"Resuming `<report file>` — Y of N decided. Walking remaining blocks."*
2. Re-print the chat summary, but only for blocks in `state: pending-decision`. Indices stay stable (block 5 is still block 5 even if 1–4 are done).
3. Enter the same prompt loop.

## Backwards-compatible offline review

If the BA prefers their editor over chat:

1. They type `stop` immediately when the prompt appears.
2. They edit the report freely — delete blocks they want dismissed, edit text in any block, demote `type:` to `note` for items they want logged-only.
3. They flip top-level `status: pending-ba-review` → `status: approved` by hand.
4. Next `/intake-and-triage` invocation hits the **Backwards-compat batch approval** branch above and treats every still-`pending-decision` block as `ok`.

This keeps the today-flow working with no regression — the interactive loop is opt-in by default but skippable.
