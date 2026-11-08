---
name: timeline
description: Build and publish a project's timeline page — the BA dashboard's features over time (areas → features → changes and bugs, each bar coloured by stage), the calls, emails, comments and client documents behind them, and four list tabs (Clarification pages, To-dos, Next meeting agenda, Coming up), plus planned deadlines, releases and steps after today. One page and one build for every project; only the part that reads the work tracker differs (Jira, or GitHub specs + BMAD stories). Use when the BA says "update the timeline", "rebuild the timeline", "publish the timeline", "set up a timeline for <project>", or after a dashboard update when the project has a timeline.
---

# timeline

**One page, one build, one plug-in per tracker.** The page (`template.html`) and the shared build
(`scripts/build.py`) are the same in every project. What differs — where stage dates, work items, old work,
changes and bugs come from — is a tracker plug-in in `scripts/trackers/`. The fields the page reads are
listed in `docs/timeline-data-contract.md` (ba-tools repo); the plan behind it is
`docs/timeline-shared-engine-plan.md`.

**The timeline never writes to the dashboard.** It reads `dashboard.yaml` and the dashboard's built page.

## Stage rules (every project)

| Stage | Rule |
|---|---|
| Spec & design | a spec exists |
| Ready for dev | the spec is ready — no open questions |
| In dev | the first work item (ticket or story) starts |
| In QA | every work item done, not yet on production |
| Done | on production |

Stage dates written by hand in the data file (`features:`) win over the tracker. A date the tracker works
out rather than reads is shown like any other: the chart is read in weeks and days (Vadim, 5 Nov 2026).

## Files in the project

| File | What it is |
|---|---|
| `docs/BA/timeline/<project>-timeline.yaml` | The data file: `product:` settings, area `groups`, `placements`, recorded `features`, `pins`, `tags`, `upcoming`, plus the tracker's own block |
| `docs/BA/timeline/descriptions.yaml` | Optional: 2–3 plain bullets per row that has no client text on the dashboard |
| `docs/BA/timeline/<project>-timeline.html` | The built page (publish this) |

`product:` in the data file:

```yaml
product:
  name: Acme Lending            # the page title
  dashboard: AcmeLending        # the product's name in the dashboard data
  clarifications: acme   # `product:` in docs/BA/clarifications/*-decisions.yaml
  tag_word: Release            # Release or Phase — the tag filter and row tags
  tracker: jira                # jira · github-bmad · none
  ba: Vadim                    # the BA's first name ("BA" in the dashboard means them)
  slack_prefix: acme     # optional: only Slack intake files whose channel starts with this
  summary_drop: 'investor|…'   # optional: drop pin summary lines that match (another product's talk)
  intake_skip: 'gmail-.*agreement'   # optional: leave out intake files whose name matches (another product's)
```

## Coming up (`upcoming:` in the data file)

Planned events after today: a hard deadline, a step that waits for a feature, a change with no date yet.
Add one when the BA says so in plain words ("add a deadline …", "after What3Words we need …"). Each shows
in the "Coming up" lane at the top of the chart, in the "Coming up" tab, and as a flag on the features it names.

```yaml
upcoming:
  - id: tidio-off                  # unique in the list
    title: Switch off Tidio on the website   # up to 300 characters
    kind: deadline                 # deadline · release · planned
    date: 2026-12-17               # a date, or `after:`, or neither ("No date yet")
    needs: [tidio]                 # optional: feature ids it needs — they get "Needed by 17 Dec · in N days"
    what:                          # optional, up to 20 lines: what has to happen
      - Acme Lending removes the Tidio chat from the website by 17 Dec.
    who: Acme Lending · Relevant    # optional, up to 200 characters
  - id: pips-perks-v2
    title: New Pips Perks agreement — every customer signs it
    kind: planned
    after: w3w                     # no date: comes after this feature goes live ("Then: … →" on w3w)
```

- A deadline draws a red diamond and a red dashed line down the chart; a release or planned item a blue
  diamond on its date. `after` and undated items sit in the striped "No date yet" column at the right.
- The chart runs past today to the last dated item or future release, plus 7 days (at most a year).
- Past items stay, greyed, and show "N days late"; the tab lists them under "Passed".
- The build stops with one plain line when an item names a feature that is not on the timeline, repeats an
  id, or has both `date` and `after`.
- `milestones:` is the **old name for pins**, not for these. Do not use it for planned events.
- Future Jira releases show on the chart by themselves. Use `kind: release` only for a release that is not in Jira.
- An item with `after` never passes. Remove it once it is done.

Future releases: the dashboard's unreleased releases with a date (today or later) draw as release lines too.

## Build

From the project's repo root:

```bash
python <skills>/timeline/scripts/build.py docs/BA/timeline/<project>-timeline.yaml
```

The build prints what it left out (areas not in the data file, rows without a description). Fix those in
the data file, not in the page.

## Publish

Publish the built `.html` to the project's timeline link with the Artifact tool (same link every time; omit
`capabilities` so the page keeps its `db` and `user` store). Notes, Resolved ticks and suggestions saved on the
page come back the same way as on the dashboard: read the store with ArtifactData, run the dashboard's
`sync.py` for notes and the project's `suggestions_to_intake.py` for suggestions.

## Pins (the icons on the time axis)

From the intake file names: `fireflies` `plaud` `manual` `client-call` → call · `gmail` `client-message` → email ·
`slack` `confluence` → comments · `document` → **doc** (any file the client sends: a sheet, a Doc, a PDF, an
image) · `portal` → clarification-page answers. Answers on another product's clarification page are left out. One pin per day and kind; the panel shows the intake file's
people, minutes, summary, the decisions taken that day and what the call left waiting.

## Area panel

Counts **features** by stage — never commits or tickets (the client reads this page). Jira projects may add a
"See all in Jira" link (`link` on the area).

## The two trackers

| `tracker:` | Reads | Data file blocks |
|---|---|---|
| `jira` | ticket status history and releases (JIRA_* login, else the caches next to the data file); stories created before `start` as rows of their own (`issue_types` and `until: all` widen this to every ticket not on the dashboard) | `earlier_work: {epic_areas, fallback_area, issue_types, until}`, `jira_project`, `product.work_link` |
| `github-bmad` | BA spec status (git history), BMAD stories (`sprint-status.yaml` history on `docs_ref`), the app's `dev` / `main` branches, the QA bug list | `github: {docs_ref, repo_url, spec_branch, spec_prefix, spec_areas, titles, skip, aliases, mvp, changes, doc_subject}`, `code_repo`, `code_commits`; `bug-parents.yaml` next to the data file |

Both are read only.

## Add a tracker

A new module `scripts/trackers/<name>.py` with `class Tracker(Base)` — the hooks and what each returns are in
`scripts/trackers/__init__.py`. `tracker: none` builds a page from the dashboard and recorded features only.
