# Contract `timeline/1`

The readable twin of `timeline-1.schema.json`. If the two ever disagree, the schema wins and this file is fixed.
Since contract 1.6.0.

`timeline/1` is the BA's Timeline page data (ba-tools `skills/timeline`, `build.py --json`), sent to the Portal
for one product. The Timeline replaces Map and Board (Vadim, 6 Nov 2026). Clients see what the BA sees: every
field the build writes is kept, except the BA page's own links (below).

- **Where it goes:** `POST /api/v1/publish/dashboard`, like `dashboard/2`, with the same key and `?dry_run=1`.
  The Portal stores it as the project's Dashboard version. The latest send of either kind wins: a `timeline/1`
  send replaces a `dashboard/2` one, and a later `dashboard/2` send brings Map and Board back.
- **One send is one product**, as with `dashboard/2`.
- **No light HTML.** Every text field is plain text. The Portal escapes it.
- **No nulls.** A field the build writes as `null` is left out of the send. A `null` anywhere is refused.

## Who sees a field

The levels are those of `dashboard-2.md`: `client` (may be shown), `id` (an identifier, never shown as text),
`portal` (server only), `admin` (the Publishing log only). Everything below is `client` unless its row says
otherwise.

## What changes from the BA page's data

| BA page field | In `timeline/1` |
|---|---|
| feature `clar` (a claude.ai artifact link) | **left out**. The feature names its Portal Clarification page by slug in `page` instead |
| feature `clarLabel` | kept only when the feature has a `page` |
| `pages` (the Clarification pages tab) | **left out**: the Portal builds that tab from its own pages |
| `dashboardUrl` | **left out**: the Portal has its own address |
| `pins[].decided[].url` | **left out** (an artifact link) |
| — | **added:** the envelope, `client_contacts`, `clarification_pages` |

## Envelope — all `admin`

As in `dashboard/2`, with `contract` exactly `timeline/1`: `contract`, `sent_at` (UTC, exactly
`YYYY-MM-DDTHH:MM:SS.sssZ`), `sent_by` (≤ 200), `ba_tools_version` (≤ 40), all required; `source_commit` (≤ 64),
optional.

## The top level

| Field | Type | Required | Who sees |
|---|---|---|---|
| `product` | object, below | yes | client |
| `today` | date `YYYY-MM-DD`: the build day | yes | client |
| `start` | date: where the chart starts | yes | client |
| `from` | date: the earliest feature start, when before `start` | no | client |
| `built` | text ≤ 40: "06 Nov 2026, 11:11" | yes | client |
| `groups` | ≤ 200 area groups, below | yes | client |
| `pins` | ≤ 10,000 pins, below; ids unique (`unique_pin_id`) | yes | client |
| `releases` | ≤ 2,000 `{ name ≤ 255, date }`, both required | yes | client |
| `client_contacts` | ≤ 200 `{ name ≤ 100, email?, slack? }`, as in `dashboard/2` | yes (may be empty) | portal |
| `clarification_pages` | ≤ 1,000 page slugs, as in `dashboard/2`; unique (`unique_page_slug`). Missing: no page is touched | no | portal |
| `suggestion_status` | since 1.8.0: ≤ 100,000 decisions on Client suggestions, below | no | client |
| `upcoming` | since 1.9.0: ≤ 500 planned events ("Coming up"), below | no | client |

`product`: `name` (≤ 200), `tagWord` ("Release" or "Phase", ≤ 40), `tracker` ("jira", "github-bmad", ≤ 40), `ba`
(the BA's first name, ≤ 100), `footer` (≤ 5,000, may be empty), all required; `workLink` (`https://` link ≤ 2,000),
optional.

## A group and an area

- Group: `name` (≤ 300) and `areas` (≤ 500), both required.
- Area: `name` (≤ 300) and `features` (≤ 5,000 rows), both required; `link` `{ label ≤ 200, url }` optional (a
  "see all in Jira" link; `https://` only).

## A row (`features[]`)

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 300; unique across the whole send (`unique_feature_id`) | yes | id |
| `label` | text ≤ 1,000 | yes | client |
| `stage` | `concept` · `spec` · `design` · `ready` · `dev` · `qa` · `done` · `live` | yes | client |
| `stages` | ≤ 50 `{ stage, from }` (the bar) | no | client |
| `since`, `doneDate`, `startedBefore` | dates | no | client |
| `origin` | `dashboard` · `spec` · `old-work` | yes | client |
| `basis` | `recorded` · `tracker` · `code` · `none` | yes | client |
| `originNote`, `basisNote` | text ≤ 2,000 | no | client |
| `desc` | text ≤ 20,000, may be empty | yes | client |
| `about` | ≤ 20 texts ≤ 2,000 | no | client |
| `page` | a page slug (the `clarification/1` slug rule); when `clarification_pages` is sent, one of them (`known_page`) | no | id |
| `clarLabel` | text ≤ 300 | no | client |
| `openQ` | ≤ 100 texts ≤ 2,000 | no | client |
| `todos` | ≤ 500 to-dos, below | no | client |
| `who` | ≤ 50 texts ≤ 100 | yes (may be empty) | client |
| `askedIn` | a pin's `id` (`known_pin`) | no | id |
| `askedBy` | text ≤ 200 | no | client |
| `tags` | ≤ 50 texts ≤ 200 (releases or phases) | yes (may be empty) | client |
| `work` | ≤ 1,000 work items, below | yes (may be empty) | client |
| `guess` | yes/no | yes | client |
| `changes` | a feature id; not checked (it may name a row of a later send) | no | id |
| `requests` | ≤ 500 changes and bugs, below | no | client |

A **work item**: `id` (≤ 300), `title` (≤ 2,000, may be empty), `status` (≤ 200, may be empty), all required;
`url` (`https://` link) and `done` (date), optional. Its text is copied from the tracker.

A **change or bug** (`requests[]`): `id` (≤ 300, id), `kind` (`sub-feature` · `change` · `improvement` · `bug`),
`title` (≤ 1,000), `stages`, `work`, all required; `askedIn` (a pin's id, `known_pin`), `askedBy` (≤ 200), `asked`
(≤ 2,000), `about`, `note` (≤ 2,000), `self` (a feature id, not checked), `guess`, `merged` (date), `splitOff` (a feature
id, not checked: it may name a feature of a later send), `tags`, optional. `self` and `splitOff`, like a row's
`changes`, are not checked against the send's feature ids.

## A to-do (`todos[]`)

| Field | Type | Required | Who sees |
|---|---|---|---|
| `key` | 12 lowercase hex: the BA page's item key, `sha1("<kind>\|<title>")`, title trimmed, UTF-8. Unique across the send (`unique_item_key`). Notes and Resolved ticks are saved under it | yes | id |
| `kind` | `waiting` · `agenda` · `todo` (the BA's own to-do) | yes | client |
| `title` | text ≤ 500 (as `answers/2` → `item.title`) | yes | client |
| `id` | text ≤ 40: the dashboard's short id | no | id |
| `who` | text ≤ 200, may be empty | no | client |
| `since` | date | no | client |
| `age` | whole number ≥ 0 | no | client |
| `status` | `open` · `hot` · `old` | no | client |
| `prod` | text ≤ 100 | no | client |
| `s`, `l` | text ≤ 10,000, may be empty | no | client |

## A pin (`pins[]`)

`id` (≤ 100, id; unique), `date`, `kind` (`call` · `email` · `comments` · `doc` · `page` · `idea`), `title`
(≤ 500), all required. Optional: `subject` (≤ 1,000), `ref` (≤ 100, id), `people` (≤ 200 names ≤ 100), `staff`
and `minutes` (whole numbers ≥ 0), `summary` (≤ 50 texts ≤ 5,000), `decided` (≤ 500 `{ title, page, how }`, each
text, may be empty) and `owes` (≤ 500 `{ who, text }`, each text, may be empty).

## Decisions on suggestions (`suggestion_status`, since 1.8.0)

Clients suggest a new feature or a change on the Portal Timeline (the Suggest button). `fetch-portal` brings each
suggestion in once (`answers/3`). The BA marks it Accepted or Declined in the product's
`docs/BA/timeline/suggestions.yaml`, and the next `timeline/1` send carries every decision:

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | the suggestion's id from `answers/3` (UUID) | yes | id |
| `status` | `accepted` · `declined` | yes | client |
| `reason` | text ≤ 2,000, may be empty: "Why it was declined", or "Note from <BA>" | yes | client |

- Each send replaces the whole list. A suggestion not in the list shows "Suggested".
- An id the Portal does not know is **ignored**, not refused (the BA may decide before the Portal has it, or a
  suggestion of another product).
- The Client view (`client_timeline_1`) carries the list as sent.

## Coming up (`upcoming`, since 1.9.0)

Planned events, from the data file's `upcoming:` list (ba-tools `skills/timeline`): a hard deadline, a
step that waits for a feature, a change with no date yet. The Portal shows them in the "Coming up" lane at the
top of the chart, in the "Coming up" tab, and as flags on the features they name. Clients see every field (Vadim,
6 Nov: the Client sees the same as the BA).

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 100, unique in the send (`unique_upcoming_id`) | yes | id |
| `title` | text ≤ 300 | yes | client |
| `kind` | `deadline` · `release` · `planned` | yes | client |
| `date` | date `YYYY-MM-DD` | no | client |
| `after` | a row `id` of the send (`known_feature`): it comes after that feature goes live | no | id |
| `needs` | ≤ 50 row `id`s of the send (`known_feature`) | no | id |
| `what` | ≤ 20 lines, each text ≤ 2,000: what has to happen | no | client |
| `who` | text ≤ 200 | no | client |

- An item has `date`, or `after`, or neither ("No date yet") — never both (a schema rule: a `not`, reported at the
  item, `/upcoming/<n>`).
- An item whose `date` has passed stays, greyed, with "N days late", until the BA removes it from the list.
- Each send replaces the whole list. Without the field there is nothing coming up.

## Named checks

In this order (see `checks.md`): `unique_feature_id`, `unique_item_key`, `unique_pin_id`, `unique_page_slug`,
`known_pin`, `known_page`, `unique_upcoming_id` and `known_feature` (both since 1.9.0), `no_html_entities`. `no_html_entities` skips the links (`product.workLink`, area
`link.url`, work `url`), the Client contacts' emails and the text copied from the tracker (work `title` and
`status`, `releases[].name`).

## The reply

The Portal replies `publish-reply/1` (kind `dashboard`). `counts`: `features` = every row plus their changes and
bugs, `items` = the to-dos, `client_contacts`, `areas`, `pins`. A dry run carries `client_view` in the
`client_timeline_1` form (with `suggestion_status` and `upcoming` as sent): the send without the envelope, `client_contacts` and `clarification_pages`, and
`client_contact_names`. With `clarification_pages`, `pages_removed` comes as for `dashboard/2`.
