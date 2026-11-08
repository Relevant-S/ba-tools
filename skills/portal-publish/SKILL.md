---
name: portal-publish
description: Send the project's Dashboard, or one Clarification page with its screenshots, to the Relevant Clients Portal, on purpose and checked — build it from docs/BA/dashboard.yaml or docs/BA/clarifications/<slug>-decisions.yaml, check it against the Portal's data contract, show the BA exactly what the Client will read (the Portal's own dry run), and send only after the BA says yes. Use when the BA says "publish to the portal", "send the dashboard to the client", "send this page to the client", "portal-publish dashboard", "portal-publish page <slug>", or after ba-dashboard or clarification-page publishes on a project whose profile has tools.portal.
---

# portal-publish

**What it does.** The Client cannot open the project repo. This skill puts the Dashboard, or one Clarification
page, in front of the Client in the Relevant Clients Portal — only when the BA decides, and with nothing
internal in it. The Portal checks every send again and logs it at **Admin → Projects → the Project →
Publishing**. The Dashboard steps come first below; the page steps are in "A Clarification page".

**Two commands with the BA's yes in between.** The shell cannot wait for typed input, so:

1. `dashboard plan` builds, checks and sends a **dry run** for each product. The Portal stores and logs
   nothing on a dry run. It answers with the Client's view, which you show the BA.
2. The BA says yes or no, once per product.
3. Yes → `dashboard send` for that product. No → `dashboard discard` for that product.

```
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard plan [--refresh] [--product "<name>"]
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard send --payload <file>
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard discard --payload <file>
```

`<skills>` = the folder this skill is installed in, one level up. Run from the project root (or add
`--root <project>`). Each command prints one JSON line: `ok: true` with the result, or `ok: false` with
`error` — already worded for the BA.

**One product, one Portal project.** A repo can hold two products (for example "AcmeLending" and "Investor
Portal" — the product switch on the BA page). Each product goes to its own Portal project, with that
project's own Publish key. The BA page's product switch is for the BA only: the Client switches projects in
the Portal's header. A repo with one product works as before, with one key.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. No passing
  stamp → `ba-setup check`.

## Settings

| Setting | Where | When it is missing |
|---|---|---|
| The Portal address | `tools.portal.url` in `docs/BA/specs/.ba-profile.yml` | stop: run `ba-setup project` |
| The Publish key, one product | `PORTAL_PUBLISH_KEY` in `.env` at the repo root (`ba-setup project` puts it there from a connect code) | stop: run `ba-setup project` |
| The Publish keys, two or more products | `tools.portal.products` in the profile names, per product, the `.env` variable that holds its key — for example `{AcmeLending: PORTAL_PUBLISH_KEY_ACME, Bond Portal: PORTAL_PUBLISH_KEY_BOND}` — and `.env` holds each one | stop before anything is sent, naming the product or the variable: run `ba-setup project` |
| `.env` kept out of git | `.gitignore` lists `.env`, and `.env` is not committed | stop: add it to `.gitignore` (and `git rm --cached .env` if it was committed) |
| The Jira site (ticket links) | the Jira search link of the first area on the BA page, else `jira.site` in the profile | stop: add `jira.site` to the profile |
| Client contacts | `tools.client_contacts` in the profile (`name`, `email`, `slack`) | falls back to `client_owners` in `docs/BA/dashboard-slack.yaml` (names only); with neither, a warning |

The script checks all of these itself, before it sends anything. **Never print, echo or paste a key.** Never
open `.env` to show it. Never ask the BA for a key, or tell them to copy one into `.env`. When a key is missing
or refused, the BA asks an Admin for a **connect code** (Admin → Projects → the project → Publishing → Connect a
repo), one per product, and runs `ba-setup project`: it swaps the code for a new key and writes it into `.env`.
Each connect adds a key; keys other repos use keep working.

Two products never share a Portal project. Two products naming the same `.env` variable, or two keys that
open the same Portal project, stop the run before anything is sent.

Pages (`page <slug>`) and `fetch-portal` use the same keys: each page goes to its own products' Portal
projects, and `fetch-portal` fetches from every product's project. `targets.py` reads these settings for both
skills.

**Which product a Clarification page goes with.** A page is a `docs/BA/clarifications/*.yaml` whose `slug:`
is its file name (`<slug>.yaml` or `<slug>-decisions.yaml`) and that has a `store_key:`. Other YAMLs are
skipped. A slug that breaks the slug rule is skipped with a warning. When `<slug>.yaml` and
`<slug>-decisions.yaml` both hold the page, the `-decisions` file is used, with a warning. With two or more
products, a page goes with the `prod` of every Feature in `docs/BA/dashboard.yaml` whose `clar.url` is the
page's `url:` (both trimmed and a trailing `/` dropped, as the Portal compares them; "Both" means every
product). If only Features with a `prod` that has no Portal project (a misspelled product) link a page, the run
stops and names them. A page no Feature links at all goes with the first product in `tools.portal.products`,
with a warning. With one product, or no `dashboard.yaml`, every page goes with the first product. To move a page to another product, change its Feature's `prod`: the next
Dashboard send removes it from the old project, and the next page send adds it to the new one.

## Run

1. **`dashboard plan`** (add `--refresh` only when the BA asks for it, or says yes to the stale-Jira
   warning; add `--product "<name>"` when the BA wants to send one product only). It:
   - runs `ba-dashboard`'s `dashboard.py build`, then `map/build.py`, so stages, areas and releases are current;
   - makes one `dashboard/2` payload per product from the BA page's own data (`const DATA` in
     `docs/BA/mind-map/mind-map.html`). Each holds the rows of that product and the rows marked "Both": its
     areas (with each area's Jira facts and its first 5 open tickets, in the BA page's order), Features, Map
     topics, Waiting and agenda Items (an Item on no Feature goes under its topic, or under "Not linked yet"),
     releases, and Board cards with their tickets. No payload holds a product field;
   - since contract 1.4.0, also copies four things the BA page shows: an Item's `hot` (the BA's `hot: true`), a
     Feature's "why this stage" line (`stage_why`, word for word as the BA page writes it) and how it was placed
     in its area (`area_how`), and each open ticket's last Jira update (`updated`, for the order). Each is sent
     only when the BA page's data has it; nothing is guessed;
   - lists, in each payload, the slugs of the Clarification pages that go with that product
     (`clarification_pages`). **The Portal removes from that project every page not on the list** (the Client
     stops seeing it; its data is deleted once its Answers are fetched). So a YAML that cannot be read, or two
     YAMLs with one slug, stop the run: a page missing from the list would be removed;
   - leaves out what the Client must not see: a Feature or Item with `client: false`, the Items and Board
     cards of a hidden Feature, to-dos, `done` Items, the BA's notes and the page title. `client_s` replaces
     `s`. Release names are sent whole (Jira allows 255 characters). A Board card that sits in another
     product's release is not on this product's Board on the BA page either, so it is left out, with a
     warning;
   - checks every product's payload against the contract (`checks.py`) **before anything goes to the
     Portal**. A failure names the product, the file, the row and the field. Nothing is cut to fit;
   - then, per product: asks the Portal which project the product's key opens (`GET /status`), sends the
     payload as a dry run, and writes it to a temp file outside the repo. If two products' keys open the same
     Portal project, it stops; nothing is sent.
2. **Show the BA, product by product, word for word:**
   - every line of `warnings`, once (stale Jira files, no Client contacts, a Board card in another product's
     release, pages no Feature links, a product with no pages at all);
   - each entry of `products`: its `client_list` starts with `<product> → Portal project "<project_name>"`,
     then the areas, the Features (title, short label, summary, stage, open questions, its Clarification
     page), the topics, one Board line ("Board: N cards (feature / epic / other), N tickets"), the Items
     grouped as "Waiting on you" and "Next-call agenda", and the Client contacts' names. Ticket lists are not
     printed. It comes from the Portal's own dry-run reply. Never rebuild it, reorder it or work out "Waiting
     on you" yourself. When the send would remove pages from that project, its last line is
     `These pages will be removed from the Portal project "<project_name>": <title> (<slug>), …` (from the
     reply's `pages_removed`). The BA must see it before saying yes;
   - that product's `left_out` as one line: "Left in the repo: N Features, N Items and N Board cards
     (client: false, done, to-dos)".
3. **Ask one question per product:** "Send this to the Portal project "<project_name>"?" If `warnings` has
   the no-contacts warning, the first question also asks whether to go on without contacts. Wait for each
   answer.
4. **Yes** → `dashboard send --payload <that product's payload path>`. It re-checks the file, asks the Portal
   again which project the key opens (and stops, keeping the file, if that is not the project `plan` showed),
   sends the same bytes for real with that product's key, and deletes the file. `send` and `discard` only take a
   `portal-publish-*.json` file in the system temp folder — a path `plan` printed.
   **No** (or anything but a clear yes) → `dashboard discard --payload <that path>`. Nothing is sent for that
   product. A "no" to one product does not stop the others.
5. **Report** `report` from each `send`: which product went to which Portal project, the counts (areas,
   Features, topics, Items, Board cards and tickets, Client contacts), the Portal's `publish_id` and its
   confirmation time (`received_at`, UTC), and the pages it removed, if any. The BA can see the new row at Admin → Projects → the Project →
   Publishing.

If the BA edits `dashboard.yaml` after `plan`, discard and run `plan` again — `send` sends what `plan` built.

## The Timeline — `timeline plan | send | discard` (contract 1.6.0)

The BA's Timeline replaces Map and Board on the Portal (Vadim, 6 Nov 2026). A product moves to the Timeline when
the BA sends `timeline/1` for it; a later `dashboard send` for that product brings Map and Board back. Until the
Timeline page is on the Portal, the Client sees a "new dashboard is on its way" card after a Timeline send, so
**send a Timeline only when the BA asks for it.**

```bash
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py timeline plan [--product "<name>"]
```

1. **`timeline plan`** finds each product's Timeline data file (`docs/BA/timeline/**/*-timeline.yaml`, matched by
   its `product.dashboard`), runs the Timeline build (`skills/timeline/scripts/build.py --json`), and turns it into
   one `timeline/1` payload per product: every field of the BA page, except that a feature's clarification page
   link becomes the Portal page's slug, and the BA page's own links are left out. It adds the Client contacts and
   the product's Clarification pages (`clarification_pages`, with the same removal rule as the Dashboard send).
   It checks every payload, asks the Portal which project each key opens (the Portal must accept `timeline/1`),
   sends a dry run, and writes each payload to a temp file.
2. **Show the BA**, product by product, every `warnings` line and the `client_list` word for word. Clients see
   what the BA sees: the list names every to-do, the BA's own included, and says pins are shown whole.
3. **Ask one question per product**, as for the Dashboard. **Yes** → `timeline send --payload <path>`;
   **no** → `timeline discard --payload <path>`. A Timeline payload is refused by `dashboard send`, and the
   other way round.
4. **Report** `report` from each `send`.

### Decisions on suggestions (contract 1.8.0)

Clients suggest features and changes on the Portal Timeline; `fetch-portal` brings each one in as an intake file
with its `suggestion_id`. The BA's answer goes back in the next Timeline send as `suggestion_status`, from one file
per product: **`suggestions.yaml` next to that product's Timeline data file** (e.g.
`docs/BA/timeline/suggestions.yaml`, or `docs/BA/timeline/admin/suggestions.yaml` for a product kept in
`docs/BA/timeline/admin/`):

```yaml
- id: 019a5a10-0b00-7c00-8a00-000000000001
  status: accepted
  reason: Planned for the next release.
- id: 019a5a10-0b00-7c00-8a00-000000000002
  status: declined
  reason: "Out of scope: not for the pilot."
```

- When the BA says **"accept suggestion …"** or **"decline suggestion … because …"**, add or change that line
  (the id from the intake file's `suggestion_id`; the reason in the BA's words, plain text, at most 2,000
  characters). Do not send: the decision goes out with the next `timeline plan`, when the BA asks for it.
- Keep every line: each send carries the whole list, and a suggestion not in it shows "Suggested". An id the
  Portal does not have is still sent; the Portal ignores it.
- `timeline plan` reads the file before the build. A bad line (not a list, an id that is not a suggestion id, a
  status other than accepted or declined, an unknown field, the same id twice) stops it with a plain message
  naming the file and the line; nothing is sent. No file: the send has no `suggestion_status`.
- The dry-run list shows "Decisions on Client suggestions (N)", one line per decision with its reason.

### Coming up (contract 1.9.0)

The Timeline build's `upcoming` list (the data file's `upcoming:`, see `skills/timeline/SKILL.md`) goes into the
send as it is: planned deadlines, releases and steps, which the Portal shows in its "Coming up" lane and tab.
The build stops on most bad items. For the rest, the Portal's check refuses the send and the plan names the item
(`unique_upcoming_id`, `known_feature`: `needs` and `after` name a feature of the send). The dry-run list shows "Coming up (N)", one line per item. Deploy a
Portal on 1.9.0 first: an older one refuses a send that carries `upcoming`.

## When it stops

Show `error` as it is; it already says what to do. Nothing was sent in these cases, except the "may have arrived" row.

| Case | What the BA sees |
|---|---|
| No `tools.portal`, no `.env`, no key | "… Run `ba-setup project` …" |
| Two or more products, and `tools.portal.products` names no key for one of them | "This repo has 2 products (…). … tools.portal.products … names no key for: …" |
| Two products name the same `.env` variable in `tools.portal.products` | "tools.portal.products … gives App and Admin the same .env variable (…), so both would go to the same Portal project …" |
| Two products' keys open the same Portal project | "The keys for App (…) and Admin (…) both open the same Portal project, "…" …": ask an Admin for the right key for one of them |
| At `send`, the key opens a different project from the one `plan` showed | "The key in PORTAL_PUBLISH_KEY_… now opens Portal project "…", but `dashboard plan` showed the … Dashboard going to "…" …": check `.env`, run `dashboard plan` again. The payload file is kept; `dashboard discard` removes it |
| A product's variable is not in `.env` | ".env has no PORTAL_PUBLISH_KEY_BOND (the Publish key for Bond Portal) …" |
| `--product` names no product of this repo | "There is no product called '…'. This repo's products: …" |
| A page YAML cannot be read and has no `slug:` line | "<file> does not read as YAML, and no top-level `slug:` line could be found in it …" |
| A page YAML cannot be read and its `slug:` line is not its file name | "<file> does not read as YAML, and its `slug:` line ('…') does not match its file name …" |
| A page YAML is not UTF-8 | "<file> is not UTF-8 text, so it is not clear whether it is a Clarification page …" |
| Only Features with an unknown `prod` link a page | "The page … (<file>) is linked only by Features whose prod is not a product with a Portal project (…): '<Feature>' (prod '…') in docs/BA/dashboard.yaml. Fix the prod …" |
| `.env` not ignored by git | ".env is not ignored by git …" |
| The build fails | "dashboard.py build failed: …" or "map/build.py failed: …" |
| The local check fails (any product) | "The Bond Portal Dashboard does not match the contract …", then one line per problem, like `docs/BA/dashboard.yaml → features 'Sign-up' → area: …` or `Jira → the release '…' → its name: … (/releases/3/name)` |
| No Jira site | "There is no Jira site address …": add `jira.site` to the profile |
| The Portal refuses a key on `GET /status` | "The Portal refused the key in PORTAL_PUBLISH_KEY_… (invalid_key) …", then: ask an Admin for a connect code and run `ba-setup project` (it replaces the key, after asking) |
| The Portal does not accept `dashboard/2` yet | "The Portal at <url> does not accept dashboard/2 yet …" |
| The Portal refuses | "The Portal refused the send (code): its message", each field it named, then the next step. Codes: `invalid_key` (wrong key), `project_archived`, `contract_invalid`, `contract_version_not_accepted`, `payload_too_large` |
| The Portal is down or the address is wrong | "The Portal is not reachable at <url>" |
| The real send went out but no reply came back (timeout, dropped connection) | "… it may have arrived …": check Admin → Projects → the Project → Publishing before sending again. The payload file is kept, so `send` can be run again with it if the send is not there. This is the one case where something may have been sent. |
| A reply the skill does not understand (for example an older Portal) | "The Portal's reply was not understood (HTTP <n>)" |

## A Clarification page — `page <slug>`

Same settings, same Step 0, same two steps with the BA's yes in between.

```
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page plan <slug> [--product "<name>"]
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page send --payload <file>
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page discard --payload <file>
```

`<slug>` is the `slug:` line of the page YAML (`page <slug>` alone does the same as `page plan <slug>`).

1. **`page plan <slug>`.** It:
   - finds `docs/BA/clarifications/<slug>-decisions.yaml`, else `<slug>.yaml`, and stops if the YAML's `slug:`
     is not `<slug>`;
   - runs clarification-page's `scripts/_fixyaml.py` on it first. That script quotes values holding a colon, in
     the BA's file. When it changed lines, the first warning says so: the BA commits the file with the page;
   - stops if the page has no `round:` line (the Round label the Client reads);
   - builds the page from the fields the contract names, and nothing else. Old `settled:` lines become
     decisions with no date and no person. `spec`, `events`, `figma_page`, `frame`, `spec_ref` and every
     other internal field stay in the repo and are listed in `left_out`. A placeholder `url` (like
     `https://claude.ai/artifact/<the page id>`) is left out with a warning; the page still sends;
   - gives each screen its "Open in Figma" link (contract 1.7.0), the same one the claude.ai page shows: a design
     screen's from `design.figma_file` and its `node`, a Question screen's own `figma`. A link that does not start
     with `https://www.figma.com/` is left out with a warning; the screen still sends, without the button. A
     `design.figma_file` that is not a bare key (letters and digits) warns once and gives no links; screens with a
     node but no `figma_file` warn once; an unquoted node (YAML reads `12:34` as 754) warns "quote the node".
     **The Portal must be on contract 1.7.0 first**: one on 1.6.0 refuses a page that carries `figma`. So deploy
     the Portal, then update ba-tools in the BA repos;
   - collects every screenshot the page names (`src`, relative to the YAML's folder). Each goes as its bare
     file name; a second file with the same name goes as `name-2.png`, then `-3` …;
   - checks it all: the contract (at most 50 Questions, 30 screenshots), each screenshot there, PNG, JPEG or
     WebP, at most 10 MB, and at most 90 MB in all. A failure names the YAML file, the row and the field;
   - finds the page's products (see "Which product a Clarification page goes with" above). With
     `--product "<name>"`, only that one, which must be one of them;
   - per product, with that product's key: with two or more products, asks the Portal which project the key
     opens (`GET /status`); then sends a **dry run** (multipart: the page JSON, then one part per screenshot).
     The Portal stores and logs nothing. **If any project refuses, the whole plan stops**: no payload file is
     kept and nothing is sent anywhere. If two keys open the same project, it stops too;
   - writes one payload file per project, in temp. Each holds the page JSON, each screenshot's path and
     checksum (never the screenshots themselves), the product and the name of its `.env` variable (never the
     key).
   The result has `products`: one entry per Portal project, each with its `payload`, `client_view`, `round`
   and `counts` (and `project_name` with two or more products). With one project, these are also at the top.
2. **Show the BA, word for word, for each entry of `products`:** every line of `warnings` (once); its
   `client_view` — with two or more products its first line is `<product> → Portal project "<name>"`, which
   the BA must see before saying yes; then the page name, the Round label, whether it is a new Round or
   replaces one, each Question with its options and the recommended one, the settled decisions and the
   counts. It comes from the Portal's own dry run: never rebuild or reorder it. Then `left_out` as one line:
   "Left in the repo: <the fields, comma-separated>".
3. **Ask one question per project:** "Send this page to the Client?" (with two or more products: "Send this
   page to the Portal project "<project_name>"?"). Wait for each answer.
4. **Yes** → `page send --payload <that project's payload path>`. It reads the key from the `.env` variable
   saved in the file, and stops if that variable is gone or the profile no longer gives it to that product. It
   re-reads every screenshot; if one changed since `plan`, it stops ("run `page plan` again"). With two or
   more products it asks the Portal again which project the key opens, and stops (keeping the file) if that is
   not the project `plan` showed. Then it sends the same page for real and deletes the file.
   **No** (or anything but a clear yes) → `page discard --payload <path>`. Nothing is sent to that project. A
   "no" to one project does not stop the others.
5. **Report** `report` from `send`: the page, the Round label, new Round or replaced, the counts of Questions
   and screenshots, the Portal's `publish_id` and its confirmation time (`received_at`, UTC). The BA sees the
   row at Admin → Projects → the Project → Publishing.

If the BA edits the YAML after `plan`, discard and run `plan` again — `send` sends what `plan` built.

**When a page send stops**, show `error` as it is. Besides the cases in the table above:

| Case | What the BA sees |
|---|---|
| No YAML for the slug | "No page YAML for '<slug>'. Looked for … and …" |
| One project refuses the dry run (two or more products) | `<product> → Portal project "<name>": ` then the refusal, then "No payload was kept: nothing was sent to any Portal project." |
| `--product` names a product the page does not go with | "The page … goes with …, not …: the Features in docs/BA/dashboard.yaml that link it (by clar.url) say so …" |
| `--product` on a page no Feature links | "No Feature in docs/BA/dashboard.yaml links the page … (by clar.url), so it goes with the first product, …, not … . To send it with …, put the page's url in the clar.url of a … Feature …" |
| At `page send`, the saved `.env` variable is gone, or no longer the product's | ".env has no …" or "`page plan` used the key in … for …, but the profile now names … for …" |
| At `page send`, the key opens a different project from the one `plan` showed | "The key in … now opens Portal project "…", but `page plan` showed the page going to "…" …". The payload file is kept; `page discard` removes it |
| The YAML's `slug:` is different | "… has slug 'a', but you asked for 'b' …" |
| No `round:` line | "… has no `round:` line …" |
| A screenshot is missing, not PNG / JPEG / WebP, or over 10 MB | `docs/BA/clarifications/<file> → design.screens[1] → src: …` |
| Over 90 MB in all | "… the Portal takes at most 90 MB in one send …" |
| The round key was already used: the Round has answers, or it was replaced and deleted (`round_has_answers`) | "Round <label> was already used (it has answers, or it was replaced and deleted) — give it a new round key", then: change `store_key` (and the round label) and run `page plan` again |
| `screenshot_mismatch` | a named screenshot did not arrive, or an unnamed one did; run `page plan` again |
| `contract_invalid`, `project_archived`, `payload_too_large`, `invalid_key` | the Portal's message, each field it named, then the next step |
| A screenshot changed between `plan` and `send` | "The screenshot … changed (or is gone) since `page plan` …" |

## Files

- `publish.py` — the commands above (`dashboard …` and `page …`).
- `targets.py` — the Portal address, and each product's `.env` variable and key. `fetch-portal` loads the same
  file.
- `checks.py` and `contract/` — the data contract both sides check against. Do not edit them here; a contract
  change is its own ba-tools change, copied to the Portal.
- `tests/` — `uv run pytest` in this folder.
