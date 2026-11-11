---
title: One item model — every feature, change and bug is a spec, and the project is the source of truth
status: draft            # for ba-tools; agreed in principle with Vadim on 11 Nov 2026
owner: Vadim (BA)
created: 2026-11-11
applies_to: ba-tools — skills ba-spec, timeline, intake-and-triage, portal-publish (and their Portal data rules)
pilot: NWE (this repo); then Acme Lending and the Bond Portal
---

# One item model

## Why

The NWE Timeline now runs on rules that only NWE has, most of them copied by hand from the client's sheet
"Feedback after UAT":

| NWE-only rule today | Where it lives |
|---|---|
| A client item is a spec whose name starts with "TKT-" | `github.change_prefix` in `docs/BA/timeline/nwe-timeline.yaml` |
| Bug or change, from the sheet's Type column | `row_kinds:` (copied by hand, 11 Nov 2026) |
| Before / After Global, from the sheet's column | `extra_tags:` (copied by hand) |
| The parent feature of a change | `parent:` in `github.changes:`, and a second list, `bug-parents.yaml` |
| Items with no spec at all | `hand_rows:` |
| The client text and the Figma link | `docs/BA/timeline/descriptions.yaml` |
| Our own QA bugs hidden | `github.qa_bugs: false` |

None of this would work on another project, and each copied list goes stale the day the sheet changes.

## Decisions (Vadim, 11 Nov 2026)

1. **Every feature, improvement, change and bug is an item in our project.** Old and new features alike.
2. **Every item is a spec**, with a status. A small bug is an `xs` spec; the template already allows it.
3. **An item can have a parent, and can be a parent** to other items.
4. **An item from an outside source refers to it.** The sheet, Jira, an email or a call is a reference, not the
   item.
5. **The project is the source of truth.** When an outside source changes, Vadim says "check for updates", and
   the change comes in through intake and triage (or a direct update). Nothing outside writes to the Timeline.
6. **Old MVP work: one item per MVP story** — about 100 items, marked as built before the BA process.
7. **Our internal QA bugs do not become items.** They stay in the QA bug list (`docs/issues/`). Only bugs the
   client reports become items.

## The item: six new header fields and a Summary section

Everything else in the spec header stays as in `skills/ba-spec/assets/spec-template.md`.

| Field | Holds | Replaces |
|---|---|---|
| `type` | `feature` · `improvement` · `change` · `bug` | `row_kinds:`, the "TKT-" prefix rule |
| `baseline` | `true` for work built before the BA process ("first build") | the MVP-story special case in the tracker |
| `parent` | the id of one other item; its children are found by reading `parent` backwards | `parent:` in `changes:`, `bug-parents.yaml` |
| `refs` | where it came from, one line each: `{source, key, who, date, asked, url}` | `source:` in `changes:`, the row's `asked` |
| `tags` | e.g. `[BG]`; tag groups and their full names live in the project profile | `extra_tags:` |
| `figma` | the design link (the file key comes from the product's design profile) | the links in `descriptions.yaml` |

The 4–6 plain bullets the client reads are not a header field: they are the spec's `## Summary` section (see
"Settled" below). Together with `figma`, they replace `descriptions.yaml`.

Example:

```yaml
id: NWE-212
type: bug
parent: NWE-148          # the event hub
tags: [BG]
refs:
  - {source: 'Feedback after UAT', key: TKT-63, who: Sofia, date: 2026-11-07, asked: '"View all speakers" opens Page not found'}
figma: https://www.figma.com/design/<file>/?node-id=…
---

# The Info tab's "View all speakers" and agenda links open the right tab

## Summary
- The "View all speakers" and full agenda links on the event's Info tab should open the right tab.
- …
```

## Status: what we decide, then what the code shows

| Part | Statuses | Set by |
|---|---|---|
| Before build | draft → eliciting → ready → filed · parked | the BA, in the spec (as today) |
| Build | In dev → In QA → Done (Done = on production) | read from the item's work links: stories, the ticket, or `commits:` in the header (replaces `code_commits:`) |
| Closed with no code | `done` with a date (checked fixed on production), or `resolution: no-change-needed` | the BA |

Every Timeline build lists where a reference source and the code disagree, so a stale status is caught at once
(on 11 Nov, seven were found by hand).

## Ids

Every item gets the project's own id from the profile's `ids` block. An outside key ("TKT-62", a Jira key) is kept
only in `refs`, so a second sheet or tracker can never clash with our numbering.

## How outside changes come in

1. Vadim: "check the sheet" (or Jira, or an email).
2. A fetch step writes what changed as an intake file.
3. Triage compares it with the items and proposes: a new item, an edit to an item, or a note.
4. On approval, the specs change. The Timeline is rebuilt from the specs.

## What the Timeline becomes

- It reads only the specs. Rows are items with no parent; children come from `parent`, all on one level.
- Types, tags and Figma links come from the header; the client text from the `## Summary` section; an
  item's area from its top parent.
- The data file keeps only the page layout: area groups, areas and their order.
- Gone: `change_prefix`, `row_kinds`, `extra_tags`, `changes`, `hand_rows`, `qa_bugs`, `descriptions.yaml`,
  `bug-parents.yaml`, `code_commits`.
- The same engine works for Acme Lending and the Bond Portal: they write specs too, and Jira is linked through
  `refs` and the ticket field.

## Portal data rules (one change, before any of this goes to ba-tools)

- Allow `kind` and `asked` on a row (today only on an item under a row). Without this, every product's Timeline
  send is refused once the shared scripts are updated.
- Allow tag groups (name + short label + full name).
- Allow a `figma` link on a row and on an item.

## Moving NWE over

| What | How many | Work |
|---|---|---|
| Client items with a spec (NWE-TKT-…) | 25 | add the six header fields and a Summary section |
| Client items with no spec (today's hand rows and some dashboard rows) | about 16 | write an `xs` spec each, generated from today's Timeline data |
| Old MVP work | about 100 (one per MVP story) | generate `baseline` items; the story is the work link |
| New features (NWE-FR-…) | 55 | add `type: feature`, `parent` where they belong under another |
| Our QA bugs | 61 | none — they stay in the QA list |

Order: the Portal data rules → the header fields in the template and ba-spec → the Timeline reading specs → NWE
moved over → Acme Lending and the Bond Portal.

## Settled on 11 Nov 2026

- **Area: the area of its top parent** (Vadim). An item has no `area` of its own; it sits in the area of the item
  at the top of its parent chain, so moving a parent moves its whole tree. Only top items need a place in the
  Timeline's layout.
- **Ids: one sequence for every type, and the type is never part of the id** (BA call, Vadim left it open). A type
  can change — a reported "bug" can turn out to be a change — and the id must not. Existing ids stay as they are;
  new items continue the project's numbering from the profile's `ids` block.
- **The client summary is a section of the spec text, not a header field** (BA call). The 4–6 bullets the
  client reads go in a short section right under the title, `## Summary`, so whoever opens the spec reads them
  first and edits them with the rest of the text. The build reads that section by its heading. `figma` stays a
  header field, since it is one link.
