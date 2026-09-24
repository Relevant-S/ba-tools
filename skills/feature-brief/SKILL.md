---
name: feature-brief
description: Turn internal specs into a client-facing Feature Brief — numbered capability statements, per-section review markers, linked designs — and publish it to Confluence. Use when a spec (or a set of specs covering one feature area) needs to go to a client for review or approval, or when an approved brief must be re-rendered after the spec changes. Not for publishing a spec as-is; a spec is an internal working surface and reads as one.
---

# Feature Brief — specs → a page a client can approve

> **Where the brief sits (decided 2026-09-24).** The **clarification page** is where the client answers —
> the page the BA shares on the call and collects the answers on (`client_review` in the profile). A
> brief is how the client *sees* the settled requirements, and Figma is how they see the screens
> (`client_representations`). **Comments the client leaves on a brief are extra client input**: capture
> them and put them into the spec like any other source; questions that need an answer go on the
> clarification page.

A **spec** is where a change is elicited, argued and settled. It carries provenance, `[PROPOSED]` markers,
conflicts and superseded rules — all load-bearing, all unreadable to a client. Hand one over and you get
*"this is too hard to read and approve"*.

A **brief** is a *rendering* of one or more specs for the people who must say yes. Same facts, different
instrument.

> 🔑 **The spec is the source of truth. The brief is a rendering.**
> When they disagree, the spec wins and the brief is **re-rendered** — never patched in Confluence, or the
> two drift and you end up with two contradicting documents, which is worse than having one dense one.

---

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Use `briefs_dir`, `confluence_space`, `confluence_parent`, `figma_file`, `figma_url_slug` and `briefs` (the brief settings kept in the same profile) and `tools.confluence`.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## When to use

- A feature area's specs have reached `eliciting` or better and the client needs to review or approve them.
- A spec changed after its brief was published — re-render, don't hand-edit.
- **Not** for publishing specs themselves. If someone wants the detail, link the spec; don't flatten it.

## Prerequisites

| Needs | Where |
|---|---|
| The `confluence` skill | publishing; this skill never posts directly |
| Per-project settings | `docs/BA/specs/.ba-profile.yml` — see below |
| The specs | `docs/BA/specs/<product>/` |
| Design frame ids | the project's design registry (e.g. `figma-build-config.md`) |

```yaml
# .ba-profile.yml — the brief block
briefs_dir:        docs/BA/briefs/<product>
confluence_space:  Northwind
confluence_parent: <page id>          # the phase/release parent
figma_file:        <fileKey>
figma_url_slug:    NWE---Design-System   # the name segment in a figma.com/design/<key>/<slug> URL
briefs:                                  # one entry per brief — the mapping IS the decision
  - title:  Partner & Company experience
    file:   partner-company-experience.md
    specs:  [NWE-FR-75, NWE-FR-76, NWE-FR-122]
    page:   <page id once published>
```

---

## Step 1 — Decide the split

**One brief per feature area, not per FR.** A client thinks in *"the partner experience"* and *"running a
booth"*, not in FR-115 vs FR-117. Two to five specs per brief is normal. A spec that spans two areas
(download tracking touching both a company page and leads) is rendered into **both**, each taking the half
that belongs there — say so in each brief's footer.

## Step 2 — Read the specs, and take four things from each

1. **Rules** → become capability statements.
2. **Decisions** → the `✅ Decided <date>` markers, and the client quotes worth showing back.
3. **Open** → the "Open questions for <client>" section. Items owned by *us* do **not** go in — the client
   cannot answer them and listing them reads as indecision.
4. **Conflicts / superseded** → usually omitted, unless a rule the client previously agreed has been
   reversed. Then say so plainly, with the date.

## Step 3 — Write it

### Structure

```
# <Feature area>
   one-line italic scope note + what is on the sibling brief
   > a client quote that shows why this exists   (their words, dated, attributed)
   How to review this   (comment on a number)
---
## The key idea: <the one distinction a reader must hold>
---
## 1. <Section> — 👀 Pending review | ✅ Decided <date>
   1. A <actor> can <capability>.
   2. A <actor> cannot <capability>.
   * ✅ _Decided (<date>):_ …          (only where it adds something)
   * **Why <this way>:** …             (contested points only)
   **Designs**
                                        ← blank line, mandatory
   [Frame](url) · [Frame](url)
---
## What this does _not_ include
## Open questions for <client>
---
_Detail behind this page: specifications FR-x, FR-y._
```

### The rules that make it approvable

1. **Number capabilities continuously across the whole page.** Not per section. The client comments
   *"point 34 is wrong"*; you answer against the same number. Say so in the *How to review* line.
2. **Every line names its actor** — *a logged-off visitor*, *a Company Admin*, *NWE staff*. Never "the
   user": a capability with an unnamed actor is read as belonging to whoever is reading.
3. **One capability per line.** If it needs an "and", it is probably two.
4. **Negatives get their own numbered line.** *"A Company Admin cannot switch the Webinars tab on"* is a
   decision someone made; buried inside a sentence about what they can do, it is lost — and that is exactly
   where the disagreements are.
5. **Reasoning only on genuinely contested points** — three or four per brief. Everywhere else, state the
   decision. A brief that argues every point reads as unsettled.
6. **Never present our inference as the client's words.** If a `[PROPOSED]` or `[ASSUMPTION]` from the spec
   reaches the brief, it is labelled as ours and usually belongs in Open questions instead.
7. **No estimates. Ever.** No hours, no story points, no t-shirt sizes, no "small change".
8. **Per-section review markers** — `👀 Pending review` or `✅ Decided <date>` — so approval happens in
   pieces rather than all-or-nothing.
9. **Link the designs.** A client approves a screen far more confidently than a paragraph. Label each block
   **Designs** on its own line.
10. **Say what is not included.** The absences a reader will wonder about, each with its reason. Deferred
    work says *who* deferred it — if it was us, say so.

---

## Step 4 — Verify before publishing

Run all of these. The first two have bitten:

- [ ] **Numbering is sequential from 1** — renumber **deterministically in document order**, never by hand
      and never with a regex bump. Inserting one line by hand and shifting the rest produced duplicate
      numbers within a single edit.
- [ ] **Every `point N` cross-reference still lands on the right line** — re-check *after* renumbering.
- [ ] **No estimates** — grep for hour and point figures.
- [ ] **Every `**Designs**` label is followed by a blank line** — see the trap below.
- [ ] **No raw HTML outside code spans** — Confluence validates storage XHTML and 400s on malformed input.
- [ ] Every claim the brief makes is in a spec. If it is not, either the spec is behind or the brief is
      inventing — both are bugs.

### ⚠️ The trap: Confluence turns source newlines into hard line breaks

A browser folds a newline inside `<p>` into a space. **Confluence Cloud does not** — its storage→ADF
conversion makes each one a visible break, so a markdown file hard-wrapped at ~100 characters renders ragged
mid-sentence.

The `confluence` skill fixes this at conversion time (`collapseSourceWraps`), which has a consequence here:
**a single newline is now a space**, so a label and the thing under it must be separated by a **blank
line** or they render on one line. This is why the **Designs** label needs one.

The stored XHTML is innocent — no `<br>` in it — so this survives a dry run, a byte count and a body diff.
**Look at the rendered page.**

## Step 5 — Publish

```bash
node "<skills>/confluence/scripts/confluence.mjs" upsert "<briefs_dir>/<file>.md" \
  --space <space> --parent <parent-id> --strip-h1 \
  --title "<Feature area>" \
  --note "**DRAFT for review** — every capability is numbered; comment on a number." \
  --message "<what changed>"
```

**Title is the upsert key** — keep it identical across re-renders or you create a second page.

Record the returned page id in `.ba-profile.yml`, and in each source spec's `downstream:`. Traceability has
to work in both directions: from a spec to the page the client is reading, and back.

## Step 6 — The review loop

1. Client comments **inline** in Confluence.
2. **Capture the comments to a local markdown file BEFORE republishing** — republishing orphans inline
   anchors and the comments are lost.
3. Update the **spec** — decisions, dated and attributed, with the quote.
4. **Re-render** the brief and republish.

Never let an answer live only in the brief. The spec is what feeds the PRD.

---

## Anti-patterns

| Don't | Why |
|---|---|
| Publish the spec and call it a brief | The provenance and conflict machinery is what makes a spec unreadable — and stripping it for readability destroys the Definition-of-Ready gate |
| Edit the brief in Confluence | It is a rendering; the edit is lost on the next re-render, and the spec never learns |
| One brief per FR | The client does not think in FR numbers, and cross-cutting rules get told three times |
| List our own open items | They cannot answer them; it reads as indecision |
| Soften a reversal | If a previously-agreed rule changed, say it changed and when — they will notice, and finding it themselves costs more than telling them |
