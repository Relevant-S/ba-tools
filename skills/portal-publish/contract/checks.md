# Contract checks

How a Publish is checked: a Dashboard (`dashboard/<n>`) or a Clarification page (`clarification/<n>`). Both
sides do exactly this: the portal-publish skill before it sends, the Portal when a send arrives. Each side
writes the checks once. Both run `fixtures/` in their tests and must get the same result.

## The result

A failed check gives one error code and a list of details:

```json
{ "code": "contract_invalid", "details": [{ "path": "/features/3/id", "check": "unique_feature_id", "message": "..." }] }
```

- `code` is one of the codes in `errors.json`.
- `path` is a JSON Pointer into the sent document (`/features/3/title`; `""` is the whole document). For a
  missing field it is the path the field should have had. For an unknown field it is the path of that field.
- `check` is `contract_version`, `schema`, or one of the named checks below.
- `message` is for people. Its wording may differ between the two sides; the code, check and path do not.

## Order

1. **Version** (`contract_version`). Each endpoint takes its contract types (`POST /publish/dashboard` takes
   `dashboard` and, since 1.6.0, `timeline`; `POST /publish/page` takes `clarification`). The accepted versions
   of an endpoint are the entries of `index.json` → `accepted` that start with one of its types and `/`, in
   `index.json` order. If the document is an object whose `contract` is a string that is not one of them, the
   result is `contract_version_not_accepted` with one detail at `/contract`. Its message names the accepted
   versions:
   `dashboard/3 is not accepted. This Portal accepts dashboard/1, dashboard/2, timeline/1.` Nothing else is
   checked.
   A `contract` that is missing or not a string is left to the schema of the **oldest** accepted version of
   the type (`dashboard/1`, `clarification/1`), so adding a version never changes how such a document fails.
2. **Schema** (`schema`). The document is checked against the schema named for its `contract` in
   `index.json` → `schemas`, with JSON Schema draft 2020-12 and format checks on. Every failure is listed.
   Any failure → `contract_invalid`, and the named checks do not run.
3. **Named checks.** Only on a document that passed the schema. Every named check of the contract type runs;
   every failure is listed. Any failure → `contract_invalid`.
   - `dashboard/1`: `unique_feature_id`, `unique_item_key`, `no_html_entities`.
   - `dashboard/2`, in this order: `unique_area_id`, `unique_feature_id`, `unique_topic_id`,
     `unique_item_key`, `unique_card_id`, `unique_release_name`, `unique_special`, `unique_ticket_in_list`,
     `unique_page_slug` (since 1.3.0), `known_area` (Features, then topics, then cards), `known_parent`, `known_card_feature`, `known_release`,
     `card_kind_fields`, `answered_in_range`, `no_html_entities`.
   - `timeline/1` (since 1.6.0), in this order: `unique_feature_id`, `unique_item_key`, `unique_pin_id`,
     `unique_page_slug`, `known_pin`, `known_page`, `unique_upcoming_id` (since 1.9.0), `known_feature` (since
     1.9.0), `figma_link` (since 1.10.0), `no_html_entities`.
   - `clarification`: `unique_question_id`, `unique_option_v`, `one_rec_max`, `bare_file_names`,
     `one_hero_max`, `max_screenshots`, `unique_decision_id`, `figma_link` (since 1.7.0), `no_html_entities`.
4. **Parts** (`screens_match_parts`) — pages only. Only on a page that passed steps 1 to 3, and only when the
   caller has the screenshot parts: the Portal always (the multipart parts except `publish`; its page check
   cannot be called without them); the skill does not run it, because it builds the parts from the page
   itself. Any failure → `screenshot_mismatch`.

## Named checks

### `unique_feature_id`

- **Rule:** no two Features share an `id` (data-contract R18, E5).
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later Feature's `id`; the message names both places, for example
  `Feature id "client-sign-in" is used twice: /features/2/id and /features/7/id`.

### `unique_item_key`

- **Rule:** no two Items share a `key` (data-contract R18, E5).
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later Item's `key`; the message names both places, for example
  `Item key "3f2a9c0d1e4b" is used twice: /items/5/key and /items/40/key`.

`dashboard/2` makes the Item key from `sha1("<kind>|<parent>|<title>")` (title trimmed, UTF-8, first 12 hex
characters), so two Items with one title under two parents do not clash. `dashboard/1` keeps
`sha1("<kind>|<title>")`.

### `unique_area_id`, `unique_card_id`, `unique_release_name` (dashboard/2)

- **Rule:** no two areas share an `id`; no two cards share an `id`; no two releases share a `name` (a card
  names its release by name).
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later one's `id` (or `name`); the message names both places, for
  example `Area id "ABC:Payouts" is used twice: /areas/1/id and /areas/4/id`,
  `Card id "c00012" is used twice: /cards/2/id and /cards/9/id` or
  `Release name "6.2" is used twice: /releases/0/name and /releases/2/name`.

### `unique_special` (dashboard/2)

- **Rule:** each `special` value (`no_area`, `not_linked`) is on at most one area.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later area's `special`, for example
  `The special area "no_area" is sent twice: /areas/1/special and /areas/2/special`.

### `unique_topic_id` (dashboard/2)

- **Rule:** no two topics share an `id`, and no topic has a Feature's `id`. An Item's `parent` names a Feature
  or a topic, so the two lists must not clash.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later topic's `id`, for example
  `Topic id "payouts" is used twice: /topics/0/id and /topics/3/id`; a topic with a Feature's id gives one
  detail at the topic's `id`: `Topic id "payouts" is also a Feature id: /features/2/id and /topics/0/id`.
  Repeats are listed first, then clashes with Features.

### `unique_ticket_in_list` (dashboard/2)

- **Rule:** a ticket `key` is in one ticket list at most once. The ticket lists are each area's
  `jira.open_tickets` and `jira.shipped`, and each Feature's, topic's and card's `tickets`. Two different
  lists may hold the same ticket.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** walking the lists in that order (areas, then Features, topics, cards), `path` is
  the later ticket's `key`; the message names both places, for example
  `Ticket "ABC-12" is in one list twice: /cards/2/tickets/0/key and /cards/2/tickets/2/key`.

### `unique_page_slug` (dashboard/2, since 1.3.0)

- **Rule:** a slug is in `clarification_pages` at most once. The field is optional; when it is missing, the
  check finds nothing.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later entry, for example
  `Page slug "probate-decisions" is listed twice: /clarification_pages/0 and /clarification_pages/2`.

### `known_area`, `known_parent`, `known_card_feature`, `known_release` (dashboard/2)

- **Rule:** every reference names something sent in the same Publish:
  - `known_area`: `features[].area`, `topics[].area` and `cards[].area` are area `id`s;
  - `known_parent`: `items[].parent` is a Feature `id` or a topic `id`;
  - `known_card_feature`: `cards[].feature`, when sent, is a Feature `id`;
  - `known_release`: `cards[].release`, when not `null`, is a release `name`.
- **Raises:** `contract_invalid`.
- **One detail per unknown reference:** `path` is the field, in list order; the message names it and the value,
  for example `/items/2/parent names a Feature or topic "no-such-feature" that is not in this Publish.`

### `timeline/1` checks (since 1.6.0)

The rows of a `timeline/1` are walked in order: each group, each of its areas, each of its `features`. A row's
path is `/groups/<g>/areas/<a>/features/<i>`.

- **`unique_feature_id`:** no two rows share an `id`, across the whole send. One detail per repeat at the later
  row's `id`, naming both places, for example
  `Feature id "otp" is used twice: /groups/0/areas/0/features/0/id and /groups/0/areas/1/features/0/id`.
- **`unique_item_key`:** no two to-dos share a `key`, across the whole send (rows in order, each row's `todos`
  in order). One detail per repeat at the later `key`, naming both places (`To-do key "…" is used twice: …`).
- **`unique_pin_id`:** no two pins share an `id`. One detail per repeat at the later `pins/<n>/id`.
- **`unique_page_slug`:** as for `dashboard/2`, on `clarification_pages`.
- **`known_pin`:** a row's `askedIn`, then each of its `requests[].askedIn` in order, names a pin `id` of the
  send. One detail per unknown one at that `askedIn`, naming the value.
- **`known_page`:** only when `clarification_pages` is sent: a row's `page` is one of its slugs. One detail per
  unknown one at that `page`.
- **`unique_upcoming_id`** (since 1.9.0): no two `upcoming` items share an `id`. One detail per repeat at the later
  `upcoming/<n>/id`, naming both places (`Upcoming id "…" is used twice: …`).
- **`known_feature`** (since 1.9.0): each `upcoming` item's `needs`, in order, then its `after`, names a row `id`
  of the send. One detail per unknown one at that place (`/upcoming/<n>/needs/<j>` or `/upcoming/<n>/after`),
  naming the value.
- **`figma_link`** (since 1.10.0): a row's `figma`, then each of its `requests[].figma` in order, follows the
  `figma_link` rule below. One detail per bad link at that `figma` (`/groups/<g>/areas/<a>/features/<i>/figma` or
  `…/requests/<j>/figma`), with the same message as for a page screen.
- **`no_html_entities`:** below.
- **Raises:** `contract_invalid`.

### `card_kind_fields` (dashboard/2)

- **Rule:** a card's fields match its `kind`: a `feature` card has `feature` and no `epic`; an `epic` card has
  `epic` and no `feature`; an `other` card has neither.
- **Raises:** `contract_invalid`.
- **One detail per wrong field:** per card in order, `feature` first then `epic`; `path` is the missing or
  extra field, for example `/cards/0/feature is missing: a feature card names its feature.` or
  `/cards/4/epic is not allowed on a other card.`

### `answered_in_range` (dashboard/2)

- **Rule:** a Feature's `answered.done` is at most its `answered.total`.
- **Raises:** `contract_invalid`.
- **One detail per Feature:** `path` is `answered/done`, for example
  `/features/0/answered/done is 6, more than the total of 5.`

### `no_html_entities`

- **Rule:** a plain-text field holds no HTML entity such as `&mdash;`, `&#8212;` or `&#x2014;`
  (data-contract R17). The pattern is `&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);`.
- **Fields:** every string in the document, list entries included, except exactly these. Light-HTML fields may
  hold entities, and the Portal cleans them; the others have a format that may hold `&`.
  - `dashboard`: `features[].summary`, `items[].text` (light HTML), `features[].clar_url` and
    `client_contacts[].email`. In `dashboard/2` also `jira_base` and `areas[].jira.search` (links) and every text copied from Jira,
    because the BA does not write it and cannot fix it, and the Portal shows it as escaped plain text, so an
    entity there shows as its letters and never as markup: `areas[].name`, `areas[].jira.description`, the
    `summary` of `jira.shipped[]` and the `summary` and `status` of `jira.open_tickets[]`, `releases[].name`,
    `cards[].release`, `cards[].title` (an epic's name, or the Feature title), and the `summary`, `status`
    and `assignee` of every ticket of `features[]`, `topics[]` and `cards[]`. BA-written text (Feature,
    topic and Item titles, `short`, `open`, `who`, `how_to_send`) is still checked.
  - `timeline/1`: the links `product.workLink`, `groups[].areas[].link.url` and every work item's `url`
    (of rows and of their `requests`), `client_contacts[].email`, and the text copied from the tracker: every
    work item's `title` and `status`, and `releases[].name`. Since 1.10.0 also the Figma links: a row's `figma`
    and each `requests[].figma` (checked by `figma_link`). Everything else, BA-written, is checked — `kind`,
    `asked` and `figmaWhere` included.
  - `clarification`: `description`, `problem`, `solution`, `design.summary`, `design.detail`,
    `questions[].body`, `questions[].body2`, `questions[].snag` (light HTML), `url`, the screen file
    names `design.screens[].file` and `questions[].screens[].file` (checked by `bare_file_names`), and since
    1.7.0 the screen links `design.screens[].figma` and `questions[].screens[].figma` (checked by `figma_link`).
- **Raises:** `contract_invalid`.
- **One detail per field:** `path` is the field; the message names it and the entity, for example
  `/features/0/title holds an HTML entity (&mdash;). This field is plain text: use the character itself.`

### `unique_question_id` (pages)

- **Rule:** no two Questions share an `id` (data-contract R19, E5).
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later Question's `id`; the message names both places, for example
  `Question id "payout-day" is used twice: /questions/1/id and /questions/3/id`.

### `unique_option_v` (pages)

- **Rule:** no two options of one Question share a `v` (data-contract R19, E5). Two Questions may each have an
  option with the same `v`.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later option's `v`; the message names both places, for example
  `Option value "monday" is used twice in one Question: /questions/2/options/0/v and /questions/2/options/2/v`.

### `one_rec_max` (pages)

- **Rule:** at most one option per Question has `rec: true`. `rec: false` does not count.
- **Raises:** `contract_invalid`.
- **One detail per extra:** `path` is the second (third …) recommended option's `rec`; the message names the
  first one too, for example
  `A Question may have at most one recommended option: /questions/0/options/0/rec and /questions/0/options/1/rec`.

### `bare_file_names` (pages)

- **Rule:** every screen `file` (in `design.screens[]` and every `questions[].screens[]`) is a bare file name,
  and no file name is used twice in the page (data-contract §10). The name is also the screenshot's part name,
  so it must say exactly one file. A name is refused when it:
  - holds `/` or `\` (a folder);
  - is `.` or `..`;
  - holds a control character (U+0000 to U+001F, U+007F) or `:`;
  - is `publish` in any letter case (the name of the part that holds the page);
  - equals a name seen earlier in the page, letter case aside (lower-cased with Python `str.lower()` /
    JavaScript `toLowerCase()`), so `Shot.png` and `shot.png` clash.
- **Raises:** `contract_invalid`.
- **One detail per screen:** walking the screens in page order (design first, then each Question in order),
  the first rule a name breaks gives one detail at its `file`, naming the value. A repeat gives the detail at
  the later `file`, and the message names both places, for example
  `File name "payouts-overview.png" is used twice (letter case aside): /design/screens/0/file and
  /questions/4/screens/0/file`.

### `one_hero_max` (pages)

- **Rule:** at most one screen in the page has `hero: true`. `hero: false` does not count.
- **Raises:** `contract_invalid`.
- **One detail per extra:** in page order, `path` is the second (third …) hero's `hero`; the message names
  the first one too.

### `max_screenshots` (pages)

- **Rule:** at most 30 screens in the page, design and Questions together (data-contract §10 Limits). A schema
  cannot count across lists, so the screen lists have no `maxItems`.
- **Raises:** `contract_invalid`.
- **One detail in all:** `path` is the 31st screen in page order (design first, then each Question in order),
  for example `/questions/4/screens/0`; the message gives the total and the limit.

### `unique_decision_id` (pages)

- **Rule:** no two decisions share an `id`.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later decision's `id`; the message names both places, for example
  `Decision id "bank-only" is used twice: /decisions/0/id and /decisions/1/id`.

### `figma_link` (pages since 1.7.0; Timeline rows and their changes since 1.10.0)

- **Rule:** a screen's `figma` (in `design.screens[]` and every `questions[].screens[]`) starts with exactly
  `https://www.figma.com/` (lower case, `https`, with `www.`), and holds:
  - no control character or space of any kind. The list is explicit, so both sides agree: U+0000 to U+0020,
    U+007F to U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F, U+3000, U+FEFF;
  - no HTML entity (the `no_html_entities` pattern, as `&amp;` or `&#38;`). A plain `&` is fine:
    `?node-id=1-2&t=x` passes. `no_html_entities` itself skips the link, so this check is the one that refuses it.

  An empty value fails the schema first (`minLength` 1).
- **Raises:** `contract_invalid`.
- **One detail per screen:** in page order (design first, then each Question in order), `path` is the screen's
  `figma`, for example `/questions/2/screens/0/figma is not a Figma link: it must start with
  https://www.figma.com/ and hold no space or HTML entity.`

### `screens_match_parts` (pages, step 4)

- **Rule:** every named screen has a part of that name, and every part is named by a screen (data-contract E4).
  The parts are the screenshot parts only: the caller leaves out the `publish` part.
- **Raises:** `screenshot_mismatch`.
- **One detail per gap:** a named file with no part → `path` is that screen's `file`, and the message names the
  file. A part no screen names → `path` is `""` (the whole document), and the message names the part. A part
  name sent more than once → one more detail at `""`, naming the part.

## Fixtures

- `fixtures/valid/*.json` must pass. A file whose `contract` is in `index.json` → `accepted` is a Publish:
  it is checked as that contract type, and a page uses its own file names as the parts. Any other file is a
  reply or request, checked with the schema its `contract` names. A file with no `contract` field (the ack,
  reserve and connect requests) is matched by its file-name prefix: `ack-request-1…` → `ack-request/1`,
  `reserve-request-1…` → `reserve-request/1`, `connect-request-1…` → `connect-request/1`.
- `fixtures/invalid/<case>/input.json` must fail. `expected.json` gives the code and every (check, path) pair;
  both sides compare that exact set. It may say `"kind": "clarification"` (no `kind` means `dashboard`). A page
  case may hold `parts.json`, the list of part names sent with it; without it the page's own file names are the
  parts.
- A broken reply or request is an invalid case too. Its `expected.json` has `contract` (the schema it is
  checked with, for example `answers/1`) and the (check, path) pairs, and no `code`.

## Notes for both sides

- A `false` field schema ("this field may not be here") must give the field's path on both sides. Ajv does;
  jsonschema gives an empty path, so `checks.py` reads each `false` under `properties` as `{"not": {}}`, which
  means the same.
- Patterns in the schemas are ASCII-only. They are used on fields of one fixed length (dates, times, Item
  `key`, media addresses) — Python's `$` also matches before a final line break, and with a fixed length that
  cannot change the result — and on `slug` and the Jira ticket `key` of `dashboard/2`, which end in
  `(?![\s\S])` ("nothing follows") instead of `$`.
- A `dashboard/2` send may carry `clarification_pages` (since 1.3.0): the slugs of every Clarification page of
  this Portal project that is still in the repo. The Portal hides the project's other pages and lists them in
  the reply's `pages_removed` (`{ slug, title }`), on a dry run too. Without the field no page is touched.
- Since 1.4.0 a `dashboard/2` send may carry Item `hot`, Feature `stage_why` and `area_how`, and open ticket
  `updated`. All are optional; no named check is added. `stage_why` and `area_how` follow the plain-text
  rule (no HTML entities, check `no_html_entities`). `answers/2` (and its `updates`) is checked by its schema
  only; its "a batch holds at least one Answer or one update" rule is a `not`, so every checker reports it at
  one path: `""` (the whole reply).
- Since 1.5.0 `connect-request/1` and `connect/1` (connect a repo with a one-time code) are checked by their
  schemas only. The code's pattern ends in `(?![\s\S])` like the slug, since a code is 6 or 7 characters.
- The reply to a `dashboard/2` send counts `areas`, `topics`, `cards` and `tickets` too. `tickets` counts the
  tickets on Board cards only (all `cards[].tickets` together), not the Feature, topic or area ticket lists.
- Since 1.6.0 `POST /publish/dashboard` also takes `timeline/1`. A missing or non-string `contract` is still
  checked with `dashboard/1`, the oldest version the endpoint takes. `timeline/1` has no light-HTML field and no
  null field. Its reply counts (each up to 1,000,000) `features` (rows plus their changes and bugs), `items` (to-dos),
  `client_contacts`, `areas` and `pins`, and a dry run's `client_view` is `client_timeline_1`. `answers/2` takes
  the item kind `todo` (a to-do of a `timeline/1` send).
- Since 1.8.0 `answers/3` (Client suggestions from the Portal Timeline) is checked by its schema only, like
  `answers/2`; its "a batch holds at least one Answer, update or suggestion" rule is a `not` at path `""`. A
  suggestion's `link` is `https://` only (the `workLink` pattern). `timeline/1` may carry `suggestion_status`
  (`[{ id, status, reason }]`, the BA's Accepted or Declined); no named check is added, and `reason` follows the
  plain-text rule (`no_html_entities`). An id the Portal does not know is ignored, not refused.
- Since 1.9.0 `timeline/1` may carry `upcoming` (planned deadlines, releases and steps: "Coming up"), and
  `client_timeline_1` with it. Two named checks are added: `unique_upcoming_id` and `known_feature`. "Both `date`
  and `after`" is a schema rule (a `not`), reported at the item. Its texts follow the plain-text rule
  (`no_html_entities`).
- Since 1.10.0 a `timeline/1` row may carry `kind` (text ≤ 40), `asked` (text ≤ 2,000), `figma` (a Figma link
  ≤ 2,000) and `figmaWhere` (text ≤ 500), and each of its `requests` `figma` and `figmaWhere`; `client_timeline_1`
  carries them as sent. The `figma_link` check covers them. All four are optional, so a 1.9.0 send still passes.
- Python: `Draft202012Validator(schema, format_checker=FormatChecker())` from `jsonschema[format-nongpl]`.
- Portal: `Ajv2020` with `strict: true` and `allErrors: true`, `ajv-formats`, and `x-visibility` added with
  `addKeyword` and an enum meta-schema (`client`, `id`, `portal`, `admin`), so a schema with any other value does
  not compile.
