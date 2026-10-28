# portal-publish contract

The data contract between ba-tools and the Relevant Clients Portal. The portal-publish skill checks a send
against it before sending; the Portal checks it again on arrival. The Portal keeps an exact copy of this folder
in `portal/contract/`, with a `SOURCE` file naming the ba-tools tag and each file's SHA-256.

| File | What it is |
|---|---|
| `dashboard-1.schema.json` | The Dashboard Publish, JSON Schema draft 2020-12 |
| `dashboard-1.md` | The same, readable |
| `dashboard-2.schema.json` | The whole BA dashboard of one product (since 1.2.0), JSON Schema draft 2020-12 |
| `dashboard-2.md` | The same, readable |
| `clarification-1.schema.json` | The Clarification page Publish (one Round), JSON Schema draft 2020-12 |
| `clarification-1.md` | The same, readable |
| `publish-reply-1.schema.json` | The Portal's reply to a Publish, Dashboard or page form by `kind` (and its dry run) |
| `status-1.schema.json` | The Portal's reply to `GET /api/v1/status` |
| `answers-1.schema.json` | The Portal's reply to `POST /api/v1/answers/reserve`: a batch of sent Answers |
| `ack-request-1.schema.json` | The body of `POST /api/v1/answers/ack`: `{ batch_id }` |
| `ack-1.schema.json` | The Portal's reply to `POST /api/v1/answers/ack` |
| `index.json` | The accepted Publish versions and which schema checks each `contract` value |
| `checks.md` | Order of checks, result shape, and the named cross-field checks |
| `errors.json` | Every API error code, its HTTP status and default message |
| `light-html.json` | The tags and class kept in light-HTML fields |
| `fixtures/valid/` | Files that must pass |
| `fixtures/invalid/<case>/` | `input.json` must fail; `expected.json` gives the code and every (check, path) pair, and `"kind": "clarification"` for a page; a page case may add `parts.json` (see `checks.md` → Fixtures) |

The codes and statuses in `errors.json` are the contract. Its messages are only a guide: the Portal may send its
own message text.

**Changing anything here is a contract change.** Add a new version for any field change (data-contract R8),
bump `contract_folder` in `index.json`, tag ba-tools `portal-contract-<version>`, and copy the folder into the
Portal again.

Tests: `uv run pytest` in `skills/portal-publish`.
