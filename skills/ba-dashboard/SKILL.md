---
name: ba-dashboard
description: Keep the project's BA dashboard — one page, at one stable link, with two tabs. Map shows product → area (Jira component) → feature → items, each feature coloured by its stage, with its clarification page, everything waiting on someone else, the BA's to-dos and the agenda for the next client call. Board shows the same features by Jira release. The page is built from docs/BA/dashboard.yaml plus Jira and republished to the link in the project profile. Use when the BA says "update the dashboard", "show me the dashboard", "add this to the dashboard", "what's on the agenda", "where is the clarification page for…", "close that item", "sync the mind map", after a triage run, whenever a clarification page is published — and offer to start one right after a project brief is written.
---

# ba-dashboard

**One dashboard per project, at one link that never changes** (`tools.dashboard.url` in the project
profile). It is the BA's starting point: from it you reach every clarification page, and you see what is
open, on whom, for how long, and how far each feature has got.

**The page has two tabs:**

- **Map** (opens first) — product → area → feature → items. An area is a Jira component. Each bubble is
  coloured by its stage, and a parent's ring shows the mix of its children's stages.
- **Board** (`#board` opens it) — rows are Jira releases (upcoming, "Not planned yet", the last release,
  one earlier release picked from a list); columns are the same areas; one card per feature.

**Or the Timelines are the dashboard.** When the profile has `tools.dashboard.timelines` (one Timeline per
product, see *Profile settings*), the Map + Board page is no longer published: it is built only as the data
the Timelines and `portal-publish` read. The Timeline pages (the `timeline` skill) are what the BA and the
client open. Everything else here — the YAML, the commands, the checks — stays the same.

**The page is built, never hand-edited.** Its content lives in **`docs/BA/dashboard.yaml`**; Jira adds the
tickets, areas and releases. Change the YAML (by hand, or with the commands below), build, publish.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`
  (`<skills>` = the folder this skill is installed in, one level up). No passing stamp → `ba-setup check`.
- Read `tools.dashboard` from the project profile (`docs/BA/specs/.ba-profile.yml`): `file` (normally
  `docs/BA/dashboard.yaml`), `url` (the published page), `page` (`docs/BA/mind-map/mind-map.html`) and
  `map` (see *Profile settings*). No dashboard yet → see *Starting one*.

Two helper scripts, both run from the project root:

```
uv run --with pyyaml python <skills>/ba-dashboard/scripts/dashboard.py <command>   # edit and check the YAML
uv run --with pyyaml python <skills>/ba-dashboard/map/build.py [--refresh]        # build the page
```

## What goes in the YAML

| List | One entry is | Fields |
|---|---|---|
| `features` | one feature (several questions can belong to one feature) | `area` (its title — plain words), `prod`, `stage` (`design` · `spec` · `dev`), `who`, `since`, `s` (what it is), `open` (the client's open questions, one line each), `clar` (`url`, `label` — its clarification page), `refs` (spec and ticket links, HTML); optional `id` (short slug, used in links `#<id>`), `short` (the bubble's label), `tickets` (its Jira keys; an empty list = none yet), `jira_area` (its area while it has no tickets), `hot` |
| `topics` | a group of work with no feature row yet (for example "Refunds and Xero") | `id`, `title`; optional `prod`, `jira_area`, `tickets` |
| `awaiting` | something parked on someone else | `prod`, `who` (who owes the answer), `since`, `t` (title), `s` (the situation), `l` (where the answer lands), optional `feature`, `done`, `part`, `hot`; `n` is numbered automatically |
| `todos` | a next step that is on the BA | as above, without `n` |
| `agenda` | something to raise on the next client call | as above, without `n` |

- **`feature:` on an item** names the feature's or topic's `id`. That is what puts the item under its
  bubble on the map. An item without it lands in **Not linked yet** — link it when you add it.
- **A feature's tickets** are its `tickets:` list; without one, the Jira keys written anywhere in its text
  and its items' text. Write `tickets:` once a feature has real tickets — a passing mention can put a
  feature in the wrong area.
- **A feature's area** is the Jira component its tickets carry most; with no tickets, its `jira_area`;
  with neither, **No area**.
- **A feature's stage** (six, the same on every project): Concept → Spec & design → Ready for dev → In
  dev → In QA → Done. With open tickets it is the stage of the slowest one. Without tickets: `dev` → In
  dev; `spec` → Ready for dev only when its spec is `filed` or `resolved`, otherwise Spec & design;
  `design` → Concept. Tickets at To Do never make it Ready for dev while its spec is still being written.

`prod` is a product name (see *Profile settings*) or `Both`. `since` is `YYYY-MM-DD` — the page counts
the days itself; a red badge counts open client questions, an orange one items waiting over 30 days.
**Everything is plain words**: the page is read by a BA in a hurry, so a title says what the thing is,
never a code. Item text is short bullets, open question first.

## Commands (`dashboard.py`)

| To | Run |
|---|---|
| Check the YAML (and build the plain table view, `docs/BA/dashboard.html`) | `build` |
| Add an item | write it to a small YAML file (with its `feature:`), then `add awaiting --item <file>` (or `todos`, `agenda`). A title already there is skipped. |
| Mark an item answered | `close awaiting --n <N>` or `close todos --title "<exact title>"` — it stays, shown as resolved on the map |
| Point a feature at its clarification page | `set-clar --feature "<area>" --url <link> --label "<label>"`; add `--open <file>` to replace its open questions, `--new <file>` to create the row if the feature has none yet |
| See what is there | `list` |

Anything else — rewording, moving an item between lists, linking items to a feature, removing a finished
one — edit the YAML directly, then `build`.

## Bring everything the change touches in line — every update, without being asked

**The dashboard is one of four places that say where a feature stands.** If only the dashboard moves,
the others contradict it. Whenever you change a feature row or close an item, check each of these
**for that feature** and update the ones that are out of date, in the same run. Do not stop to offer
it. The BA expects it as part of "update the dashboard".

| Place | Out of date when | What to do |
|---|---|---|
| **The feature's clarification page** (`clar` on the row; `docs/BA/clarifications/<slug>-decisions.yaml`) | a question on it was answered or dropped, or a new question for the client came up | Run the `clarification-page` skill for the next round (V<n+1>). Answered questions become `decisions` (with a timeline event). New questions are added. Captions that describe the old state are rewritten, and the hero screen moves if its question has gone. Then publish it to the same link, run `set-clar` with the new label and open questions, and update its row in `docs/BA/clarifications/README.md`. |
| **The spec's status** (the spec header, and its row in the FR register) | a ticket exists but the status still says `draft` or `ready`; or the work shipped | Set it to `filed` (or `resolved`), with today's date in `updated`, in the spec and in the register. |
| **The spec's release folder** (`docs/BA/specs/<product>/<release>/`, when the profile has `release_folders: true`) | the ticket's fixVersion in Jira does not match the folder or header. Check it live: `jira search "key = <KEY>"`. | Run `jira refresh-specs --projects <KEY>=<folder>` so the folder exists. `git mv` the spec into it, and record the fixVersion in the header. Then fix every link to the old path: search for the file name across `docs/BA`. |
| **Shipped features still listed** — check on EVERY update, not only for the feature you touched | a `dev` row's ticket is Done in Jira, or the BA says it is deployed. Check every `dev` row's ticket live: `jira search "key in (<KEYS>)"` | Remove the row from `features` (keep its `id` as a topic only if open items still point at it). Set the spec to `resolved`, move it to its released folder, and fix its links. Re-open any awaiting item or to-do that waited for this release. If the Jira release is not marked released, tell the BA. |
| **The dashboard's own text** | the row's `s`, `open`, `refs`, `stage` or `tickets`, or a related awaiting/to-do item, still describes the old state | Rewrite it, close the answered items, and add a to-do for any next step that now sits on the BA (for example, a filed ticket nobody is assigned to). |

Report each one you changed. If one needs the BA's judgement, do everything else and ask about that one
alone. For example: a question you cannot word without inventing a client position.

## Publish

1. `dashboard.py build` — it checks the YAML (missing fields, an item's `feature` that no feature or
   topic has, an id used twice). Fix what it reports.
2. `map/build.py` — add **`--refresh`** when the Jira files in `docs/BA/mind-map/` are older than a day
   (needs `node` and the Jira variables `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`; the Jira scripts
   only read). It writes `docs/BA/mind-map/mind-map.html` and `docs/BA/mind-map/stages.json` (the
   clarification pages read their stage and the Back-to-the-map link from it).
3. Publish `docs/BA/mind-map/mind-map.html` **to `tools.dashboard.url`**. Leave `capabilities` out, so
   the page keeps its saved notes store, and do not use `force`. Never publish `docs/BA/dashboard.html` to
   that link — it would replace the map.
   **When the profile has `tools.dashboard.timelines`, do this instead:** for each product, build its
   Timeline (`timeline` skill → *Build*, with that product's `data` file) and publish the built page to its
   `url` (`timeline` → *Publish*). Do not publish the map page anywhere.
4. **The share pin does not move by itself** — if the page is shared, tell the BA to move it from the
   artifact's share menu.
5. If `docs/BA/dashboard-slack.yaml` exists, sync the client copy in Slack (next section).
6. When the profile has `tools.portal`, run `portal-publish dashboard` after the Slack sync — or, when it has
   `tools.dashboard.timelines`, `portal-publish timeline` (the Timelines are what the Client sees; a Dashboard
   send would put Map and Board back, so `dashboard plan` stops). It shows the
   BA what the Client will read in the Relevant Clients Portal and sends it only after a yes. If the BA
   says no, nothing is sent. A repo with two products sends each product to its own Portal project (its
   key is named in `tools.portal.products`), with one dry run and one yes or no per product.
7. Commit `dashboard.yaml`, `dashboard.html`, `dashboard-slack.yaml` and `docs/BA/mind-map/` together
   (ask before pushing).

When a clarification page's stage should change with this update, rebuild and republish that page too
(`clarification-page`) — it reads its stage from `stages.json`.

## Notes saved on the map ("sync the mind map")

A Waiting, To-do or agenda item's panel on the map has an **Update** box: a note and a "Resolved" tick.
They save in the published page's own store (collection `resolutions`) and show on the map at once. The
page cannot change the repo, so to make them stick:

1. Read the store: ArtifactData `list` on `tools.dashboard.url`, collection `resolutions`, saved to a JSON file.
   With `tools.dashboard.timelines`, read each Timeline's store instead (its `url`, same collection), one
   file per page, and run steps 2 and 3 once per file.
2. `uv run --with pyyaml python <skills>/ba-dashboard/map/sync.py <that file>`. Notes go to the front of
   the item's `s` as "UPDATE <date> — …" / "CLOSED <date> — …"; resolved items get `done: true`.
3. Delete exactly the `applied` keys from the store (ArtifactData `batch` delete). Keys under
   `not_found` (title changed, item gone) stay for a look.
4. Publish (above).

**The Client's notes from the Portal.** Client people can use the same Update box on the Portal's Map and
Board. `fetch-portal` brings their notes and ticks in as `docs/BA/portal-updates/YYYY-MM-DD-HHMM-<product>.json`,
in the same shape as the store. To sync one, skip steps 1 and 3: run step 2 with that file, then publish. Its
notes say who wrote them, so they read "UPDATE <date> — <client name>: …". Tell the BA about any `not_found`
item: the client wrote on an item whose title has changed since.

Item links: the copy icon in an item's panel copies `<Kind>: "<title>" <map>#i-<key>`. When the BA pastes
one, find the item by its title; the key is the first 12 characters of sha1("<kind>|<title>") over the
YAML items (kind `waiting` = awaiting, `todo` = todos, `agenda` = agenda).

## The client copy in Slack — when the project has one

The BA's page stays the full, internal view. A project may also give the client a **separate copy in
Slack**: two Slack Lists with only the **features in flight** and the **items waiting on the client's
side** — no to-dos, no agenda. Its settings and row ids live in **`docs/BA/dashboard-slack.yaml`**
(`channel`, `client_owners`, the two list ids). **When that file exists, sync Slack every time you publish.**

1. `slack-plan` — prints the rows to `create`, `update` (changed text) and `close` (gone from the YAML).
   An awaiting item goes to Slack only when the **first** person in its `who` is in `client_owners`;
   an item answered before it ever reached Slack is skipped; a closed one shows as **Answered**.
2. Write them with the Slack connector: `slack_add_list_record` for each `create`,
   `slack_update_list_record` (with its `record_id`) for each `update` and `close`.
3. Save what came back as `{"rows": [{"list", "key", "hash", "record_id", "closed"?}]}` and run
   `slack-ack --file <that file>`. Re-run `slack-plan` — it must show zero of everything.
   **`closed: true` is only for rows from the `close` list** (items gone from the YAML). An item marked
   answered (`done`) comes through as an `update` with Status = Answered. Ack it with its `hash`, like any
   update. Flagging it `closed` drops the hash, and the next `slack-plan` shows it again.
4. Commit `dashboard-slack.yaml` with the other files.

Per item, in `dashboard.yaml`: `client: false` keeps it out of Slack; `client_s:` replaces `s` with
wording written for the client.

## Who else writes to it

- **`clarification-page`** — every time it publishes a page, it runs `set-clar` for that feature (the
  link, the version label, the open questions), then publishes the dashboard. So a new page is findable
  from the dashboard the moment it exists.
- **`intake-and-triage`** — each approved `dashboard` action is an `add` to `awaiting`, `todos` or
  `agenda`, with `feature:` set when the item belongs to a known feature; at the end of the run it
  publishes the dashboard once.
- **`ba-spec`** — when a feature gets its ticket, it adds the key to the feature's `tickets:`.

## Profile settings

In `docs/BA/specs/.ba-profile.yml`, under `tools.dashboard`:

```yaml
dashboard:
  file: docs/BA/dashboard.yaml
  url: https://claude.ai/artifact/<id>          # the published page — one link, never changes
  page: docs/BA/mind-map/mind-map.html          # what gets published
  map:
    products: { PROJ: Product name }             # optional: Jira project -> product name as dashboard.yaml writes it
    stage_of_status:                              # optional: Jira status -> stage (concept/spec/ready/dev/qa/done)
      In Review: qa
```

**The Timelines as the dashboard** — replace `url` with one Timeline per product (the key is the product
name as `dashboard.yaml` writes it in `prod:`):

```yaml
dashboard:
  file: docs/BA/dashboard.yaml
  page: docs/BA/mind-map/mind-map.html          # still built — the data the Timelines read; never published
  timelines:
    AcmeLending: { data: docs/BA/timeline/epd-timeline.yaml, url: https://claude.ai/artifact/<id> }
    Bond Portal: { data: docs/BA/timeline/bond-portal/ip-timeline.yaml, url: https://claude.ai/artifact/<id> }
```

The clarification pages' Back button then reads "Back to the timeline" and opens the Timeline of the page's
feature's product ("Both" → the first one). Switching an existing project over: add `timelines`, remove `url`,
build the map, rebuild every clarification page (so its Back button moves), publish the Timelines, and only
then, with the BA's yes, delete the old Map + Board artifact.

Without `map.products`, the products come from the profile's `products` (`jira_project` → `name`).
Statuses not in `stage_of_status` use Jira's own groups: To Do → Ready for dev, In Progress → In dev,
Done → Done. List every status that means "being tested" as `qa`, or the map never shows In QA.

## Starting one — offer it right after the project brief

**When a project brief has just been written** (`bmad-product-brief`, or any brief the BA hands over) and
the profile has no `tools.dashboard.url`, offer to start the dashboard in the same turn: "The brief is
done — shall I start the project's dashboard from it?" It is the place every later feature, question and
clarification page hangs from, so it is best started before the first feature is specced. `ba-setup
check` also flags a project that has a brief but no dashboard.

On a yes:

1. `dashboard.py init --title "<Project> BA Dashboard" --products "<Product A>,<Product B>"` — creates an
   empty `docs/BA/dashboard.yaml`. Use the product names the profile's `products` use.
2. **Seed it from the brief.** One `features` row per feature or capability the brief names: `area` (its
   title, plain words), `id`, `prod`, `stage: design`, `who` (who asked for it), `since` (the brief's
   date), `s` (one or two lines from the brief). The brief's open questions go to `agenda` (for the
   client) or `todos` (on the BA), each with its `feature:`. Show the BA the list before writing it.
3. Fill `lede` (one paragraph: what this page is for).
4. Add `tools.dashboard` to the profile (`file`, `page`, and `map` if the Jira statuses need it).
5. `dashboard.py build`, then `map/build.py --refresh` (or without `--refresh` when there is no Jira yet —
   every feature then shows under **No area** until it has tickets or a `jira_area`).
6. Publish `docs/BA/mind-map/mind-map.html` as a **new** artifact with `capabilities: {"db": {}}` (the
   notes store). Put its link into the profile as `tools.dashboard.url`, rebuild, and publish again to that
   link (so the page knows its own link). Commit.
