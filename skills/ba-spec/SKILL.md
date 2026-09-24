---
name: ba-spec
description: Write one BA spec in the approved template, from a triage block, an intake, a PRD open item or a plain request, and take it through the ready gate to its hand-off — a Jira ticket or the PRD, whichever the project profile says. Walks the template as steps — load and classify, need and value, rules with the cold walk, edge cases, existing code at a named commit, conflicts/assumptions/open, write at the right size, the ready gate, and hand-off (id, ticket or PRD, write-back). Reads every project fact from docs/BA/specs/.ba-profile.yml. Use when the BA says "write a spec", "spec this", "turn this into a spec", "file this as a ticket", or when a triage `proposed_action: spec` block is approved. Not for converting old specs (convert only when reopened).
---

# BA spec

Writes one spec in the approved format and, when the BA approves, hands it off. The format lives in
**`assets/spec-template.md`** in this skill — read it at the start of every run. This skill never
restates the template; it walks it. If the template and this skill disagree, the template wins; fix
this skill.

**The template and this skill are the same in every project.** Everything that differs — products,
roles, id numbering, where specs go, Jira, code repos and branches, how the client reviews — is in the
project profile, **`docs/BA/specs/.ba-profile.yml`**. What each key means:
[`profile/README.md`](https://github.com/Relevant-S/ba-tools/blob/main/profile/README.md).

## Step 0 — Load the profile (every run)

1. **Setup check.** Run `uv run --with pyyaml python ../ba-setup/scripts/setup.py` (the `ba-setup` skill is installed
   next to this one) with `stamp-status`. If there is no passing stamp for this version, run the `ba-setup` skill in `check`
   mode first, and carry on only when nothing is ❌. This is how a new BA is sent through setup on
   their first run.
2. Read `docs/BA/specs/.ba-profile.yml`. If it is missing, stop: tell the BA to run `ba-setup project`.
   Do not guess project facts. Check `profile_version` is `2`; anything else, send the BA to
   `ba-setup project`, which upgrades it.
3. Check the project's copy of the template (`docs/BA/specs/_template.md`, if present) carries the same
   `ba_tools_version` as `assets/spec-template.md`. If not, tell the BA the project copy is out of date
   or was edited locally — the copy in this skill is the one to follow.
4. If a later step needs a key the profile does not have, ask the BA for the value and suggest adding
   it to the profile. Never fill it with a value from another project.

**How to run it:** then follow the steps in order. Each step file says what to read, what to write
into the draft, and when to stop and ask.

| Step | File | Template section |
|---|---|---|
| 1 | `steps/01-load-and-classify.md` | header (`id`, `covers`, `size`, folder) |
| 2 | `steps/02-need-and-value.md` | 1, 2 |
| 3 | `steps/03-rules-and-cold-walk.md` | 3 |
| 4 | `steps/04-edge-cases.md` | 4 |
| 5 | `steps/05-existing-code.md` | 14 |
| 6 | `steps/06-decisions-conflicts-open.md` | 5–9 (and 10–13 when their trigger applies) |
| 7 | `steps/07-write.md` | the sections the size needs |
| 8 | `steps/08-ready-gate.md` | 16 |
| 9 | `steps/09-file.md` | header (`id`, `jira_ticket`, `status: filed`) |

Steps 4 and 5 are separate on purpose: they are the two sections every earlier workflow skipped
(edge cases in 0 of 90 measured specs; code references banned in Sarah's step 6). Do not fold them into
another step.

## Hard rules (each one cost a real mistake)

1. **Plain English, and gloss every id** — every FR, ticket key, rule number and edge-case code gets a
   short name the first time it appears in a message.
2. **Never invent a client question or client wording.** A rule is tagged `[src: …]`, `[design]`,
   `[BA]` or `[PROPOSED]`. `[PROPOSED]` rules also go to section 9. Check provenance before calling
   anything "the client asked".
3. **Only questions someone else must answer go in section 9.** If the BA can decide it, decide it and
   log it in section 6 as `[BA]`.
4. **Code is read from the remote, fresh.** `git -C <repo> fetch origin` first, then read
   `origin/<code.dev_branch>` — never the local checkout. Read `origin/<code.live_branch>` too when the
   question is "what is live". A stale local ref once produced a false finding.
5. **Roles are the product's real roles** — `products[].roles.list` in the profile, with its `notes`.
   Never a role from another project, never an invented one.
6. **Spec before hand-off.** Show the spec and get an explicit yes before any Jira call or PRD edit.
7. **Tickets are trackers.** Short description + spec link (+ Figma link). Never paste the spec body.
8. **Pushing needs approval every time.** A spec link must resolve — commit and push first.

## Quick spec or change request

The spec step does not decide client scope. Before step 2, say which lane this is:

- **Quick spec** — a bug fix (restores behaviour already defined) or an internal-only change with no
  client-visible effect. No change request needed. Say so in one line under the title.
- **Change request** — anything new or different that a client or end user will see. The spec can be
  written, but it is not handed off until the client has approved it on the **clarification page**
  (`client_review` in the profile) — the page the BA shares with the client on the call and collects
  the answers on. Mark `status: eliciting` until then. The feature brief and the Figma designs
  (`client_representations`) show the client the requirements; comments left on them are extra client
  input — read them into the spec like any other source.

## Thin spec (a feature from the brief, before any design)

When the BA says "thin spec", or is breaking a project brief into features: run **step 0, step 1 and
section 1 (Need) of step 2 only**. Write the file with the header and `# Title` + `## 1. Need`,
`status: draft`, and stop. The thin spec is what the design is drawn from and what triage attaches
later call notes to. Run the full skill on the same file when the feature is picked up again.

## Re-creating a spec that is already handed off

When the spec already has a ticket or PRD entry that development has not started (Jira status
"To Do", or no story built from it):

- **Step 1** — the source is the old spec **plus** its ticket or PRD entry and the call or intake it
  came from. Re-read the source; do not trust the old spec's quotes or attributions. If work has
  started, stop and ask the BA.
- **Steps 2–8** — as normal. Rewrite in place (same path, so links keep working); the old version
  stays in git history. Keep the existing `id`, `jira_ticket`, `source_intake` and `triage_ref`.
- **Step 9** — no new ticket or id. Commit and (with approval) push. If the ticket description is out
  of date or pastes the spec, replace it with the short form — with the BA's approval, since the
  assignee reads it.

## Paths and names — all from the profile

| Thing | Where |
|---|---|
| Template | `assets/spec-template.md` (this skill) |
| Profile | `docs/BA/specs/.ba-profile.yml` |
| Next id | `ids` — `register` (read `next_free`) or `highest-existing` (scan `ids.scan`) |
| PRD | `prd.paths` |
| Specs | `docs/BA/specs/<product key>/<release-slug>/<slug>.md` when `release_folders: true` (release = a real Jira fixVersion, default `backlog`); `docs/BA/specs/<product key>/<id>-<slug>.md` when `false` |
| Jira | `jira` block and `products[].jira_project` — only when `downstream` includes `jira` |
| Code | `code.repos`, `code.dev_branch`, `code.live_branch` |
| Spec link | `<spec_links.repo_url>/blob/<spec_links.branch>/<path>` |
