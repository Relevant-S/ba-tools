# Contract `dashboard/1`

The readable twin of `dashboard-1.schema.json`. If the two ever disagree, the schema wins and this file is
fixed. Source of the fields: data-contract spec §10 (clients-portal).

One Dashboard Publish is one JSON object: the envelope at the top level, plus `features`, `items`, `areas`,
`release_rows` and `client_contacts`. A field not listed here is refused (`contract_invalid`, naming it).

## Who sees a field

| Level | Meaning |
|---|---|
| `client` | May be shown to a Client person. |
| `id` | An identifier. May reach the browser only as a hidden value (form values, data attributes, web addresses), never shown as text. |
| `portal` | Used by the Portal's server only. Never sent to any browser. |
| `admin` | Shown only in the Publishing log. |

## Envelope — all `admin`

| Field | Type | Required |
|---|---|---|
| `contract` | exactly `dashboard/1` | yes |
| `sent_at` | UTC time, exactly `YYYY-MM-DDTHH:MM:SS.sssZ` | yes |
| `sent_by` | text ≤ 200 (git user name) | yes |
| `ba_tools_version` | text ≤ 40 | yes |
| `source_commit` | text ≤ 64 (the repo commit) | no |

## `features` — at most 300

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 40, unique (check `unique_feature_id`) | yes | id |
| `title` | text ≤ 200 | yes | client |
| `short` | text ≤ 40 | no | client |
| `summary` | light HTML ≤ 2,000 | yes | client |
| `open` | list of text ≤ 500 | no | client |
| `clar_url` | link (URI) ≤ 2,000 | no | portal |
| `stage` | one of `concept`, `spec`, `ready`, `dev`, `qa`, `done` | yes | client |
| `map_area` | text ≤ 100 | yes | client |
| `releases` | list of text ≤ 100 (empty or absent = "Not planned yet") | no | client |
| `done_date` | date `YYYY-MM-DD` | no | portal |

## `items` — at most 1,000

| Field | Type | Required | Who sees |
|---|---|---|---|
| `key` | 12 lower-case hex characters, unique (check `unique_item_key`) | yes | id |
| `kind` | `waiting` or `agenda` | yes | portal |
| `feature` | text ≤ 40 (a Feature `id`) | no | portal |
| `who` | text ≤ 200 | yes | portal |
| `since` | date `YYYY-MM-DD` | yes | portal |
| `title` | text ≤ 300 | yes | client |
| `text` | light HTML ≤ 2,000 | no | client |
| `how_to_send` | text ≤ 300 | no | client |

## `areas` and `release_rows` — both `client`

| Field | Type | Required |
|---|---|---|
| `areas` | list of text ≤ 100, in order | yes (may be empty) |
| `release_rows[].name` | text ≤ 100 | yes |
| `release_rows[].released` | yes/no | yes |

`release_rows` is required and may be empty.

## `client_contacts` — at most 200, all `portal`

Required, may be empty (then nothing shows under "Waiting on you"). Each accepted Publish replaces the whole list.

| Field | Type | Required |
|---|---|---|
| `name` | text ≤ 100 | yes |
| `email` | email ≤ 254 | no |
| `slack` | text ≤ 100 (Slack name or member id) | no |

## Text rules

- Every text field has at least 1 character.
- **Light HTML** (`features[].summary`, `items[].text`): only the tags and class in `light-html.json`. The
  Portal cleans these on arrival.
- **Plain text** (every other text field): no HTML entities such as `&mdash;` (check `no_html_entities`).
- Lengths count characters (Unicode code points), not bytes.

## Limits not in spec §10

These were set while writing the contract, to give every text field a bound: release names and `areas` entries
≤ 100 (as `map_area`), `feature` on an Item ≤ 40 (as a Feature `id`), `sent_by` ≤ 200, `ba_tools_version`
≤ 40, `source_commit` ≤ 64, `clar_url` ≤ 2,000, contact `email` ≤ 254 and `slack` ≤ 100.

## Checks

See `checks.md` for the order of checks, the result shape and the three named checks.
