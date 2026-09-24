# New project — from the brief to PRD Phase 1, and every phase after

**Our flow is not BMad's.** BMad goes *brief → PRD → UX → architecture → epics and stories → build*,
writing the whole PRD up front. We go feature by feature: each feature is designed and agreed with the
client first, and the agreed features are then grouped into a PRD, one phase at a time.

```
Brief ─► feature list ─► per feature:  thin spec ─► design ⇄ client ─► full spec ⇄ client ─► ready
                                                  (skip design when there are no screens)
        ready specs ─► PRD Phase N ─► architecture ─► epics and stories ─► build ─► next phase
```

## Steps

| # | Step | BMad or ours | Skill | Result |
|---|---|---|---|---|
| 0 | Set up the project: its profile, tool areas, BA folders — and the design system: a stock kit plus the client's brand | ours | `ba-setup project`, `ba-setup design` | `docs/BA/specs/.ba-profile.yml`, `docs/BA/…` folders |
| 1 | Collect the first inputs: kick-off calls, the client's documents, email | ours | `fetch-fireflies`, `fetch-gmail`, `fetch-slack` | files in `docs/BA/intake/` |
| 2 | *(optional)* Research the market or domain, or stress-test the idea | BMad | `bmad-deep-recon`, `bmad-forge-idea`, `bmad-prfaq` | research notes |
| 3 | Project brief | BMad | `bmad-product-brief` | the brief |
| 4 | Break the brief into features; write a **thin spec** for each — the need and the outcome only | ours | `ba-spec` (stops after the need) | one `draft` spec per feature |
| 5 | **Per feature — design**, when it has screens: draw it, show it, change it | ours | `figma-build` (concept mode) | a concept page in the product's Figma file |
| 6 | **Per feature — client review**: questions and the designs go on the feature's clarification page; the client answers on the call | ours | clarification page | answers, pasted back |
| 7 | **Per feature — full spec**: rules, edge cases, code check, decisions, open questions | ours | `ba-spec` | spec at `eliciting` |
| 8 | Repeat 5–7 until nothing is open; the ready gate | ours | `ba-spec` | spec at `ready` |
| 9 | Group the ready specs into **PRD Phase N** — one PRD document per phase | ours, then BMad | *(the grouping step is not built yet)* → `bmad-prd` | the phase PRD |
| 10 | Check the phase PRD | BMad | `bmad-prd` (validate) | a findings report |
| 11 | Hand the phase to development | BMad (the dev team leads) | `bmad-architecture` → `bmad-create-epics-and-stories` → `bmad-sprint-planning` | architecture, epics and stories, a readiness verdict |
| 12 | Next phase — back to step 4 with the features left, and anything new from calls | ours | `intake-and-triage` from here on | — |

## How the client takes part

- **The clarification page is where the client answers.** One page per feature, shared on the call,
  answers collected on it and pasted back into the spec.
- **The feature brief and the Figma designs are how the client sees the requirements.** Comments the
  client leaves on either are extra input — read them into the spec like any other source.
- A spec never reaches the PRD while the client still has an open question on it.

## Notes

- **Why a thin spec first:** the design needs a brief, and triage needs somewhere to attach what the
  next call says about the feature.
- **Features without screens** — permissions, reports, calculations — skip step 5 and go straight
  to the full spec.
- **BMad's UX step** (`bmad-ux`) is mostly not needed: design happens per feature in Figma. Use it at
  most once at the start, for the overall look and navigation.
- **Triage starts once there are specs to compare against** (after step 4). Before that, call notes go
  straight into the brief.
- **`bmad-spec` is not `ba-spec`.** BMad's is a contract for developers; ours is the BA spec. Use ours.

## Not built yet

| Gap | Today |
|---|---|
| The step that groups ready specs into a phase PRD — pick them, check them against each other, carry any accepted open items into the PRD | done by hand, then `bmad-prd` |
| Clarification pages as a ba-tools skill | a generator and a README in the Acme Lending repo (`docs/BA/clarifications/`) |
| Reading Figma and Confluence comments as intake | by hand |
