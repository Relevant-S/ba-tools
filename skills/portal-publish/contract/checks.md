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

1. **Version** (`contract_version`). Each endpoint takes one contract type (`POST /publish/dashboard` takes
   `dashboard`, `POST /publish/page` takes `clarification`). The accepted versions of that type are the
   entries of `index.json` → `accepted` that start with `<type>/`. If the document is an object whose
   `contract` is a string that is not one of them, the result is `contract_version_not_accepted` with one
   detail at `/contract`. Its message names the accepted versions:
   `dashboard/2 is not accepted. This Portal accepts dashboard/1.` Nothing else is checked.
   A `contract` that is missing or not a string is left to the schema of the newest accepted version.
2. **Schema** (`schema`). The document is checked against the schema named for its `contract` in
   `index.json` → `schemas`, with JSON Schema draft 2020-12 and format checks on. Every failure is listed.
   Any failure → `contract_invalid`, and the named checks do not run.
3. **Named checks.** Only on a document that passed the schema. Every named check of the contract type runs;
   every failure is listed. Any failure → `contract_invalid`.
   - `dashboard`: `unique_feature_id`, `unique_item_key`, `no_html_entities`.
   - `clarification`: `unique_question_id`, `unique_option_v`, `one_rec_max`, `bare_file_names`,
     `one_hero_max`, `max_screenshots`, `unique_decision_id`, `no_html_entities`.
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

### `no_html_entities`

- **Rule:** a plain-text field holds no HTML entity such as `&mdash;`, `&#8212;` or `&#x2014;`
  (data-contract R17). The pattern is `&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);`.
- **Fields:** every string in the document, list entries included, except exactly these. Light-HTML fields may
  hold entities, and the Portal cleans them; the others have a format that may hold `&`.
  - `dashboard`: `features[].summary`, `items[].text` (light HTML), `features[].clar_url` and
    `client_contacts[].email`.
  - `clarification`: `description`, `problem`, `solution`, `design.summary`, `design.detail`,
    `questions[].body`, `questions[].body2`, `questions[].snag` (light HTML), `url`, and the screen file
    names `design.screens[].file` and `questions[].screens[].file` (checked by `bare_file_names`).
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

### `unique_decision_id` (pages)

- **Rule:** no two decisions share an `id`.
- **Raises:** `contract_invalid`.
- **One detail per repeat:** `path` is the later decision's `id`; the message names both places, for example
  `Decision id "bank-only" is used twice: /decisions/0/id and /decisions/1/id`.

### `max_screenshots` (pages)

- **Rule:** at most 30 screens in the page, design and Questions together (data-contract §10 Limits). A schema
  cannot count across lists, so the screen lists have no `maxItems`.
- **Raises:** `contract_invalid`.
- **One detail in all:** `path` is the 31st screen in page order (design first, then each Question in order),
  for example `/questions/4/screens/0`; the message gives the total and the limit.

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
  reply or request, checked with the schema its `contract` names. A file with no `contract` field (the ack
  request) is matched by its file-name prefix: `ack-request-1…` → `ack-request/1`.
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
  cannot change the result — and on `slug`, which ends in `(?![\s\S])` ("nothing follows") instead of `$`.
- Python: `Draft202012Validator(schema, format_checker=FormatChecker())` from `jsonschema[format-nongpl]`.
- Portal: `Ajv2020` with `strict: true` and `allErrors: true`, `ajv-formats`, and `x-visibility` added with
  `addKeyword` and an enum meta-schema (`client`, `id`, `portal`, `admin`), so a schema with any other value does
  not compile.
