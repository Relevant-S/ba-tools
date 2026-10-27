---
name: portal-publish
description: Send the project's Dashboard to the Relevant Clients Portal, on purpose and checked — build it from docs/BA/dashboard.yaml, check it against the Portal's data contract, show the BA exactly what the Client will read (the Portal's own dry run), and send only after the BA says yes. Use when the BA says "publish to the portal", "send the dashboard to the client", "portal-publish dashboard", or after ba-dashboard publishes on a project whose profile has tools.portal. `portal-publish page <slug>` (Clarification pages) is not built yet.
---

# portal-publish

**What it does.** The Client cannot open the project repo. This skill puts the Dashboard in front of the Client
in the Relevant Clients Portal — only when the BA decides, and with nothing internal in it. The Portal checks
every send again and logs it at **Admin → Projects → the Project → Publishing**.

**Two commands with the BA's yes in between.** The shell cannot wait for typed input, so:

1. `dashboard plan` builds, checks and sends a **dry run**. The Portal stores and logs nothing on a dry run.
   It answers with the Client's view, which you show the BA.
2. The BA says yes or no.
3. Yes → `dashboard send`. No → `dashboard discard`.

```
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard plan [--refresh]
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard send --payload <file>
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py dashboard discard --payload <file>
```

`<skills>` = the folder this skill is installed in, one level up. Run from the project root (or add
`--root <project>`). Each command prints one JSON line: `ok: true` with the result, or `ok: false` with
`error` — already worded for the BA.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. No passing
  stamp → `ba-setup check`.

## Settings

| Setting | Where | When it is missing |
|---|---|---|
| The Portal address | `tools.portal.url` in `docs/BA/specs/.ba-profile.yml` | stop: run `ba-setup project` |
| The Publish key | `PORTAL_PUBLISH_KEY=<key>` in `.env` at the repo root | stop: run `ba-setup project` |
| `.env` kept out of git | `.gitignore` lists `.env`, and `.env` is not committed | stop: add it to `.gitignore` (and `git rm --cached .env` if it was committed) |
| Client contacts | `tools.client_contacts` in the profile (`name`, `email`, `slack`) | falls back to `client_owners` in `docs/BA/dashboard-slack.yaml` (names only); with neither, a warning |

The script checks all of these itself, before it builds or sends anything. **Never print, echo or paste the
key.** Never open `.env` to show it. The Publish key is one per Project: an Admin sees it once in the
Portal at Admin → Projects → the Project → Publishing, and "Regenerate key" there replaces it.

## Run

1. **`dashboard plan`** (add `--refresh` only when the BA asks for it, or says yes to the stale-Jira
   warning). It:
   - runs `ba-dashboard`'s `dashboard.py build`, then `map/build.py`, so stages, areas and releases are current;
   - makes the payload — only the fields the contract names. A Feature or Item with `client: false` is left
     out, and so are the Items of a hidden Feature. `client_s` replaces `s`. To-dos and `done` Items stay in
     the repo;
   - checks it against the contract (`checks.py`). A failure names the file, the row and the field;
   - sends it to the Portal as a dry run, and writes the payload to a temp file outside the repo.
2. **Show the BA, word for word:**
   - every line of `warnings` (stale Jira files, no Client contacts);
   - `client_list` — every Feature (title, short label, summary, stage, open questions, its Clarification
     page), the Items grouped as "Waiting on you" and "Next-call agenda", and the Client contacts' names.
     It comes from the Portal's own dry-run reply. Never rebuild it, reorder it or work out "Waiting on you"
     yourself;
   - `left_out` as one line: "Left in the repo: N Features and N Items (client: false, done, to-dos)".
3. **Ask one question:** "Send this to the Client?" If `warnings` has the no-contacts warning, the same
   question also asks whether to go on without contacts. Wait for the answer.
4. **Yes** → `dashboard send --payload <the payload path from plan>`. It re-checks the file, sends the same
   bytes for real and deletes the file. `send` and `discard` only take a `portal-publish-*.json` file in the
   system temp folder — the path `plan` printed.
   **No** (or anything but a clear yes) → `dashboard discard --payload <path>`. Nothing is sent.
5. **Report** `report` from `send`: what was sent (the Dashboard; counts of Features, Items and Client
   contacts), the Portal's `publish_id` and its confirmation time (`received_at`, UTC). The BA can see the
   new row at Admin → Projects → the Project → Publishing.

If the BA edits `dashboard.yaml` after `plan`, discard and run `plan` again — `send` sends what `plan` built.

## When it stops

Show `error` as it is; it already says what to do. Nothing was sent in these cases, except the "may have arrived" row.

| Case | What the BA sees |
|---|---|
| No `tools.portal`, no `.env`, no key | "… Run `ba-setup project` …" |
| `.env` not ignored by git | ".env is not ignored by git …" |
| The build fails | "dashboard.py build failed: …" or "map/build.py failed: …" |
| The local check fails | one line per problem: `docs/BA/dashboard.yaml → features 'Sign-up' → area: …` |
| The Portal refuses | "The Portal refused the send (code): its message", each field it named, then the next step. Codes: `invalid_key` (wrong key), `project_archived`, `contract_invalid`, `contract_version_not_accepted`, `payload_too_large` |
| The Portal is down or the address is wrong | "The Portal is not reachable at <url>" |
| The real send went out but no reply came back (timeout, dropped connection) | "… it may have arrived …": check Admin → Projects → the Project → Publishing before sending again. The payload file is kept, so `send` can be run again with it if the send is not there. This is the one case where something may have been sent. |
| A reply the skill does not understand (for example an older Portal) | "The Portal's reply was not understood (HTTP <n>)" |

## Not built yet

`portal-publish page <slug>` (a Clarification page) answers "not built yet". It comes with the Clarification
pages in the Portal.

## Files

- `publish.py` — the commands above.
- `checks.py` and `contract/` — the data contract both sides check against. Do not edit them here; a contract
  change is its own ba-tools change, copied to the Portal.
- `tests/` — `uv run pytest` in this folder.
