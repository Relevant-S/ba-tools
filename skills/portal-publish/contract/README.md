# portal-publish contract

The data contract between ba-tools and the Relevant Clients Portal. The portal-publish skill checks a send
against it before sending; the Portal checks it again on arrival. The Portal keeps an exact copy of this folder
in `portal/contract/`, with a `SOURCE` file naming the ba-tools tag and each file's SHA-256.

| File | What it is |
|---|---|
| `dashboard-1.schema.json` | The Dashboard Publish, JSON Schema draft 2020-12 |
| `dashboard-1.md` | The same, readable |
| `dashboard-2.schema.json` | The whole BA dashboard of one product (since 1.2.0), the list of its Clarification pages (since 1.3.0), and Item `hot`, Feature `stage_why` and `area_how`, open ticket `updated` (since 1.4.0, all optional), JSON Schema draft 2020-12 |
| `dashboard-2.md` | The same, readable |
| `clarification-1.schema.json` | The Clarification page Publish (one Round), JSON Schema draft 2020-12 |
| `clarification-1.md` | The same, readable |
| `publish-reply-1.schema.json` | The Portal's reply to a Publish, Dashboard or page form by `kind` (and its dry run) |
| `status-1.schema.json` | The Portal's reply to `GET /api/v1/status` |
| `answers-1.schema.json` | The Portal's reply to `POST /api/v1/answers/reserve`: a batch of sent Answers |
| `answers-2.schema.json` | Since 1.4.0. The reply to `POST /api/v1/answers/reserve` when the request accepts `answers/2`: `answers/1` plus `updates`, the Client's saves on Items (below) |
| `reserve-request-1.schema.json` | Since 1.4.0. The optional body of `POST /api/v1/answers/reserve`: `{ accept: [...] }`, the batch versions the fetcher reads |
| `ack-request-1.schema.json` | The body of `POST /api/v1/answers/ack`: `{ batch_id }`. One ack confirms a batch's Answers and updates together |
| `ack-1.schema.json` | The Portal's reply to `POST /api/v1/answers/ack` |
| `index.json` | The accepted Publish versions and which schema checks each `contract` value |
| `checks.md` | Order of checks, result shape, and the named cross-field checks |
| `errors.json` | Every API error code, its HTTP status and default message |
| `light-html.json` | The tags and class kept in light-HTML fields |
| `fixtures/valid/` | Files that must pass |
| `fixtures/invalid/<case>/` | `input.json` must fail; `expected.json` gives the code and every (check, path) pair, and `"kind": "clarification"` for a page; a page case may add `parts.json` (see `checks.md` → Fixtures) |

## Handing out Answers and updates (since 1.4.0)

`POST /api/v1/answers/reserve` may carry a body, `reserve-request/1`: `{ "accept": ["answers/1", "answers/2"] }`
(1 to 5 different versions; no `contract` field, like the ack request).

- No body, an empty body, or an `accept` list without `answers/2`: the Portal replies `answers/1` exactly as
  before. The Client's updates are not put in the batch: they wait for a fetcher that reads `answers/2`.
- `accept` holds `answers/2`: the reply is `answers/2`.

`answers/2` is `answers/1` plus a required `updates` list (may be empty). One entry per Client save on an Item's
Update box:

| Field | Type |
|---|---|
| `id` | the save's id, UUID v7 |
| `sent_at` | UTC time, exactly `YYYY-MM-DDTHH:MM:SS.sssZ` |
| `person` | `{ name ≤ 100, email ≤ 254 }` |
| `item` | `{ key, kind, title }`: `key` is the BA page's item key, the first 12 hex characters of `sha1("<kind>\|<title>")` (title trimmed, UTF-8), not the `dashboard/2` key; `kind` is `waiting` or `agenda`; `title` ≤ 500 (as on `dashboard/2` items) |
| `note` | plain text, 1 to 2,000 characters, or `null` when only the tick changed |
| `resolved` | yes/no: the Resolved tick at that save (the latest save of an Item wins) |

Updates come in `sent_at` order, then `id`. With nothing to hand out (no Answers and no updates), `batch_id`
and `reserved_until` are `null` and both lists are empty. A batch always holds at least one Answer or one
update. The same `ack-request/1` (`batch_id`) confirms the Answers and the updates together.

The codes and statuses in `errors.json` are the contract. Its messages are only a guide: the Portal may send its
own message text.

**Changing anything here is a contract change.** Add a new version for any field change (data-contract R8),
bump `contract_folder` in `index.json`, tag ba-tools `portal-contract-<version>`, and copy the folder into the
Portal again.

Tests: `uv run pytest` in `skills/portal-publish`.
