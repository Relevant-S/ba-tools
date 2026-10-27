# Contract checks

How a Publish is checked. Both sides do exactly this: the portal-publish skill before it sends, the Portal
when a send arrives. Each side writes the checks once. Both run `fixtures/` in their tests and must get the
same result.

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
   `dashboard`). The accepted versions of that type are the entries of `index.json` → `accepted` that start with
   `<type>/`. If the document is an object whose `contract` is a string that is not one of them, the result is
   `contract_version_not_accepted` with one detail at `/contract`. Its message names the accepted versions:
   `dashboard/2 is not accepted. This Portal accepts dashboard/1.` Nothing else is checked.
   A `contract` that is missing or not a string is left to the schema of the newest accepted version.
2. **Schema** (`schema`). The document is checked against the schema named for its `contract` in
   `index.json` → `schemas`, with JSON Schema draft 2020-12 and format checks on. Every failure is listed.
   Any failure → `contract_invalid`, and the named checks do not run.
3. **Named checks.** Only on a document that passed the schema. All three run; every failure is listed.
   Any failure → `contract_invalid`.

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
- **Fields:** every string in the document, list entries included, except exactly these four:
  `features[].summary`, `items[].text` (light HTML — they may hold entities, and the Portal cleans them),
  `features[].clar_url` and `client_contacts[].email`.
- **Raises:** `contract_invalid`.
- **One detail per field:** `path` is the field; the message names it and the entity, for example
  `/features/0/title holds an HTML entity (&mdash;). This field is plain text: use the character itself.`

## Notes for both sides

- Patterns in the schemas are ASCII-only and are used only on fields of one fixed length (dates, times, Item
  `key`). Python's `$` also matches before a final line break; with a fixed length that cannot change the result.
- Python: `Draft202012Validator(schema, format_checker=FormatChecker())` from `jsonschema[format-nongpl]`.
- Portal: `Ajv2020` with `strict: true` and `allErrors: true`, `ajv-formats`, and `x-visibility` added with
  `addKeyword` and an enum meta-schema (`client`, `id`, `portal`, `admin`), so a schema with any other value does
  not compile.
