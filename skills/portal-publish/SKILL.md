---
name: portal-publish
description: Send the project's Dashboard, or one Clarification page with its screenshots, to the Relevant Clients Portal, on purpose and checked — build it from docs/BA/dashboard.yaml or docs/BA/clarifications/<slug>-decisions.yaml, check it against the Portal's data contract, show the BA exactly what the Client will read (the Portal's own dry run), and send only after the BA says yes. Use when the BA says "publish to the portal", "send the dashboard to the client", "send this page to the client", "portal-publish dashboard", "portal-publish page <slug>", or after ba-dashboard or clarification-page publishes on a project whose profile has tools.portal.
---

# portal-publish

**What it does.** The Client cannot open the project repo. This skill puts the Dashboard, or one Clarification
page, in front of the Client in the Relevant Clients Portal — only when the BA decides, and with nothing
internal in it. The Portal checks every send again and logs it at **Admin → Projects → the Project →
Publishing**. The Dashboard steps come first below; the page steps are in "A Clarification page".

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

## A Clarification page — `page <slug>`

Same settings, same Step 0, same two steps with the BA's yes in between.

```
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page plan <slug>
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page send --payload <file>
uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py page discard --payload <file>
```

`<slug>` is the `slug:` line of the page YAML (`page <slug>` alone does the same as `page plan <slug>`).

1. **`page plan <slug>`.** It:
   - finds `docs/BA/clarifications/<slug>-decisions.yaml`, else `<slug>.yaml`, and stops if the YAML's `slug:`
     is not `<slug>`;
   - runs clarification-page's `scripts/_fixyaml.py` on it first. That script quotes values holding a colon, in
     the BA's file. When it changed lines, the first warning says so: the BA commits the file with the page;
   - stops if the page has no `round:` line (the Round label the Client reads);
   - builds the page from the fields the contract names, and nothing else. Old `settled:` lines become
     decisions with no date and no person. `spec`, `events`, `figma_file`, `node`, `frame`, `spec_ref` and every
     other internal field stay in the repo and are listed in `left_out`. A placeholder `url` (like
     `https://claude.ai/artifact/<the page id>`) is left out with a warning; the page still sends;
   - collects every screenshot the page names (`src`, relative to the YAML's folder). Each goes as its bare
     file name; a second file with the same name goes as `name-2.png`, then `-3` …;
   - checks it all: the contract (at most 50 Questions, 30 screenshots), each screenshot there, PNG, JPEG or
     WebP, at most 10 MB, and at most 90 MB in all. A failure names the YAML file, the row and the field;
   - sends a **dry run** (multipart: the page JSON, then one part per screenshot). The Portal stores and logs
     nothing. The payload file in temp holds the page JSON and each screenshot's path and checksum — never the
     screenshots themselves.
2. **Show the BA, word for word:** every line of `warnings`; `client_view` — the page name, the Round label,
   whether it is a new Round or replaces one, each Question with its options and the recommended one, the
   settled decisions and the counts. It comes from the Portal's own dry run: never rebuild or reorder it.
   Then `left_out` as one line: "Left in the repo: <the fields, comma-separated>".
3. **Ask one question:** "Send this page to the Client?" Wait for the answer.
4. **Yes** → `page send --payload <the payload path from plan>`. It re-reads every screenshot; if one changed
   since `plan`, it stops ("run `page plan` again"). Then it sends the same page for real and deletes the file.
   **No** (or anything but a clear yes) → `page discard --payload <path>`. Nothing is sent.
5. **Report** `report` from `send`: the page, the Round label, new Round or replaced, the counts of Questions
   and screenshots, the Portal's `publish_id` and its confirmation time (`received_at`, UTC). The BA sees the
   row at Admin → Projects → the Project → Publishing.

If the BA edits the YAML after `plan`, discard and run `plan` again — `send` sends what `plan` built.

**When a page send stops**, show `error` as it is. Besides the cases in the table above:

| Case | What the BA sees |
|---|---|
| No YAML for the slug | "No page YAML for '<slug>'. Looked for … and …" |
| The YAML's `slug:` is different | "… has slug 'a', but you asked for 'b' …" |
| No `round:` line | "… has no `round:` line …" |
| A screenshot is missing, not PNG / JPEG / WebP, or over 10 MB | `docs/BA/clarifications/<file> → design.screens[1] → src: …` |
| Over 90 MB in all | "… the Portal takes at most 90 MB in one send …" |
| The Round already has answers (`round_has_answers`) | "Round <label> already has answers — give it a new round key", then: change `store_key` (and the round label) and run `page plan` again |
| `screenshot_mismatch` | a named screenshot did not arrive, or an unnamed one did; run `page plan` again |
| `contract_invalid`, `project_archived`, `payload_too_large`, `invalid_key` | the Portal's message, each field it named, then the next step |
| A screenshot changed between `plan` and `send` | "The screenshot … changed (or is gone) since `page plan` …" |

## Files

- `publish.py` — the commands above (`dashboard …` and `page …`).
- `checks.py` and `contract/` — the data contract both sides check against. Do not edit them here; a contract
  change is its own ba-tools change, copied to the Portal.
- `tests/` — `uv run pytest` in this folder.
