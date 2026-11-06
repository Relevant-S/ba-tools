# Timeline data file — draft contract (step 1)

*5 Nov 2026 · draft for Vadim's review · part of [the shared timeline plan](timeline-shared-engine-plan.md)*

The page reads **one JSON object** (`DATA`), built by the shared build and a tracker plug-in. This file says
what each field is, and **who fills it**: **S** = the shared build (the same in every project), **P** = the
tracker plug-in (Jira or GitHub + BMAD), **C** = the project's own timeline data file.

Today's two pages use slightly different fields for the same thing. The last column says what each replaces,
so nothing is lost in the move.

## The whole file

| Field | Type | What it is | Who | Replaces today |
|---|---|---|---|---|
| `product` | object | The product — see below | C | `project`, `tagLabel`, `jira` |
| `today` | date | The build day | S | same |
| `start` | date | Where the chart starts by default (the first intake) | C | same |
| `from` | date or null | The earliest feature start, used when "Hide done" is off | S | same |
| `built` | text | "5 Nov 2026, 17:40" for the footer | S | same |
| `groups` | list | Area groups → areas → features (the rows) | S + P | same |
| `pins` | list | Calls, emails, comments, docs, page answers, suggestions | S | `milestones` |
| `releases` | list | `{name, date}` — dashed lines on the chart | P | same |
| `pages` | list | The Clarification pages tab | S | same |
| `dashboardUrl` | url | Item links ("copy link") point here | C | `mapUrl` |

Dropped: `realNames` (the footer names no features any more), `prodDay` (not shown).

### `product`

| Field | Example | What it is |
|---|---|---|
| `name` | "Acme Lending", "NWE" | Title, tab text, "Every clarification page for …" |
| `tagWord` | "Release", "Phase" | The filter and the row tags |
| `workLink` | `https://example.atlassian.net/browse/` · `https://github.com/northwind/docs/blob/main/` | Base link for a work item's id |
| `tracker` | "jira", "github-bmad" | Which plug-in built it (shown in the footer) |

## A feature (one row)

| Field | Type | What it is | Who | Replaces today |
|---|---|---|---|---|
| `id` | text | Dashboard id, spec id (`fr75`) or story id (`mvp-2-1-…`) | S/P | same |
| `label` | text | The row name | S/P | same |
| `stage` | stage | Where it is now | S/P | same |
| `stages` | list | `{stage, from}` — the bar | P | same |
| `since` | date | When the dashboard first lists it | S | same |
| `doneDate` | date | When it reached Done | P | same |
| `origin` | text | **dashboard** · **spec** (a spec not on the dashboard) · **old-work** (an old Jira story or MVP story) | S/P | `fromSpec`, `earlier`, `mvpStory` |
| `basis` | text | Where the stage dates come from: **recorded** (by hand) · **tracker** · **code** (commit list) · **none** (faded bar) | S/P | `real`, `fromJira`, `fromCode` |
| `basisNote` | text | One line for the panel: "Story 2.1 of the MVP", "A Jira story in the epic …" | P | `mvpStory`, `epic` notes |
| `desc` | text | The dashboard's client text | S | same |
| `about` | list of text | 2–3 plain bullets when there is no `desc` | C (descriptions file) | same |
| `clar` · `clarLabel` | url · text | The clarification page button — **only a claude.ai artifact link** | S | same |
| `openQ` | list of text | Open questions | S | same |
| `todos` | list | To-dos, waiting items, agenda items (as today) | S | same |
| `who` | list of text | Who asked for it | S | same |
| `askedIn` · `askedBy` | pin id · text | Where it was first asked | C | same |
| `tags` | list of text | Releases or phases | P/C | same |
| `work` | list | `{id, title, status, url}` — the tickets or stories behind it | P | `tickets` |
| `guess` | bool | Placed in this area by guess (`*` on the page) | S/C | same |
| `changes` | feature id | For a change's own row: the feature it changes | C | same |
| `requests` | list | Changes and bugs under it — see below | P/C | same |

Dropped: `gh` (the "Spec and build" panel was replaced by `about`), `newRound` (folded into `basisNote`),
`startedBefore` (folded into `askedIn`).

## A change or bug (a row under a feature)

| Field | Type | What it is | Replaces today |
|---|---|---|---|
| `id` | text | `chg-tkt52`, `bug-093`, `q1` | same |
| `kind` | text | **sub-feature** · **change** · **improvement** · **bug** | same |
| `title` | text | Plain words | same |
| `stages` | list | As for a feature | same |
| `askedIn` · `askedBy` · `asked` | pin id · text · text | Where it came from, who, and their words | same |
| `about` | list of text | Plain bullets | same |
| `note` | text | One fact line: "QA bug BUG-093 · High · found 18 Sep · fixed in app commit 2a89b06" | same |
| `self` | feature id | The change's own row, when it has one ("Open its details") | same |
| `guess` | bool | Placed under this feature by guess | same |
| `merged` · `splitOff` | date · text | When it merged into the feature / it became a feature of its own | same |
| `work` | list | As for a feature | `jira` |
| `tags` | list | Only when different from the feature's | same |

## An area and a group

| Field | What it is | Replaces today |
|---|---|---|
| group `name`, `areas` | e.g. "Getting in" | same |
| area `name`, `features` | e.g. "Sign-in" | same |
| area `link` | Optional: a "see all in Jira" link | `jira.search` |

**The area panel counts features by stage** (worked out on the page). Dropped: `jira.done/open` and `code`
counts — not useful to the client.

## A pin

| Field | What it is | Replaces today |
|---|---|---|
| `id`, `date` | `2026-10-26-email` | same |
| `kind` | **call** · **email** · **comments** · **doc** (any file the client sends) · **page** (clarification answers) · **idea** (a suggestion) | same (+ `doc`) |
| `title`, `subject` | "Email", "Re: Test & Feedback" | same |
| `people`, `staff`, `minutes` | Who took part | same |
| `summary`, `decided`, `owes` | The panel's "In short", "Decided", "To-dos from it" | same |

## Stages

`concept` · `spec` · `ready` · `dev` · `qa` · `done` · `live` (`design` is shown as `spec`). Rules: see the
plan's stage table.

## Decided (Vadim, 5 Nov)

1. **Area link** — keep the optional "see all in Jira" link (`link`). NWE has none.
2. **Side panels follow "Hide done"** — when "Hide done" is on, the side panel also hides done items: done
   work items (tickets or stories) and done changes and bugs. When it is off, the panel shows everything.
   Both projects show their `work` list this way.

3. **No mark for worked-out dates** — some dates are worked out, not read (NWE: a story with no app commit
   noted is dated from the day it was accepted). The page treats them like any other date: the chart is read in
   weeks and days, so a guess of a day or two does not matter. No `inferred` field.
