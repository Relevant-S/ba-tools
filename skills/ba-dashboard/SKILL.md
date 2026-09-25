---
name: ba-dashboard
description: Keep the project's BA dashboard — the one page, at one stable link, where a BA finds every feature in flight with its clarification page, everything waiting on someone else, their own to-dos, and the agenda for the next client call. The page is built from docs/BA/dashboard.yaml and republished to the link in the project profile. Use when the BA says "update the dashboard", "add this to the dashboard", "what's on the agenda", "where is the clarification page for…", "close that item", after a triage run, and whenever a clarification page is published.
---

# ba-dashboard

**One dashboard per project, at one link that never changes** (`tools.dashboard.url` in the project
profile). It is the BA's starting point: from it you reach every clarification page, and you see what is
open, on whom, and for how long.

**The page is built, never hand-edited.** Its content lives in **`docs/BA/dashboard.yaml`**; the page
`docs/BA/dashboard.html` is generated from it. Change the YAML (by hand, or with the commands below), build,
publish.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`
  (`<skills>` = the folder this skill is installed in, one level up). No passing stamp → `ba-setup check`.
- Read `tools.dashboard` from the project profile (`docs/BA/specs/.ba-profile.yml`): `file` (normally
  `docs/BA/dashboard.yaml`) and `url` (the published page). No dashboard yet → see *Starting one*.

The helper script — run from the project root:

```
uv run --with pyyaml python <skills>/ba-dashboard/scripts/dashboard.py <command>
```

## The four tabs, and what goes in each

| Tab | List in the YAML | One item is | Fields |
|---|---|---|---|
| **Features in flight** | `features` | one feature (several questions can belong to one feature) | `area`, `prod`, `stage` (`design` · `spec` · `dev`), `who`, `since`, `s` (what it is), `open` (the client's open questions, one line each), `clar` (`url`, `label` — its clarification page), `refs` (spec and ticket links, HTML), optional `hot` |
| **Awaiting external input** | `awaiting` | something parked on someone else | `prod`, `who` (who owes the answer), `since`, `t` (title), `s` (the situation), `l` (where the answer lands), optional `done`, `part`, `hot`; `n` is numbered automatically |
| **Open TODOs** | `todos` | a next step that is on the BA | as above, without `n` |
| **Next call agenda** | `agenda` | something to raise on the next client call | as above, without `n` |

`prod` is a product name from the YAML's `products` list, or `Both`. `since` is `YYYY-MM-DD` — the page
counts the days itself and colours anything over 30 and 90 days. **Everything is plain words**: the page
is read by a BA in a hurry, so a title says what the thing is, never a code.

## Commands

| To | Run |
|---|---|
| Build the page | `build` |
| Add an item | write it to a small YAML file, then `add awaiting --item <file>` (or `todos`, `agenda`). A title already there is skipped. |
| Mark an item answered | `close awaiting --n <N>` or `close todos --title "<exact title>"` — it stays, struck through |
| Point a feature at its clarification page | `set-clar --feature "<area>" --url <link> --label "<label>"`; add `--open <file>` to replace its open questions, `--new <file>` to create the row if the feature has none yet |
| See what is there | `list` |

Anything else — rewording, moving an item between tabs, removing a finished one — edit the YAML
directly, then `build`.

## Publish

1. `build`.
2. Publish `docs/BA/dashboard.html` as an artifact **to `tools.dashboard.url`** — the same link every
   time, so bookmarks and links from other pages keep working. Nobody hand-edits the published page, so
   publish straight over it (`force: true`); do not read it back first.
3. **The share pin does not move by itself** — if the page is shared, tell the BA to move it from the
   artifact's share menu.
4. Commit `dashboard.yaml` and `dashboard.html` together (ask before pushing).

## Who else writes to it

- **`clarification-page`** — every time it publishes a page, it runs `set-clar` for that feature (the
  link, the version label, the open questions), then `build`, then publishes the dashboard. So a new page
  is findable from the dashboard the moment it exists.
- **`intake-and-triage`** — each approved `dashboard` action is an `add` to `awaiting`, `todos` or
  `agenda`; at the end of the run it builds and publishes the dashboard once.

## Starting one

1. `init --title "<Project> BA Dashboard" --products "<Product A>,<Product B>"` — creates an empty
   `docs/BA/dashboard.yaml`.
2. Fill `lede` (one paragraph: what this page is for) and add the first items.
3. `build`, then publish as a **new** artifact. Put its link into the profile as `tools.dashboard.url`
   (and `tools.dashboard.file: docs/BA/dashboard.yaml`).
