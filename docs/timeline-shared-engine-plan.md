# One timeline for every project — plan

*5 Nov 2026 · Vadim (BA) with Claude · status: plan agreed, step 1 agreed, step 2 done (`skills/timeline/template.html`, checked with both projects' data on 5 Nov)*

## The problem

The dashboard is now the **Timeline** page: four tabs (Timeline, Clarification pages, To-dos, Next meeting
agenda) over a Gantt chart of areas → features → changes and bugs. Two projects have it:

| | Acme Lending (acme-docs) | NWE (northwind/docs) |
|---|---|---|
| Page | `docs/BA/timeline/` · [artifact](https://claude.ai/artifact/ExampleTimelinePage01) | `docs/BA/timeline/` · [artifact](https://claude.ai/artifact/ExampleTimelinePage02) |
| Where work is tracked | **Jira** | **GitHub**: BA specs, BMAD stories, the app's `dev` / `main` branches |

They are two copies. A fix in one does not reach the other (the four tabs were copied across by hand).
Every new project would mean a third copy.

## The idea

**One page and one build, shared through ba-tools. Only the part that reads the work tracker differs: one
plug-in per tracker.**

```
project profile ──► shared build ──► one data file (the contract) ──► one page
                       │
                       ├─ shared: dashboard data, pins (intake), clarification pages,
                       │          to-dos, agenda, descriptions, suggestions
                       └─ plug-in: jira  |  github-bmad      (picked in the project profile)
```

### What every plug-in answers

1. **Work items per feature** — which tickets or stories belong to it, and for each: when it started, when
   it was done, and whether (and when) it reached production.
2. **Old work** — what was built before the timeline starts (old Jira stories; MVP stories and specs).
3. **Changes and bugs** — rows under a feature (hand-recorded; change specs; the QA bug list).
4. **Tags** — releases (Jira) or phases (BMAD).
5. **Releases** — the dashed lines on the chart.

### One set of stage rules for both

| Stage | Rule | Jira signal | GitHub + BMAD signal |
|---|---|---|---|
| Spec | a spec exists | dashboard / spec | the BA spec file exists |
| Ready | the spec is ready | dashboard / ticket created | the spec's `status: ready` |
| In dev | the first work item starts | ticket moves to In progress | story moves to in-progress |
| In QA | every work item done, not yet on production | ticket in Testing / Done | story done and its code on `dev` |
| Done | on production | ticket Done (or its release date) | the code is on `main` |

Some dates are worked out rather than read (NWE: stories with no app commit). The page does not mark them: the chart is read in weeks and days (Vadim, 5 Nov).

### What is the same in every project (moves into the shared build)

- Features, to-dos, agenda and areas from the BA dashboard.
- **Pins** from intake files: call, email, comments (Slack/Confluence/Figma), **doc** (any file the client
  sends — a sheet, a Doc, a PDF, an image), clarification-page answers, suggestions.
- The Clarification pages tab; the descriptions file; the Update box and suggestions store.
- **Area panels count features** by stage — not commits or tickets (the client reads this page).

## Steps

| # | Step | Size |
|---|---|---|
| 1 | **Agree the data file** — every field, what it means, which plug-in fills it. Draft: [timeline-data-contract.md](timeline-data-contract.md) | small, careful |
| 2 | **One page** — the Acme Lending template with nothing project-specific left; project words (product name, "Release" or "Phase") come from the data | medium |
| 3 | **Shared build in ba-tools** — a `timeline` skill: `build.py` (shared part) + `trackers/jira.py` + `trackers/github_bmad.py` | medium |
| 4 | **The two plug-ins** — move the working code: Jira from the Acme Lending build, GitHub + BMAD from NWE's `github_stages.py` | medium, mostly moving |
| 5 | **Switch Acme Lending** — build from the skill, compare the data with today's page row by row, publish to the same link | small |
| 6 | **Switch NWE** the same way, then delete both old copies | small |

Each project keeps its own timeline data file (areas, epic → area maps, change and bug placements). The
project profile gets a `timeline:` block: the tracker, the data file and the artifact link.

## Risks

- **QA means different things** — a real Jira status vs. "done but not on `main` yet". Close enough at the chart's scale of weeks and days.
- **Guessed placements** (MVP areas, changes, bugs) — one way to mark them on the page for every project.
- **The data file becomes a contract** — a change to it means both plug-ins. It is also what the Client
  Portal's Timeline page will read, so it is worth settling now.
- **No break on switch-over** — both artifacts keep their links; nothing is published until the new build
  matches today's page.

## Not in this plan

- The Client Portal's Timeline, To-dos and Agenda pages (Vadim plans those after this).
- Retiring the old Map/Board dashboard (after the Portal has the Timeline).
