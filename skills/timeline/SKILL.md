---
name: timeline
description: Build and publish a project's timeline page — the BA dashboard's features over time (areas → features → changes and bugs, each bar coloured by stage), the calls, emails, comments and client documents behind them, and three list tabs (Clarification pages, To-dos, Next meeting agenda). One page and one build for every project; only the part that reads the work tracker differs (Jira, or GitHub specs + BMAD stories). Use when the BA says "update the timeline", "rebuild the timeline", "publish the timeline", "set up a timeline for <project>", or after a dashboard update when the project has a timeline.
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
| `docs/BA/timeline/<project>-timeline.yaml` | The data file: `product:` settings, area `groups`, `placements`, recorded `features`, `pins`, `tags`, plus the tracker's own block |
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
```

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
image) · `portal` → clarification-page answers. One pin per day and kind; the panel shows the intake file's
people, minutes, summary, the decisions taken that day and what the call left waiting.

## Area panel

Counts **features** by stage — never commits or tickets (the client reads this page). Jira projects may add a
"See all in Jira" link (`link` on the area).

## Add a tracker

A new module `scripts/trackers/<name>.py` with `class Tracker(Base)` — the hooks and what each returns are in
`scripts/trackers/__init__.py`. `tracker: none` builds a page from the dashboard and recorded features only.
