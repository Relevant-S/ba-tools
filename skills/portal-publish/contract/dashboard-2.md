# Contract `dashboard/2`

The readable twin of `dashboard-2.schema.json`. If the two ever disagree, the schema wins and this file is
fixed. Source of the fields: data-contract spec §10 (clients-portal) and Story 3.7.

`dashboard/2` carries the whole BA dashboard, shaped like the data the BA page itself draws: areas with their
Jira facts, Features, Map topics, Items, releases and Board cards with their tickets. The Portal shows it as it
is. `dashboard/1` stays accepted, so an older ba-tools keeps publishing.

**One send is one product.** A BA repo with two products sends each to its own Portal project, with that
project's key. So there is no product field anywhere: a `products` or `prod` field is refused like any other
unknown field.

One Dashboard Publish is one JSON object: the envelope at the top level, plus `jira_base`, `areas`, `features`,
`topics`, `items`, `releases`, `cards`, `client_contacts` and, since 1.3.0, the optional
`clarification_pages`. A field not listed here is refused
(`contract_invalid`, naming it). Never sent: BA to-dos, notes, "Resolved" ticks and the BA page's title.

**Since 1.4.0** four optional fields copy more of the BA page: an Item's `hot`, a Feature's `stage_why` and
`area_how`, and an open ticket's `updated`. A send without them (an older ba-tools) is still valid: the Portal
leaves those parts out and never guesses them.

## Who sees a field

| Level | Meaning |
|---|---|
| `client` | May be shown to a Client person. |
| `id` | An identifier. May reach the browser only as a hidden value (form values, data attributes, web addresses), never shown as text. |
| `portal` | Used by the Portal's server only. Never sent to any browser. |
| `admin` | Shown only in the Publishing log. |

Everything below is `client` unless its row says otherwise. Unlike `dashboard/1`, ticket keys, assignees and an
Item's `who`, `since` and `kind` are shown (Vadim, 28 Oct 2026).

## Envelope — all `admin`

As in `dashboard/1`, with `contract` exactly `dashboard/2`:

| Field | Type | Required |
|---|---|---|
| `contract` | exactly `dashboard/2` | yes |
| `sent_at` | UTC time, exactly `YYYY-MM-DDTHH:MM:SS.sssZ` | yes |
| `sent_by` | text ≤ 200 (git user name) | yes |
| `ba_tools_version` | text ≤ 40 | yes |
| `source_commit` | text ≤ 64 (the repo commit) | no |

## `jira_base`

| Field | Type | Required | Who sees |
|---|---|---|---|
| `jira_base` | `https://` link ≤ 2,000, the Jira site, e.g. `https://example.atlassian.net`; any other scheme (`http:`, `javascript:` …) is refused | yes | client |

Ticket keys and "In Jira" link to this site, whether or not the Client has Jira access.

## `areas` — at most 1,000, in the BA page's order

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 300, unique (check `unique_area_id`) | yes | id |
| `name` | text ≤ 255 (a Jira component name) | yes | client |
| `quiet` | yes/no: an inactive Jira component | yes | client |
| `special` | `no_area` or `not_linked` (the two areas that are not a component); each on one area at most (check `unique_special`) | no | client |
| `jira` | the area's Jira facts, below | no | client |

`jira`:

| Field | Type | Required |
|---|---|---|
| `description` | text ≤ 5,000 | no |
| `done`, `in_progress`, `open` | whole numbers ≥ 0 | yes |
| `last_done` | date `YYYY-MM-DD` | no |
| `search` | `https://` link ≤ 2,000 to all the area's tickets in Jira ("All its tickets in Jira ↗"), since 1.4.0 | no |
| `shipped` | at most 20 of `{ key, summary ≤ 255, date }`, a key at most once (check `unique_ticket_in_list`) | no |
| `open_tickets` | at most 20 of `{ key, summary ≤ 255, status ≤ 100, stage, updated }` (`updated` optional, since 1.4.0), sent already ordered, a key at most once | no |

`open_tickets` come in the BA page's order: being built or tested first (Jira category `indeterminate`), then
newest updated. `stage` is `dev` for `indeterminate`, else `ready`, as on the BA page. `updated` (since 1.4.0,
optional) is when Jira last updated the ticket: a date `YYYY-MM-DD` or a UTC time `YYYY-MM-DDTHH:MM:SS.sssZ`.
It is only for sorting, the same way.

`open` counts every ticket that is not done, so it includes the tickets counted in `in_progress` (being
built or tested).

## `features` — at most 1,000

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 80, unique (check `unique_feature_id`) | yes | id |
| `area` | an area `id` (check `known_area`) | yes | id |
| `title` | text ≤ 500 | yes | client |
| `short` | text ≤ 100 | no | client |
| `summary` | light HTML ≤ 20,000 | yes | client |
| `open` | at most 200, each text ≤ 2,000 | no | client |
| `answered` | `{ done, total }`, whole numbers ≥ 0, `done` ≤ `total` (check `answered_in_range`) | no | client |
| `stage` | one of `concept`, `spec`, `ready`, `dev`, `qa`, `done` | yes | client |
| `stage_why` | text ≤ 400 (since 1.4.0): why the Feature is at its stage, the finished line the BA page shows, e.g. "In dev, its slowest open ticket. Tickets: 1 Done, 2 In dev" | no | client |
| `area_how` | text ≤ 200 (since 1.4.0): how the Feature was placed in its area, as the BA page says it: "from its tickets", "set on the dashboard" or "no tickets and no area set" | no | client |
| `done_date` | date `YYYY-MM-DD` ("Hide done > 2 weeks") | no | client |
| `clar_url` | link (URI) ≤ 2,000 | no | portal |
| `tickets` | at most 5,000 tickets (below), a key at most once (check `unique_ticket_in_list`) | yes (may be empty) | client |

## `topics` — at most 1,000

A Map topic is a group of work in an area that is not a Feature (no spec, no Clarification page).

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 80, unique and never a Feature's id (check `unique_topic_id`) | yes | id |
| `area` | an area `id` (check `known_area`) | yes | id |
| `title` | text ≤ 500 | yes | client |
| `stage` | a stage | yes | client |
| `tickets` | at most 5,000 tickets, a key at most once | yes (may be empty) | client |

## `items` — at most 5,000

Waiting and next-call agenda Items. Never to-dos, `done: true` or `client: false`.

| Field | Type | Required | Who sees |
|---|---|---|---|
| `key` | the first 12 hex characters of `sha1("<kind>\|<parent>\|<title>")` (title trimmed, UTF-8), unique (check `unique_item_key`) | yes | id |
| `kind` | `waiting` or `agenda` | yes | client |
| `parent` | a Feature or topic `id` (check `known_parent`) | yes | id |
| `who` | text ≤ 255 | yes | client |
| `since` | date `YYYY-MM-DD` | yes | client |
| `title` | text ≤ 500 | yes | client |
| `text` | light HTML ≤ 10,000 | no | client |
| `how_to_send` | text ≤ 2,000 | no | client |
| `hot` | yes/no (since 1.4.0): the BA marked it hot. Missing means no | no | client |

Every waiting and agenda Item is sent, so two Items under different parents may share a title. That is why the
key holds the parent too. (`dashboard/1` keeps `sha1("<kind>|<title>")`.)

## `releases` — at most 2,000, in the BA page's order

| Field | Type | Required |
|---|---|---|
| `name` | text ≤ 255, unique (check `unique_release_name`; cards name their release by it) | yes |
| `date` | date `YYYY-MM-DD` | no |
| `released` | yes/no | yes |
| `overdue` | yes/no | yes |

## `cards` — at most 10,000

The Board cards: one per Feature, Jira epic, or group of other tickets, per release and area.

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 100, unique (check `unique_card_id`) | yes | id |
| `kind` | `feature`, `epic` or `other` | yes | client |
| `area` | an area `id`, the card's column (check `known_area`) | yes | id |
| `release` | a release `name` (check `known_release`), or `null` for "Not planned yet" | yes | client |
| `title` | text ≤ 255 | yes | client |
| `stage` | a stage | yes | client |
| `blocked` | yes/no | yes | client |
| `done_date` | date `YYYY-MM-DD` ("Hide done > 2 weeks") | no | client |
| `feature` | a Feature `id` (check `known_card_feature`); required on a feature card, refused on the others (check `card_kind_fields`) | on a feature card | id |
| `epic` | the epic's Jira key; required on an epic card, refused on the others (check `card_kind_fields`) | on an epic card | client |
| `tickets` | at most 5,000 tickets, a key at most once (check `unique_ticket_in_list`) | yes (may be empty) | client |

An `other` card has neither `feature` nor `epic`.

## A ticket

| Field | Type | Required |
|---|---|---|
| `key` | text ≤ 50, `ABC-123` (pattern `^[A-Z][A-Z0-9_]*-[0-9]+`) | yes |
| `summary` | text ≤ 255 | yes |
| `status` | text ≤ 100 (the Jira status name) | yes |
| `stage` | a stage | yes |
| `assignee` | text ≤ 255 | no |

## `client_contacts` — at most 200, all `portal`

As in `dashboard/1`: required, may be empty (then nothing shows under "Waiting on you"). Each accepted Publish
replaces the whole list.

| Field | Type | Required |
|---|---|---|
| `name` | text ≤ 100 | yes |
| `email` | email ≤ 254 | no |
| `slack` | text ≤ 100 (Slack name or member id) | no |

## `clarification_pages` — optional, at most 1,000, `portal` (since 1.3.0)

The slugs of every Clarification page now in the repo (`docs/BA/clarifications/`) that belongs to this Portal
project. Each slug follows the `clarification/1` `slug` rule (runs of `a-z` and `0-9` joined by single hyphens,
1 to 80 characters), and each is listed once (check `unique_page_slug`).

- **Present** (may be empty): the Portal hides from the Client every page of this project that is not in the
  list, at once, and shows again any listed page it had hidden. A hidden page's data is deleted once none of
  its sent Answers is still waiting to be fetched. The reply's `pages_removed` names the pages this send hides
  (on a dry run, the pages it would hide).
- **Missing**: no page is touched. An older ba-tools that does not send the field changes nothing.

Which pages belong to which product's project is the sender's job: a page goes with the product of the Feature
whose `clar.url` points to it ("Both" means every product); a page no Feature links goes to the first product.

## Text rules

- Every text field has at least 1 character.
- **Light HTML** (`features[].summary`, `items[].text`): only the tags and class in `light-html.json`. The
  Portal cleans these on arrival.
- **Plain text** written by the BA (every other text field): no HTML entities such as `&mdash;` (check
  `no_html_entities`).
- **Text copied from Jira** (area names and descriptions, release names, card titles, ticket summaries,
  statuses and assignees) is not checked for entities: the BA cannot fix it, and the Portal shows it as
  escaped plain text. `checks.md` lists the exact fields.

## The reply's counts

The reply to a `dashboard/2` send also counts `areas`, `topics`, `cards` and `tickets`. `tickets` is the tickets
on Board cards only (all `cards[].tickets` together), not the Feature, topic or area ticket lists.
- Lengths count characters (Unicode code points), not bytes.

## Limits

255 is Jira's own maximum for a version name, a component name and an issue summary. Every other limit is at
least twice the largest value in the real Acme Lending data (28 Oct 2026). The Portal takes a body of at most
5 MB; all of Acme Lending in one send is about 474 KB.

## Checks

See `checks.md` for the order of checks, the result shape and the named checks.
