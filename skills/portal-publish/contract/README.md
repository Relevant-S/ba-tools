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
| `timeline-1.schema.json` | Since 1.6.0. The BA's Timeline page data for one product, sent to the Dashboard endpoint (it replaces Map and Board), JSON Schema draft 2020-12; since 1.8.0 it may carry `suggestion_status`, the BA's Accepted or Declined on Client suggestions; since 1.9.0 `upcoming`, the planned deadlines, releases and steps ("Coming up") |
| `timeline-1.md` | The same, readable |
| `clarification-1.schema.json` | The Clarification page Publish (one Round), JSON Schema draft 2020-12; since 1.7.0 a screen may carry its `figma` link (the "Open in Figma" button) |
| `clarification-1.md` | The same, readable |
| `publish-reply-1.schema.json` | The Portal's reply to a Publish, Dashboard or page form by `kind` (and its dry run; since 1.6.0 also the view of a `timeline/1` send; since 1.7.0 a page screen's `figma` link in the Client view) |
| `status-1.schema.json` | The Portal's reply to `GET /api/v1/status` |
| `answers-1.schema.json` | The Portal's reply to `POST /api/v1/answers/reserve`: a batch of sent Answers |
| `answers-2.schema.json` | Since 1.4.0. The reply to `POST /api/v1/answers/reserve` when the request accepts `answers/2`: `answers/1` plus `updates`, the Client's saves on Items (below); since 1.6.0 an item's `kind` may be `todo` |
| `answers-3.schema.json` | Since 1.8.0. The reply to `POST /api/v1/answers/reserve` when the request accepts `answers/3`: `answers/2` plus `suggestions`, the Client's suggestions from the Portal Timeline (below) |
| `reserve-request-1.schema.json` | Since 1.4.0. The optional body of `POST /api/v1/answers/reserve`: `{ accept: [...] }`, the batch versions the fetcher reads |
| `ack-request-1.schema.json` | The body of `POST /api/v1/answers/ack`: `{ batch_id }`. One ack confirms a batch's Answers and updates together |
| `ack-1.schema.json` | The Portal's reply to `POST /api/v1/answers/ack` |
| `connect-request-1.schema.json` | Since 1.5.0. The body of `POST /api/v1/connect`: `{ code, label }`, a one-time connect code and a name for the repo (below) |
| `connect-1.schema.json` | Since 1.5.0. The Portal's reply to `POST /api/v1/connect`: the code's project and a new key for it |
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
| `item` | `{ key, kind, title }`: `key` is the BA page's item key, the first 12 hex characters of `sha1("<kind>\|<title>")` (title trimmed, UTF-8), not the `dashboard/2` key; `kind` is `waiting` or `agenda`, and since 1.6.0 also `todo` (the BA's own to-dos on a `timeline/1` send); `title` ≤ 500 (as on `dashboard/2` items) |
| `note` | plain text, 1 to 2,000 characters, or `null` when only the tick changed |
| `resolved` | yes/no: the Resolved tick at that save (the latest save of an Item wins) |

Updates come in `sent_at` order, then `id`. With nothing to hand out (no Answers and no updates), `batch_id`
and `reserved_until` are `null` and both lists are empty. A batch always holds at least one Answer or one
update. The same `ack-request/1` (`batch_id`) confirms the Answers and the updates together.

## Client suggestions (since 1.8.0)

On the Portal Timeline a Client may suggest a new feature, a change, or say something is wrong (the Suggest
button). The suggestion shows on the chart at once, to everyone who can see the project, marked Suggested.

- **Hand-out.** A fetcher whose `accept` list holds `answers/3` gets `answers/3`: `answers/2` plus a required
  `suggestions` list (may be empty). Each suggestion is handed out once, held and confirmed like an Answer (the same
  `batch_id`, the same ack). A fetcher that does not accept `answers/3` gets `answers/2` or `answers/1` as before,
  and the suggestions wait for one that does.
- **One suggestion:** `id` (UUID v7), `sent_at` (UTC), `person` `{ name, email }`, `type` (`feature` · `change` ·
  `problem`), `feature` (the Timeline row's id, or `null` for a new feature in an area), `feature_name` (that row's label when it was sent, or `null`), `area` (≤ 300), `title`
  (1 to 120), `what` (plain text ≤ 5,000, one point per line, may be empty), `urgency` (`nice` · `soon` ·
  `blocking`), `link` (an `https://` link ≤ 2,000, or `null`). In `sent_at` order, then `id`.
- **The answer goes back in the next Timeline send**, as `timeline/1` `suggestion_status` (`timeline-1.md`). An id
  the Portal does not know is ignored.
- A suggestion is never changed or withdrawn once sent.

## The Timeline send (since 1.6.0)

`timeline/1` (`timeline-1.md`) is the BA's Timeline page data: area groups → areas → rows, with their changes
and bugs, to-dos, pins and releases. It goes to `POST /api/v1/publish/dashboard` like `dashboard/2`, and the
latest send of either kind is the project's Dashboard version. So a `timeline/1` send replaces Map and Board, and
a later `dashboard/2` send brings them back. `dashboard/1` and `dashboard/2` stay accepted.

- The send is the build's data with every field kept (clients see what the BA sees), except the BA page's own
  links: a feature's `clar` artifact link becomes `page`, the Portal page's slug; `pages`, `dashboardUrl` and
  `pins[].decided[].url` are left out. The envelope, `client_contacts` and `clarification_pages` are added.
- A Client may save a note or tick Resolved on any to-do of the latest send, including the BA's own (`todo`).
  Its key is the BA page's item key, as before, so `answers/2` hands it out with `item.kind` `todo`.
- An unknown version (`timeline/2`) is refused like any other, naming every accepted version:
  `timeline/2 is not accepted. This Portal accepts dashboard/1, dashboard/2, timeline/1.`

## Connecting a repo with a one-time code (since 1.5.0)

An Admin makes a connect code in the Portal (Admin → Projects → the project → Publishing → Connect a repo).
ba-setup swaps it for a key with `POST /api/v1/connect`. The request has **no** `Authorization` header: the code
is the proof.

`connect-request/1` (no `contract` field, like the ack request):

| Field | Type |
|---|---|
| `code` | 6 characters of `23456789ABCDEFGHJKMNPQRSTUVWXYZ` (no 0/O, 1/I/L), shown as `XXX-XXX`. The dash is optional and any case is fine: `K7P4XM`, `K7P-4XM` and `k7p-4xm` are the same code |
| `label` | 1 to 100 characters: the repo folder name, ` · `, and the BA's git `user.name` (just the folder when git has no name), e.g. `acme-docs · Vadim`. The Admin sees it under Connected repos |

The 200 reply is `connect/1`:

| Field | Type |
|---|---|
| `project` | `{ id, name }`: the project the code was made for (`id` is a UUID v7, `name` ≤ 200) |
| `key` | the new key, 43 characters of base64url. It opens the project for publish, fetch and status, like the project's own key. It is in this reply once: the Portal keeps only its hash |
| `key_last4` | the key's last 4 characters, as the Admin sees them under Connected repos |

Each connect makes a new key. Keys already in use keep working. A code works once and dies after 10 minutes.

Errors use the usual error envelope, `{ "error": { "code", "message" } }`:

- `connect_code_invalid` (400): the code is unknown, used, expired, or its project is archived. One code for
  all four, so a guesser learns nothing.
- `too_many_tries` (429): too many wrong codes from this caller. The `error` object also has
  `retry_after_s`, a whole number of seconds until the next try is allowed:
  `{ "error": { "code": "too_many_tries", "message": "…", "retry_after_s": 540 } }`.
- A body that is not `connect-request/1` → `bad_request` (400).

The codes and statuses in `errors.json` are the contract. Its messages are only a guide: the Portal may send its
own message text.

**Changing anything here is a contract change.** Add a new version for any field change (data-contract R8),
bump `contract_folder` in `index.json`, tag ba-tools `portal-contract-<version>`, and copy the folder into the
Portal again.

Tests: `uv run pytest` in `skills/portal-publish`.
