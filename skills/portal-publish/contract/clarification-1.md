# Contract `clarification/1`

The readable twin of `clarification-1.schema.json`. If the two ever disagree, the schema wins and this file is
fixed. Source of the fields: data-contract spec §10 (clients-portal), "`clarification/1` — the page" and
"— Questions", and its Limits.

One page Publish is one Round of one Clarification page. It goes to `POST /api/v1/publish/page` as
`multipart/form-data`: part `publish` holds this JSON object (the envelope at the top level, plus the page
fields), and each screenshot is one more part, named by its `file` value. A field not listed here is refused
(`contract_invalid`, naming it).

The skill builds the object from `docs/BA/clarifications/<slug>-decisions.yaml`. It never sends `spec`,
`product`, `doc_title`, `eyebrow`, `copy_header`, `copy_noun`, `stage`, `events`, `settled` (sent as
`decisions`), `design.figma_file`, `design.figma_page`, `screens[].node`, `screens[].frame`,
`questions[].spec_ref` or `questions[].screens[].figma`.

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
| `contract` | exactly `clarification/1` | yes |
| `sent_at` | UTC time, exactly `YYYY-MM-DDTHH:MM:SS.sssZ` | yes |
| `sent_by` | text ≤ 200 (git user name) | yes |
| `ba_tools_version` | text ≤ 40 | yes |
| `source_commit` | text ≤ 64 (the repo commit) | no |

## The page

| Field | Type | Required | Who sees |
|---|---|---|---|
| `slug` | runs of `a-z` and `0-9` joined by single `-`, 1 to 80 characters | yes | id — the page id; may appear in its web address |
| `store_key` | text ≤ 100 — the Round key | yes | portal |
| `url` | link (URI) ≤ 2,000 — matched to a Feature's `clar_url` | no | portal |
| `name` | text ≤ 120 (from `name`, else `title`) | yes | client |
| `round` | text ≤ 200 — the Round label | yes | client |
| `description` | light HTML ≤ 1,000 (from `description`, else `standfirst`) | no | client |
| `problem` | light HTML ≤ 1,000 | no | client |
| `solution` | light HTML ≤ 1,000 | no | client |
| `design` | object, below | yes | — |
| `decisions` | list, below | no | — |
| `questions` | list, below — at most 50 | yes (may be empty) | — |

The `slug` pattern is `^[a-z0-9]+(?:-[a-z0-9]+)*(?![\s\S])`: no hyphen first, last or twice in a row. It ends
in "nothing follows" rather than `$`, because Python's `$` also matches before a final line break, so
`"probate\n"` would pass there and fail in JavaScript.

## `design`

| Field | Type | Required | Who sees |
|---|---|---|---|
| `label` | text ≤ 80 | no | client |
| `more_label` | text ≤ 80 | no | client |
| `summary` | light HTML ≤ 700 | yes | client |
| `detail` | light HTML ≤ 3,000 | no | client |
| `screens[]` | list of screens | no | — |

Each design screen:

| Field | Type | Required | Who sees |
|---|---|---|---|
| `file` | bare file name ≤ 200 (no folders), unique in the page — also the name of its part | yes | portal |
| `cap` | text ≤ 300 | no | client |
| `hero` | yes/no — the screen shown first, at most one per page | no | portal |

## `decisions[]` — settled decisions, shown read-only

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 80, unique in the page | yes | portal |
| `date` | date `YYYY-MM-DD` | no | client |
| `who` | text ≤ 200 | no | client |
| `how` | text ≤ 300 | no | client |
| `title` | text ≤ 300 | yes | client |
| `detail` | text ≤ 1,000 | no | client |

An old page's `settled:` lines come as decisions with no `date`, `who` or `how` (data-contract E2).

## `questions[]` — at most 50

| Field | Type | Required | Who sees |
|---|---|---|---|
| `id` | text ≤ 80, the same in every Round (R19), unique in the page | yes | id |
| `section` | text ≤ 300 | no | client |
| `title` | text ≤ 300 | yes | client |
| `meta` | text ≤ 300 | no | client |
| `body` | light HTML ≤ 5,000 | yes | client |
| `body2` | light HTML ≤ 5,000 | no | client |
| `snag` | light HTML ≤ 5,000 | no | client |
| `quote.text` | text ≤ 1,000 (required when `quote` is there) | no | client |
| `quote.cite` | text ≤ 1,000 | no | client |
| `note` | text ≤ 300 — the prompt over the note box | no | client |
| `note_placeholder` | text ≤ 300 | no | client |
| `options[]` | 1 to 20 options, below | yes | — |
| `screens[]` | list of screens, below | no | — |

Each option:

| Field | Type | Required | Who sees |
|---|---|---|---|
| `v` | text ≤ 80, unique within the Question | yes | id |
| `t` | text ≤ 200 | yes | client |
| `d` | text ≤ 1,000 — what choosing it means | no | client |
| `rec` | yes/no — the recommended option, at most one per Question | no | client |

Each Question screen:

| Field | Type | Required | Who sees |
|---|---|---|---|
| `file` | bare file name ≤ 200 (no folders), unique in the page — also the name of its part | yes | portal |
| `cap` | text ≤ 300 | no | client |

## Limits and named checks

The schema holds every type and length above, the 50 Questions and the 1 to 20 options. What a schema cannot
say is in `checks.md`, as named checks:

| Check | Rule |
|---|---|
| `unique_question_id` | no two Questions share an `id` |
| `unique_option_v` | no two options of one Question share a `v` |
| `one_rec_max` | at most one option per Question has `rec: true` |
| `bare_file_names` | a screen `file` is a usable bare name (no folder, not `.` or `..`, no control character or `:`, not `publish`) and no two match, letter case aside |
| `one_hero_max` | at most one screen has `hero: true` |
| `unique_decision_id` | no two decisions share an `id` |
| `max_screenshots` | at most 30 screens in all, design and Questions together |
| `no_html_entities` | no HTML entity in a plain-text field |
| `screens_match_parts` | every named screen has a part, every part is named, and no part is sent twice (raises `screenshot_mismatch`) |

Each screenshot part is PNG, JPEG or WebP, at most 10 MB; a page Publish is at most 90 MB in all
(`payload_too_large`). Those are checked on the request, not in this schema.

## Light HTML

Fields typed "light HTML" keep only the tags and class in `light-html.json`. The Portal cleans them once, on
arrival. They may hold entities such as `&mdash;`; every other text field may not (`no_html_entities`).
