---
name: 02-extract-candidates
description: Walk each intake file and extract discrete candidate items — anything client-shaped (feature / change / fix / removal / question). Multi-item input is normal; one Fireflies call commonly yields 3–6 candidates.
---

# Step 2 — Extract Candidates

For each intake file loaded in Step 1:

## A.0 Summary-first pass (Fireflies intakes)

Before scanning the body, **read only the editorial digest sections** Fireflies generates at the top of the file:

- `## Summary`
- `## Outline` (if present)
- `## Key points`
- `## Action items`
- `## Keywords` (signal only — don't extract directly)

Treat these as the candidate-extraction source. Do **not** load `## Full transcript` into context for the initial extraction pass — for a 2-hour call it's typically 90–115 KB versus 3–5 KB for the digest sections (~5% of the file), and the digest is the editorial signal Fireflies has already distilled from the verbatim sentences.

Each `## Action items` line is a strong candidate signal — they're already structured as `<Person>: <verb-phrase> (timestamp)`. Use the timestamp as the `quote` provenance handle.

**When to fall back to the full transcript:**

- A digest line is ambiguous ("Investigate the issue") and the candidate's `target_hint` cannot be inferred — grep `## Full transcript` near the cited timestamp (±60 seconds) for the surrounding spoken context.
- The diff-and-classify step (step 3) needs a verbatim quote for a contradiction or 🔴 hard-block — pull just that quote, not the whole transcript.
- The BA explicitly asks for verbatim transcript citations.

For non-Fireflies intakes (Slack threads, emails, hand-authored intake files): there's no `## Summary` block — scan the whole body. This pass applies specifically to Fireflies.

The `quote:` field per candidate (see §B) should cite either the digest line (with `(timestamp)` preserved verbatim) OR a `[grepped from transcript @ HH:MM:SS]` excerpt when fallback was needed — never paraphrase.

## A. Identify candidates

Scan the body (digest sections per §A.0; full body for non-Fireflies sources) for distinct asks. Treat each as a separate candidate. Common shapes:

| Shape | Verb | Example trigger |
|---|---|---|
| New feature | add / build / create / introduce | *"Can we add a CSV export?"* |
| Modification | change / update / make it / tweak | *"The Age field should be optional"* |
| Removal | remove / disable / drop / hide | *"Drop the old reporting page"* |
| Bug / fix | fix / broken / not working / regression | *"The login button is unresponsive on iOS"* |
| Question / clarification | how do we / what if / clarify | *"How should the agent handle empty profiles?"* |
| Decision request | should we / which / when | *"Should we ship X this release or next?"* |

A single Fireflies call commonly yields 3–6 candidates. **Do not merge them** — the comparison step in Step 3 needs each item separately to detect contradictions and individual lane assignment.

## B. Capture per candidate

| Field | What |
|---|---|
| `id` | Stable per-run handle, e.g. `2026-05-01-fireflies-weekly-1` (intake-date + source + zero-padded sequence within file) |
| `source_file` | Path of the intake file |
| `verb` | `add` / `modify` / `remove` / `fix` / `clarify` / `decide` |
| `title` | One short noun phrase (e.g. *"CSV export to dashboard"*) — no verb in the title; the verb field carries it |
| `quote` | Raw excerpt from the intake body — **no paraphrasing.** Preserves the trail back to the source |
| `target_hint` | Best guess at the affected feature / area in existing approved state — leave null if unclear |
| `participants_named` | If a stakeholder named a thing as theirs (*"Marcus wants…"*), capture the name |

## C. Things to skip

Don't extract these as candidates — note them in `notes:` for the report instead:

- **Pure pleasantries** ("thanks for the work this week").
- **BA-internal commentary** — only client-uttered asks become candidates.
- **Status updates from the team** (those go to retro / sprint-status, not triage).
- **Items already explicitly tagged** in the intake body or frontmatter as `out-of-scope` / `for-info` / `parking-lot`.

## D. When in doubt

**Lean toward extracting more rather than fewer.** The comparison step will fold duplicates and the BA can dismiss in review. Per §10 soft thresholds:

- **Missed extraction** is a hard failure mode — target ≤5%.
- **Over-extraction** is acceptable — unlimited rate (the BA filters).

## Output

A list of candidate objects added to the project context. Proceed to `steps/03-diff-and-classify.md`.
