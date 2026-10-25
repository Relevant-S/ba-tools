# Step 9 — Hand it off

Only after the BA's explicit yes in step 8. The profile's `downstream` says where the spec goes:
`jira` (a ticket that links the spec), `prd` (the PRD, then epics and stories), or both.

**1. Record the id** (new capability only). Re-check the next free id the same way as step 1 —
someone may have taken it since. If it moved, take the new one and update the spec's `id`.
With `ids.source: register`, add the row to `ids.register` (id, product, spec link, status, proposed
FR text) and bump `next_free`. With `highest-existing` there is nothing else to write — the spec itself
now holds the number.

**2. Commit, then push.** Anything that links to the spec needs the link to resolve. Commit the spec
(and the register, if any). **Ask before pushing** — every push needs the BA's approval.

**3a. When `downstream` includes `jira` — create the ticket** (Atlassian connector `createJiraIssue`,
cloudId = `jira.site`):

| Field | Value |
|---|---|
| Project | the product's `jira_project` |
| Type | `jira_issuetype` — `jira.default_issuetype` unless the spec says otherwise; Bug only for a true regression |
| Summary | the spec title, plain words |
| Description | written from **`assets/ticket-template.md`**: what and why, where, what changes, how to test (test data, numbered steps with expected results, regression), known limits, then the spec link and the Figma link. Plain words — developers read it as the feature's summary, manual QA test from it. **Never the spec body.** Markdown, `contentFormat: markdown`. |
| fixVersions | `[{name: <jira_fixversion>}]` — must match a real version name exactly |
| priority | `{name: <jira_priority>}` — one of `jira.priorities` |

Before creating it, read the *How to test* part as a tester: every record under *Before you start*
must be something they can actually create the way it says. Check the code when unsure.

Then **check it landed**: search the new key and confirm fixVersion and priority are set (the create
response does not show them). Write back `jira_ticket: <KEY>` in the spec header.

**3b. When `downstream` includes `prd` — hand it to the PRD.** Tell the BA the spec is ready for the
next PRD update, and which PRD (`prd.paths`) and phase (`downstream: [prd:<phase>]`) it belongs to.
Do not edit the PRD from this step — the PRD is updated through `bmad-prd` (update intent), with
this spec as the change signal.

**4. Write back.** In the spec header: `status: filed`. If the spec came from a PRD open item, add the
ticket key or spec id to that line in the PRD. If the feature has a row on the dashboard
(`docs/BA/dashboard.yaml`), add the new key to its `tickets:` list, so the dashboard's map and board place
it by its tickets, then publish the dashboard (`ba-dashboard`). Commit. Ask before pushing.

**5. Report to the BA** with the key as a link and its summary, for example
`[KEY-123](https://<jira.site>/browse/KEY-123) (short summary) — Critical, Backlog`, or with the spec
path and the PRD it is waiting for.
