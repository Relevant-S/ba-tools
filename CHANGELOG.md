# Changelog

## Unreleased

- **`portal-publish` contract 1.4.0** (tag `portal-contract-1.4.0`, Stories 3.11 and 4.11).
  - `dashboard/2` gains five optional fields, so the Portal can copy the BA page: an Item's **`hot`** (yes/no;
    missing = no), a Feature's **`stage_why`** (≤ 400, the BA page's "why this stage" line, word for word) and
    **`area_how`** (≤ 200, how it was placed in its area), and an open ticket's **`updated`** (a date or a UTC
    time; only for the order), and an area's Jira **`search`** link ("All its tickets in Jira ↗"). A send
    without them still passes. `dashboard/1` is unchanged.
  - New **`answers/2`** (`answers-2.schema.json`): `answers/1` plus a required `updates` list, the Client's saves
    on Waiting and agenda Items (`id`, `sent_at`, `person`, `item {key, kind, title}`, `note` or null,
    `resolved`). `item.key` is the BA page's key, sha1("<kind>|<title>"). A batch holds at least one Answer or
    one update; with nothing to hand out both lists are empty. One ack confirms both.
  - New **`reserve-request/1`** (`reserve-request-1.schema.json`): the optional body of
    `POST /api/v1/answers/reserve`, `{ "accept": [...] }`. Without `answers/2` in it the Portal replies
    `answers/1` as before and the updates wait.
  - `index.json` lists both new schemas; `contract_folder` is `1.4.0`. New fixtures: `dashboard-2-with-1-4-fields`,
    `answers-2-batch`, `answers-2-updates-only`, `answers-2-nothing-to-fetch`, `reserve-request-1`; invalid cases
    `v2-hot-not-yes-no`, `v2-stage-why-too-long`, `v2-area-how-empty`, `v2-ticket-updated-not-utc`, nine
    `answers2-…` cases and four `reserve-request-…` cases. No new named check.
- **`portal-publish dashboard` sends the 1.4.0 fields** when the BA page's data has them: `hot` from the item's
  `hot:`, `stage_why` built exactly as the page's `whyText(f)` (a test runs the page's own code in node to
  compare), `area_how` from the bubble's `areaHow`, and `updated` on open tickets from `areas.json` (only a real
  date or UTC time), and the area's Jira `search` link (only an `https://` link). Nothing is guessed: a page built by an older `build.py` sends none of them.
- **`fetch-portal` brings in the Client's updates on dashboard items** (Story 4.11). It reserves with
  `{"accept": ["answers/1", "answers/2"]}`. An `answers/2` batch with updates gives one file per product,
  `docs/BA/portal-updates/YYYY-MM-DD-HHMM-<product>.json`, in the BA page's `resolutions` store shape (one entry
  per item key; `resolved` from the latest save; notes oldest first with `by`, the client person; `updatedAt`).
  It goes through the same `.tmp`, marker and ack steps as the intake files (the marker's third line counts the
  updates). The summary says "N updates on M items" and tells the BA to run "sync the mind map" with the file.
  An `answers/1` reply (an older Portal) works as before.
- **`ba-dashboard` `map/sync.py`** takes that file as it is. A note with `by` reads
  "UPDATE <date> — <by>: <note>." (and "CLOSED …" the same way). Syncing the same file twice adds nothing; an item unticked again (`resolved: false`) loses `done` and comes back. The BA page's own store files work as before.

- **`portal-publish` and `fetch-portal` work per product; the Dashboard send lists its pages** (Story 4.10).
  - **Which pages:** a page is a `docs/BA/clarifications/*.yaml` whose `slug:` is its file name (`<slug>.yaml` or
    `<slug>-decisions.yaml`) and that has a `store_key:`. With two or more products, a page goes with the `prod`
    of every Feature in `docs/BA/dashboard.yaml` whose `clar.url` is its `url:` ("Both" = every product); a page
    no Feature links goes with the first product in `tools.portal.products`, with a warning. Links match as the
    Portal matches them (trimmed, a trailing `/` dropped; `ba-dashboard`'s map does the same now). A page linked
    only by Features with an unknown `prod`, a YAML that is not UTF-8, or a YAML with no readable `slug:` line
    (or, read line by line, a `slug:` that is not its file name) stop the run (a page left off the list would be
    removed). `<slug>.yaml` beside `<slug>-decisions.yaml` with one slug: `-decisions` is used, with a warning. A
    slug that breaks the slug rule is skipped with a warning.
  - **`dashboard plan`:** each product's `dashboard/2` payload now carries `clarification_pages` (its pages'
    slugs, sorted). The dry-run list ends with `These pages will be removed from the Portal project "<name>":
    <title> (<slug>), …` when the Portal would hide any (`pages_removed`); `dashboard send` reports them. A
    product with no pages gets a warning: the send would remove every page in its project.
  - **`page <slug>`:** one dry run per Portal project of the page's products, each with that product's key; the
    view starts with `<product> → Portal project "<name>"`; one payload file and one yes/no per project; a
    refusal from any project stops the whole plan and keeps no payload. `--product "<name>"` limits it to one
    product. The payload file names the product and its `.env` variable (never the key); `page send` reads the
    key from that variable, stops if it is gone or no longer that product's, and with two or more products asks
    the Portal again which project the key opens. Two keys opening one project stop a "Both" page. The old
    "every page goes to the first product's Portal project" warning is gone.
  - **`fetch-portal`:** fetches from every product's project, in `tools.portal.products` order, one key at a
    time, after `GET /status` names each key's project (two keys opening one project stop the run). One
    product's failure does not stop the others; the result has `products` and is `ok: false` if any failed. The
    `.complete` marker also names the `.env` variable, so a leftover is acked in its own project (an older marker
    uses `PORTAL_PUBLISH_KEY` if `.env` has it, else its files are left alone). With two or more products each intake file has a
    `product: '<name>'` header line, and the summary names the product.
  - **One settings module:** `portal-publish/targets.py` turns the profile and `.env` into
    `[(product, .env variable, key)]`; `publish.py` imports it, `fetch-portal` and `ba-setup check` load it.
    `ba-setup check` shows one row per Portal product key (in `.env`, or missing). One product works as before,
    plus the page list.

- **`portal-publish` contract 1.3.0** (tag `portal-contract-1.3.0`, Story 4.9). `dashboard/2` gains an optional
  **`clarification_pages`**: the slugs of every Clarification page now in the repo that belongs to this Portal
  project (at most 1,000, each following the page `slug` rule, `portal`). The Portal hides the project's other
  pages from the Client at once and deletes their data once their Answers are fetched; a missing field touches no
  page, so an older ba-tools changes nothing. New named check `unique_page_slug` (in `checks.py` and
  `checks.md`). The Dashboard form of `publish-reply/1` gains an optional **`pages_removed`** (`{slug, title}`,
  for the BA): the pages a send hides, filled on dry runs too. `dashboard/1` is unchanged. New fixtures:
  `dashboard-2-with-pages`, two Dashboard replies with `pages_removed`, the invalid cases
  `v2-duplicate-page-slug`, `v2-bad-page-slug` and `v2-too-many-pages`, and the broken replies
  `reply-pages-removed-without-title` and `reply-page-with-pages-removed`. The skill does not send the list yet:
  that comes with Story 4.10.

- **`portal-publish dashboard` sends `dashboard/2`, one Portal project per product** (Story 3.8). The payload is
  built from the BA page's own data (`const DATA` in `docs/BA/mind-map/mind-map.html`) and holds, per product,
  the rows of that product and the rows marked "Both": areas (quiet ones flagged, "No area" and "Not linked
  yet" marked), each area's Jira facts and its first 5 open tickets in the BA page's order, Features (with
  their area, answered questions, done date and tickets), Map topics, Waiting and agenda Items (an Item on no
  Feature now goes under its topic, or "Not linked yet"), releases with dates, and every Board card with its
  tickets. `jira_base` comes from the first area's Jira link, else the profile's `jira.site`. HTML entities in
  Jira text (`&amp;`) are turned back into characters. The release-name cut at 100 characters is gone: names
  are sent whole, and a name over Jira's 255 stops the run, naming `releases[i].name`. A map "feature" card of a
  topic goes as an `other` card; a card in another product's release is left out with a warning (the BA page
  does not show it on that product's Board). A repo with two or more products needs `tools.portal.products` in
  the profile — product name → the `.env` variable that holds that Portal project's key; a missing entry or
  key stops the run before anything is sent, naming it. A repo with one product still uses
  `PORTAL_PUBLISH_KEY`. `dashboard plan` checks every product's payload first, then per product asks the Portal
  which project the key opens (`GET /status`), sends a dry run and prints the list, starting with
  `<product> → Portal project "<name>"` and with one Board line instead of ticket lists; the BA says yes or no
  per product (`dashboard send` / `discard` per payload file). `--product "<name>"` plans one product.
  The local body limit is now 5 MB. Page sends and `fetch-portal` use the first product's key until Story 4.10.
  `ba-setup project` asks for one key per product when the repo has several.
  Two products never share a Portal project: two products naming the same `.env` variable, or two keys that
  open the same Portal project, stop `dashboard plan` before anything is sent; `dashboard send` asks the Portal
  again which project the key opens and stops (keeping the payload file) if it is not the one `plan` showed;
  with two or more products, `page plan` names the Portal project the page goes to (`Goes to Portal project
  "<name>"`, first line of `client_view`, plus a warning). Contract docs only: an area's Jira `open` count
  includes the tickets counted in `in_progress` (no schema rule changed).

- **`portal-publish` contract 1.2.0** (tag `portal-contract-1.2.0`). Adds **`dashboard/2`**
  (`dashboard-2.schema.json` and its readable twin `dashboard-2.md`): the whole BA dashboard of one product,
  shaped like the BA page's own data — `jira_base`, areas with their Jira facts and up to 20 open tickets,
  Features, Map topics, Items (with `who`, `since` and `kind`, now shown), releases with dates, and Board cards
  (Feature, epic and other) with their tickets. One send is one product: there is no product field. Limits come
  from Jira (255 for names and summaries) or are at least twice the real Acme Lending values. `jira_base` must
  be an `https://` link. The Item key is `sha1("<kind>|<parent>|<title>")` (first 12 hex), so same-title
  Items under two parents do not clash. New named checks `unique_area_id`, `unique_topic_id` (a topic may not
  take a Feature's id either), `unique_card_id`, `unique_release_name`, `unique_special`,
  `unique_ticket_in_list` (every ticket list), `known_area`, `known_parent`, `known_card_feature`,
  `known_release`, `card_kind_fields` and `answered_in_range`, in `checks.py` and `checks.md`. Text copied
  from Jira is not checked for HTML entities. `publish-reply/1` now takes either Client view (`client_dashboard_1` or
  `client_dashboard_2`) and optional `areas`, `topics`, `cards` and `tickets` counts. `index.json` accepts
  `dashboard/1`, `dashboard/2` and `clarification/1`. A missing `contract` is now checked with the oldest
  accepted version, so adding `dashboard/2` changed nothing for it. New fixtures: `dashboard-2-small`, a
  synthetic `dashboard-2-real-size` (48 areas, 436 cards, 2,042 tickets; no client text), a `dashboard/2` dry-run
  reply and 34 `v2-…` invalid cases; the `version-not-accepted` case now sends `dashboard/3`. The skill still
  sends `dashboard/1`; sending `dashboard/2` comes with Story 3.8.

- **`fetch-portal`** — new skill: brings the Client's Answers from the Relevant Clients Portal into
  `docs/BA/intake/`, one file per Clarification page (`YYYY-MM-DD-HHMM-portal-<slug>.md`, `source: portal`), for
  `/intake-and-triage`. `fetch.py` reserves a batch (`POST /api/v1/answers/reserve`), writes the files under a
  `.tmp` name, acks (`POST /api/v1/answers/ack`, 3 tries) and only then renames them; leftover `.tmp` files from an
  earlier run are acked (or deleted) first. Same settings as `portal-publish` (`tools.portal.url`, `.env` key);
  every reply is checked with `portal-publish/checks.py` and its contract (`answers/1`, `ack/1`), never a copy.
  `intake-and-triage` and `clarification-page` now point to it on projects with `tools.portal`. Dependencies in
  `skills/fetch-portal/pyproject.toml` (`httpx`, `jsonschema`, `pyyaml`); tests: `uv run pytest` in that folder.
  Built and tested only against a fake Portal: the real hand-out API (Story 4.7) is not built yet, so it has not
  been tried end to end. A `portal-<batch>.complete` marker means every page of a batch is on disk; a batch cut
  off mid-write is deleted, never acked.
- **`portal-publish page <slug>`** — sends one Clarification page, with its screenshots, to the Relevant Clients
  Portal. `publish.py page plan <slug>` finds `docs/BA/clarifications/<slug>-decisions.yaml` (else `<slug>.yaml`),
  runs `_fixyaml.py` on it, builds the `clarification/1` page from the contract's fields only (old `settled:` lines
  become decisions with no date or person; `spec`, `events`, Figma ids, `spec_ref` and the rest stay in the repo),
  sends each screenshot under a bare, unique file name (`name-2.png` on a clash), checks the contract and the limits
  (PNG / JPEG / WebP, 10 MB each, 90 MB in all), sends a multipart dry run and prints what the Client will read.
  After the BA's yes, `page send` re-checks every screenshot and sends the same page (`page discard` on a no). A
  placeholder `url` is left out with a warning; a page with no `round:` line stops. "Round <label> already has
  answers — give it a new round key" when the Portal refuses a re-send. `clarification-page` → Publish runs
  portal-publish when the profile has `tools.portal`.

- **`portal-publish` contract 1.1.0** (tag `portal-contract-1.1.0`). Adds the `clarification/1` page schema and its
  readable twin; the `answers/1`, `ack-request/1` and `ack/1` schemas for handing Answers out; and the page form of
  `publish-reply/1` (picked by `kind`). `index.json` accepts `dashboard/1` and `clarification/1`. New named checks
  `unique_question_id`, `unique_option_v`, `one_rec_max`, `bare_file_names`, `one_hero_max`, `max_screenshots`,
  `unique_decision_id` and `screens_match_parts` (raises `screenshot_mismatch`); `no_html_entities` now covers page
  text. New fixtures, among them the converted `example-probate-decisions.yaml`; broken replies and requests are
  shared invalid cases too; every 1.0.0 fixture is unchanged. `check_publish` takes `kind` and, for a page, the
  screenshot part names. PyYAML is a new dev dependency (fixture build only).
- **`portal-publish` contract v1** (tag `portal-contract-1.0.0`). New folder `skills/portal-publish/contract/`: the
  `dashboard/1` schema and its readable twin, the `publish-reply/1` and `status/1` reply schemas, `errors.json`,
  `light-html.json`, `index.json`, `checks.md` and valid/invalid fixtures. The Relevant Clients Portal keeps an exact
  copy. Python checks in `skills/portal-publish/checks.py`; tests: `uv run pytest` in that folder. The skill itself
  comes later.
- **`portal-publish dashboard`** — sends the Dashboard to the Relevant Clients Portal. `publish.py dashboard plan`
  builds the dashboard, makes the `dashboard/1` payload (no `client: false` Features or Items, `client_s` for `s`,
  no to-dos or done Items), checks it against the contract, sends a dry run and prints what the Client will read;
  after the BA's yes, `dashboard send` sends the same payload and reports the Portal's confirmation (`dashboard
  discard` on a no). New profile keys `tools.portal.url` and `tools.client_contacts`; the Publish key lives in a
  git-ignored `.env` (`PORTAL_PUBLISH_KEY`). `ba-setup project` asks for both keys; `ba-dashboard` → Publish runs
  portal-publish when the profile has `tools.portal`. `install.py` no longer copies a skill's `.venv` or
  `.pytest_cache`. `portal-publish page <slug>` answers "not built yet". New dependencies in
  `skills/portal-publish/pyproject.toml`: `httpx` and `pyyaml` (run with `uv run --project <skills>/portal-publish`).
  `tools.portal.url` must be `https://` except for localhost, 127.0.0.1, `*.localhost` and `*.test`.

- **Dashboard search.** A search box on the Map and Board (or press `/`) finds areas, features and items
  in every product by part of their name; picking one opens it on the map. The first option, "Show all
  matches", filters the Map and Board to those names instead (an area or feature whose name matches
  keeps everything under it); a "Name" chip shows and clears it. First built on Acme Lending (28 Oct).
- **Open tickets on an area.** An area's "In Jira" section lists up to 5 of its open tickets, the ones
  being built first. `jira-areas.mjs` now keeps each open ticket's key, name and last update — run
  `map/build.py --refresh` once to get them.
- **The page title comes from `dashboard.yaml`'s `title`**, so a rename no longer resets on each build.

## 0.7.0 — 2026-10-25

- **The dashboard page is now Map + Board.** `ba-dashboard` builds one page with two tabs and publishes it
  to the same link: **Map** (product → area, which is a Jira component → feature → items; six stages,
  the same on every project, as colours and stage-mix rings; red badge for open client questions,
  orange for items waiting over 30 days; a note and "Resolved" tick on each item that `map/sync.py`
  writes back) and **Board** (rows are Jira releases, columns are areas, one card per feature). New
  folder `skills/ba-dashboard/map/`: `build.py` (`--refresh` re-reads Jira), the page template, three
  read-only Jira scripts, `sync.py`. First built on Acme Lending (24–25 Oct).
- **Nothing project-specific in the build.** Grouping now lives in `dashboard.yaml`: a feature's `id`,
  `short`, `tickets` and `jira_area`; a new `topics:` list for work with no feature row; an item's
  `feature:` puts it under its bubble. The profile gains `tools.dashboard.page` and
  `tools.dashboard.map` (`products`, `stage_of_status`). `dashboard.py build` checks the new fields.
- **Offer the dashboard right after the project brief.** `ba-dashboard` → *Starting one* seeds features
  from the brief; `ba-setup check` warns when a project has a brief but no dashboard, or still has the
  old table page; the new-project flow has it as step 3b.
- **Dashboard rules that were project-only are now in the skill:** bring the clarification page, spec
  status and release folder in line on every update; the client copy in Slack (when the project has
  `dashboard-slack.yaml`).
- **Clarification pages — new layout.** Name, description, problem and solution; "Open in Figma" on every
  screen; answered questions collapsed with "Change this answer"; a side panel with progress, Send and a
  timeline (`decisions` with who and when, `events` for rounds and stage changes). The stage comes from the
  dashboard map (`docs/BA/mind-map/stages.json`, by the page's `url`), and "Back to the map" opens the map
  on the feature. Send also carries `changes` (requests to change an earlier decision). Old pages with
  `settled:` still build; `scripts/_convert_v2.py` moves one to the new fields. The example page is the
  new layout.
- `intake-and-triage` dashboard items carry `feature:`; `ba-spec` adds a filed ticket to the feature's
  `tickets:` on the dashboard.

- **`figma-build` gotchas G57–G59**, first recorded on Majordome (2026-09-30): a bound-variable paint keeps its
  opacity only when the opacity is in the paint you bind, and tints are safest re-set in a separate call (G57);
  a screenshot in the same call as a fill change can show the old fill (G58); some CMS-served WebP files upload
  with HTTP 200 and render blank — convert to JPEG first (G59).
- **`figma-build` gotcha G60** — generated FigJam diagrams: connectors keep their old routes after the shapes move;
  recreate them after the move, and set the label font to Inter because generated labels report an empty family.

## 0.6.1 — 2026-09-29

- **A Jira ticket is the feature's storefront, not a tracker line.** Feedback from the Acme Lending dev and
  QA team: developers build from the spec with BMad and read the ticket as the plain-language summary of
  what to do; QA test mostly by hand and work from the ticket. New **`skills/ba-spec/assets/ticket-template.md`**:
  what and why, where (the click path), what changes, how to test (test data, numbered steps with the
  expected result, regression, the not-allowed role), known limits that are not bugs, then the spec and
  Figma links. Still never the spec body. `ba-spec` step 9 writes the description from it and checks
  every test-data step can really be done; `ba-spec` hard rule 7, `jira`, `fetch-jira-backlog` and the
  ongoing-project flow point at it instead of "short description + spec link". First used on ACME-1710.
- **`figma-build` gotcha G56** — hiding layers inside an instance replaces the node (re-find from the
  instance root for every hide), hidden sublayers drop out of `.children`, and fixed-height wrappers keep
  their gap; hide the known item level by name, never "climb until the parent has ≥N children".

## 0.6.0 — 2026-09-25

- **One PRD per phase, everywhere.** No living whole-system PRD: the code says how the system works now
  (Claude reads it), specs say why, phase PRDs say what is being built. Acme Lending's `docs/prd.md` is
  frozen at 6.0 / 1.17.0; the PRD catch-up routine is dropped. FR numbers live in the register; the phase
  PRD that takes a spec lists its number (template `decided` updated).
- **Reference folder** — `docs/BA/reference/` in every project, for documents from the client and sales
  (proposal, WBS, contract scope): an index `README.md` and a `.gitignore` that keeps recordings out of git.
  `ba-setup project` creates it; the new-project flow starts from it.
- **`skills/data-dictionary`** — new. NWE's domain-dictionary generator, made general: several Prisma
  schemas read from the remote branch, UI labels from translation files or constant files (suggested
  labels), and two new columns, Required and Min / max. `ba-spec` checks every new field name and label
  against it.
- **`skills/messages`** — new. The messages catalogue: every email, in-app, push and SMS message, with
  trigger, recipients, subject, content, status and spec; a searchable page built from
  `docs/BA/messages.yaml`. The template now asks rules that send a message to name its id (`[msg: M-012]`).
- Profile: `tools.dictionary`, `tools.messages`; `ba-setup check` reports both.

## 0.5.0 — 2026-09-25

- **`skills/ba-dashboard`** — new. The project's BA dashboard, one page at one link: features in flight
  (each with its clarification page and open questions), awaiting external input, open to-dos, and the
  **next call agenda** (was "Friday agenda"). Built from `docs/BA/dashboard.yaml`, never hand-edited; the
  script builds the page and adds, closes and links items.
- **`clarification-page`** puts every page on the dashboard as part of publishing (`set-clar`, build,
  republish) — the dashboard is now the register of clarification pages.
- **`intake-and-triage`** writes its dashboard actions into `dashboard.yaml` (lists `awaiting`, `todos`,
  `agenda`) instead of markdown zones in `dashboard.md`, and rebuilds and republishes the dashboard once
  at the end of a run.
- Profile: `tools.dashboard` (`file`, `url`); `ba-setup check` reports it.

## 0.4.0 — 2026-09-24

Every BA skill now lives in ba-tools and reads the project profile.

- **Moved in** from the lead BA's personal config: `fetch-fireflies`, `fetch-gmail`, `fetch-slack`,
  `fetch-jira-backlog`, `intake-and-triage`, `jira`, `confluence`, `feature-brief` — and the
  clarification-page generator as a new skill, `clarification-page`. No personal paths left; each
  skill starts with the setup check and reads its area from the profile.
- **Fetchers read the profile.** Fireflies keeps only calls with a client participant
  (`--clients`); Gmail lists client threads straight from `tools.client_emails` with no label or
  saved config; Slack takes `tools.slack.channels` as `--channels`. The old per-tool config files
  still work as a fallback. `project_slug` is no longer needed.
- **Gmail sign-in moved** to `~/.claude/ba-tools/state/gmail-token.json` — never inside a skill folder
  a project commits. The old location is still read.
- **Jira scripts** take `--projects KEY=folder,…` instead of the hard-coded ACME/BOND. `jira file-spec`
  is retired (it pasted the spec into the ticket and blanked header lists) — `ba-spec` files tickets.
  `jira` gained its missing name/description header.
- **Triage fixes**: a spec counts as approved when its status is `ready` or `filed` (the "goes against
  something approved" check could never fire on template specs); Jira is read with the `jira` skill;
  the pointer to a missing design document, the stale "test mode only" status and the retired
  downstream skills are gone; it reminds the BA that the dashboard page is updated by hand.
- **`feature-brief`** is generic (no NWE wording) and records that the brief is how the client sees
  the requirements, while the clarification page is where they answer.
- **`scripts/install.py`** installs or updates everything in a project; `ba-setup check` warns when a
  project is behind the local ba-tools clone and prints the command.

## 0.3.1 — 2026-09-24

- **Default: the design system lives inside the product's own Figma file** — components on their own
  pages beside the screens, live at once, no publish and accept. A separate library file only when two
  or more design files share the components (Acme Lending + Bond Portal keep theirs for that reason).
  Rule 19, the design-system mode and `ba-setup design` now handle both setups; the one-file setup gets
  a screenshot check of a few screens after a component change instead of a publish review.

## 0.3.0 — 2026-09-24

- **`skills/figma-build`** — moved from the lead BA's personal commands and made the same for every
  project. Three modes: `reproduce` (a shipped screen, from the code), `concept` (a new feature or
  change, from the spec), `design-system` (set up or change a design system). The quick clone-first
  method is the default; the spec-first method is only for a genuinely new or complex screen, and the
  skill says so before starting. Loads Figma's own `figma-use` skill first.
- `references/rules.md` — 24 build rules gathered from the Acme Lending build rules and the lead BA's
  memory, with every project value taken out.
- `references/plugin-gotchas.md` — one file of Figma plugin traps: Acme Lending's 488 lines and the
  ~25 NWE recorded separately, merged.
- `references/inventory.md` — the frame inventory is generated from the live file, never hand-kept
  (NWE's config had grown a 4,200-line frame list).
- **Design profiles** — one per product (`docs/BA/design-system/<folder>/design-profile.yml`): Figma
  files, design-system library, tokens, frame sizes, product traps. Real ones for Acme Lending, the
  Bond Portal and NWE in `profile/examples/design/`. The project profile points at them
  (`products[].design_profile`).
- **`ba-setup design`** — writes a design profile: read out of the code and Figma for a shipped
  product, or set up from a stock kit and the client's brand for a new one. `check` now reports a
  missing or incomplete design profile.
- A new concept may draw what the design system lacks, but only as a layer named `DS gap · …`, listed
  in the concepts register.

## 0.2.0 — 2026-09-24

- **`skills/ba-setup`** — new. `check` shows one table of everything a BA needs; `me` walks the BA's
  own keys, connectors and programs; `project` fills the project's area in each tool into the profile.
  `me` also offers starter defaults for newcomers: a simple-language section in `~/.claude/CLAUDE.md`
  and read-only permissions (reading runs without asking; changes still ask; force-push, hard reset,
  `rm -rf` and sending email are blocked). Nothing is removed from the BA's settings; both files are
  backed up.
- **Profile version 2** — new `tools:` block (client emails, Slack channels, Figma files, Confluence),
  and `client_representations`. `client_review` is `clarification-pages` in every project: the page the
  BA shares with the client on the call. The feature brief and Figma show the requirements; comments on
  them are extra client input.
- **`ba-spec`** — runs the setup check before its first step, so a new BA is sent through `ba-setup`
  automatically; change requests are approved on the clarification page.
- `scripts/check-project.py` folded into `ba-setup` (`check-project`), and now ignores Windows line
  endings. `.gitattributes` keeps every file on LF.
- `docs/` — the three flow documents.

## 0.1.0 — 2026-09-24

First release: the spec step, made the same for every project.

- `skills/ba-spec` — the spec skill, moved from acme-docs (`.claude/skills/ba-spec`, branch
  `ba-tools`). Every Acme Lending fact taken out and read from the project profile instead: products,
  roles, id numbering, spec folders, Jira, code repos and branches, spec links, client review route.
  Hand-off now follows the profile's `downstream` — a Jira ticket, the PRD, or both.
- `skills/ba-spec/assets/spec-template.md` — the approved template (acme-docs `ba-tools` @
  8cc4893d), made universal: the header, section 11 (roles), section 14 (code branch) and "How it is
  used" now point at the profile. Carries `ba_tools_version`.
- `profile/` — the profile layout (`README.md`), a blank example, and the two real profiles:
  Acme Lending + Bond Portal, and NWE (built from NWE's existing `.ba-profile.yml`, with the facts
  its 24 Sep local template edits had added).
- `scripts/check-project.py` — fails when a project's profile is missing a key or its template copy
  differs from ba-tools.
