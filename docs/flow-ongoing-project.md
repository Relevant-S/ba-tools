# Ongoing project — the weekly loop

What a BA does every week on a live product. The example is Acme Lending + Bond Portal, where today each
ready spec becomes a Jira ticket (`downstream: jira`). Every project is moving to **one PRD per phase**:
there, steps 7–9 are replaced by grouping the phase's ready specs into its PRD — see
[`flow-new-project.md`](flow-new-project.md), step 9. There is no living whole-system PRD: the code says how
the system works now, the specs say why.

## Steps

| # | Step | Skill | Result |
|---|---|---|---|
| 1 | A client call, Slack thread or email happens | — | — |
| 2 | Pull it in — first check there is no newer call you have missed | `fetch-fireflies`, `fetch-slack`, `fetch-gmail` | files in `docs/BA/intake/` |
| 3 | Triage: for each ask, decide — a new spec, a change to an existing ticket, a dashboard item, or a note | `intake-and-triage` | a triage report in `docs/BA/triage/`; the intake is archived |
| 4 | The dashboard is rebuilt and republished with the new items | `intake-and-triage` → `ba-dashboard` | the dashboard, same link |
| 5 | Write each new spec — thin first, then full | `ba-spec` | a spec in `docs/BA/specs/<product>/<release>/` |
| 6 | If the client will see the change: questions and any designs go on the feature's clarification page; the client answers on the call; the answers go into the spec's Decisions | `clarification-page`, then `fetch-slack` / `fetch-gmail` for pasted answers | the spec, updated |
| 7 | The ready gate, then your explicit yes | `ba-spec` | `status: ready` |
| 8 | File it: the next requirement number (new features only), commit, push (it asks), a Jira ticket with a short description and the spec link | `ba-spec` | the ticket key in the spec, `status: filed` |
| 9 | When the sprint or phase branch is cut, copy its specs onto it | by hand | the hand-off branch |
| 10 | A release ships: move its spec folder to `released/`, rebuild the release list | `jira refresh-specs` | `_releases.md` |

**Side door:** an existing Jira ticket with no proper spec → `fetch-jira-backlog` → `ba-spec`, using
its "re-create a spec already filed" path.

## Rules that hold the loop together

- **Spec before ticket.** Nothing reaches Jira without a written spec and the BA's yes.
- **Tickets are trackers.** A short description and the link to the spec, never the spec itself.
- **Every ticket has a release (fixVersion) when it is created.** `Backlog` is a release.
- **Every push is asked for.**
- **The clarification page is a surface, not the record.** Answers live in the spec's Decisions.

## Not built yet

| Gap | Today |
|---|---|
