---
name: fetch-portal
description: Bring the Client's Answers from the Relevant Clients Portal into the repo — one intake file per Clarification page at docs/BA/intake/YYYY-MM-DD-HHMM-portal-<slug>.md, for the /intake-and-triage skill to process. Each sent Answer comes once. Use when the BA says "fetch portal answers", "get the answers from the portal", "fetch-portal", when the Portal's Publishing tab shows Answers waiting to be fetched, or when a clarification page's answers come back on a project whose profile has tools.portal. Companion to /fetch-fireflies, /fetch-gmail and /fetch-slack — same target folder, same intake-file shape, different source (`source: portal`).
---

# fetch-portal

**What it does.** Clients answer Clarification pages in the Relevant Clients Portal. This skill pulls the sent
Answers into `docs/BA/intake/`, one file per page, so `/intake-and-triage` can turn them into spec changes like
email and Slack. The Portal hands each sent Answer out once. The Answers stay in the Portal afterwards.

**How the hand-out works (two steps, so nothing is lost).** The script first asks the Portal to *reserve* the
new Answers (it holds them for 10 minutes). It writes the files under a `.tmp` name. Only when every file is on
disk does it *ack* — tell the Portal "got them" — and then gives the files their real names. If anything fails in
between, the Answers are not lost: the next run finishes the job, or the Portal hands them out again.

```
uv run --project <skills>/fetch-portal python <skills>/fetch-portal/fetch.py
```

`<skills>` = the folder this skill is installed in, one level up (normally the project's `.claude/skills/`).
Run from the project root, or add `--root <project>`. `--help` prints a short plain-text description (not JSON)
and runs nothing. It prints one JSON line: `ok`, `files` (the intake files
written, as repo paths) and `message` — or `ok: false` and `error`. Both are already worded for the BA.

fetch-portal needs the `portal-publish` skill installed next to it: it checks every reply with that skill's
contract (`portal-publish/checks.py`, `portal-publish/contract/`). `install.py` copies both.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. No passing
  stamp → `ba-setup check`.

## Settings

The same settings as `portal-publish`:

| Setting | Where | When it is missing |
|---|---|---|
| The Portal address | `tools.portal.url` in `docs/BA/specs/.ba-profile.yml` | stop: run `ba-setup project` |
| The Publish key | `PORTAL_PUBLISH_KEY=<key>` in `.env` at the repo root | stop: run `ba-setup project` |
| `.env` kept out of git | `.gitignore` lists `.env`, and `.env` is not committed | stop: add it to `.gitignore` (and `git rm --cached .env` if it was committed) |

`tools.portal.url` must start with `https://`. Plain `http://` is allowed only for localhost, 127.0.0.1,
`*.localhost` and `*.test`. The script checks all of this itself before it asks the Portal anything. **Never
print, echo or paste the key.** Never open `.env` to show it. An Admin finds the key in the Portal at
Admin → Projects → the Project → Publishing.

## Run

1. Run the command above.
2. **`ok: true`** → show `message` as it is. It lists each file written with its page and number of Answers,
   like this:

   ```
   Wrote 2 intake files:
     - docs/BA/intake/2026-10-27-1100-portal-merchant-payouts.md (Merchant payouts, 2 answers)
     - docs/BA/intake/2026-10-27-1100-portal-statements.md (Statements, 1 answer)
   ```

   or "No new answers since 2026-10-27 11:00 UTC." (or "No new answers. None have been fetched yet.").
3. If `files` is not empty, ask one question:

   ```
   Run /intake-and-triage now? [Y/n]
   ```

   On `Y`: invoke `/intake-and-triage`. On `n`: stop.
4. **`ok: false`** → show `error` as it is and stop. Do not retry in a loop.

Never commit a `.tmp` or `.complete` file in `docs/BA/intake/`. They belong to a fetch that is not finished yet;
the next run finishes it. Triage lists only `*.md`, so it never reads them. A `portal-<batch>.complete` marker is
written only once every page of a batch is on disk; a batch without it was cut off mid-write and is deleted,
never confirmed, so its Answers come again after the hold (about 10 minutes).

## The intake file

One file per Clarification page, named `YYYY-MM-DD-HHMM-portal-<slug>.md` from the fetch time (UTC). If the name
is taken, `-2`, `-3` … is added. All times end in "UTC". Answers keep the order the Portal sent (page, Round,
Question position, send time).

```markdown
---
source: portal
date: 2026-10-27
project: 'Sample'
page: 'merchant-payouts'
page_title: 'Merchant payouts'
rounds:
  - key: 'merchant-payouts-v7'
    label: 'Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6'
    published: '2026-10-20 08:00 UTC'
participants:
  - 'Sample Client <sample.client@example.com>'
answer_count: 1
first_answer: '2026-10-26 14:03 UTC'
last_answer: '2026-10-26 14:03 UTC'
fetched_at: '2026-10-27 11:00 UTC'
processed: false
---

# Merchant payouts (portal answers)

**Project:** Sample
**Rounds:** Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6 (published 2026-10-20 08:00 UTC)
**Answers:** 1
**Fetched:** 2026-10-27 11:00 UTC

## Answers

### payout-day — Sample Client — 2026-10-26 14:03 UTC

**Round:** Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6 (published 2026-10-20 08:00 UTC)
**From:** Sample Client <sample.client@example.com>
**Answer id:** 019a2b90-0a1b-7c2d-8e3f-405162738495
**Question:** Which day of the week should merchants be paid?
**Option:** Every Friday (`friday`)
**Note:**

    Friday suits our cash flow better.

Replaces the answer sent 2026-10-22 09:12 UTC by Sample Client:
- Earlier answer id: 019a2a01-9f8e-7d6c-8b5a-493827161504
- Earlier option: Every Monday (`monday`)
- Earlier note: none
```

- The heading of each Answer is `### <Question id> — <person> — <send time> UTC`. The Question id is the one in
  the clarification page's YAML, so triage can match it.
- `participants` lists everyone who sent an Answer, removed people included.
- A note is kept whole and indented 4 spaces. "none (note only)" means the person sent a note and no option.
- "Replaces the answer sent …" appears when the person changed an earlier Answer. The earlier option and note
  follow. Treat the new Answer as the one that counts.

## When it stops

Show `error` as it is; it says what to do. In every case the Answers are safe in the Portal.

| Case | What the BA sees | Files |
|---|---|---|
| No `tools.portal`, no `.env`, or no key | "… Run `ba-setup project` …" | nothing written |
| The profile is not valid YAML, or not laid out as a profile | "… could not be read …" or "… is not laid out as a project profile … Run `ba-setup project`" | nothing written |
| `portal-publish` is not installed next to fetch-portal | "fetch-portal needs the portal-publish skill next to it … Install ba-tools again" | nothing written |
| git is not installed | "git is not installed (or not on PATH)" | nothing written |
| The folder is not a git repository | "… is not a git repository … Run fetch-portal from the project repo" | nothing written |
| `.env` not ignored by git | ".env is not ignored by git …" | nothing written |
| Wrong key | "This key is not valid for this Project" and where to get the right one | nothing written |
| Portal not running or wrong address | "The Portal is not reachable at <url>"; if it timed out, Answers it set aside come again after the hold (about 10 minutes) | nothing written |
| A reply that does not match the contract | "The Portal's reply was not understood (HTTP <n>)" — maybe an older Portal | nothing written, nothing confirmed |
| The ack got no reply (3 tries) | the files stay as `.tmp`; "the next fetch-portal run finishes them" | run again soon |
| Wrong key on the ack | "This key is not valid for this Project" | `.tmp` kept; fix the key, run again |
| The ack reply is not understood (also: it confirms another batch) | "The Portal's reply to the ack was not understood" | `.tmp` kept; the next run finishes them |
| The Portal no longer knows the batch (`batch_unknown`) | "The Answers come in the next fetch" | this batch's `.tmp` deleted |
| The Portal gave these Answers to a newer fetch (`batch_expired`) | "The Answers come in the next fetch" | this batch's `.tmp` deleted |
| A file could not be written (disk full, no access) | "Could not write the intake files …"; the Answers come again after the hold time | this batch's `.tmp` deleted, nothing confirmed |

**Leftover `.tmp` files** from an earlier run are handled first, before new Answers are asked for. The script
acks that earlier batch: if the Portal confirms, the files get their real names (from the time they were
fetched); if the Portal no longer holds that batch, they are deleted and those Answers come again. If the Portal
does not answer, the files are kept and the run stops. If earlier files were renamed and then the new fetch
stops, the JSON line has `ok: false` but `files` still lists the files written; show them. Files named
`portal-*.md.tmp` that fetch-portal does not recognise are named in `message`, left alone, for the BA to delete.
