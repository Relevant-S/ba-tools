# portal-publish contract

The data contract between ba-tools and the Relevant Clients Portal. The portal-publish skill checks a send
against it before sending; the Portal checks it again on arrival. The Portal keeps an exact copy of this folder
in `portal/contract/`, with a `SOURCE` file naming the ba-tools tag and each file's SHA-256.

| File | What it is |
|---|---|
| `dashboard-1.schema.json` | The Dashboard Publish, JSON Schema draft 2020-12 |
| `dashboard-1.md` | The same, readable |
| `publish-reply-1.schema.json` | The Portal's reply to a Dashboard Publish (and its dry run) |
| `status-1.schema.json` | The Portal's reply to `GET /api/v1/status` |
| `index.json` | The accepted Publish versions and which schema checks each `contract` value |
| `checks.md` | Order of checks, result shape, and the named cross-field checks |
| `errors.json` | Every API error code, its HTTP status and default message |
| `light-html.json` | The tags and class kept in light-HTML fields |
| `fixtures/valid/` | Files that must pass |
| `fixtures/invalid/<case>/` | `input.json` must fail; `expected.json` gives the code and every (check, path) pair |

The codes and statuses in `errors.json` are the contract. Its messages are only a guide: the Portal may send its
own message text.

**Changing anything here is a contract change.** Add a new version for any field change (data-contract R8),
bump `contract_folder` in `index.json`, tag ba-tools `portal-contract-<version>`, and copy the folder into the
Portal again.

Tests: `uv run pytest` in `skills/portal-publish`.
