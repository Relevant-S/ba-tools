---
name: fetch-gmail
description: Pull email threads from Gmail — through the BA's Gmail connector (no keys needed), or the Gmail API script when the BA has its keys — and write them as intake files at docs/BA/intake/YYYY-MM-DD-gmail-<thread-id>.md for the /intake-and-triage skill to process. Two-step flow — first run sets up tracked senders + applies a project-scoped label (BA-intake/{project_slug}); subsequent runs list labeled threads and let the BA pick which to fetch. Use when the BA wants email-channel signals from clients alongside meetings (/fetch-fireflies). Per-project namespacing via the BMAD config project_slug field; one BA can run on multiple projects without label collision.
---

# Fetch Gmail

Pulls email threads from Gmail and writes them as properly-formatted intake files for `/intake-and-triage` to ingest. Companion to `/fetch-fireflies` (meetings) — same target folder, same intake-file shape, different source (`source: gmail`).

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Take `tools.client_emails.include` and `.exclude` and pass them to `list` as `--clients` and `--exclude` — no `init-project` and no Gmail label needed. (The label mode below still works for projects that already use it.)
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.
- **Pick the route.** Both write the same intake file, so triage cannot tell them apart.

  | Route | When | Why |
  |---|---|---|
  | **Script** (*Workflow* below) | `GMAIL_OAUTH_CLIENT_ID` and `GMAIL_OAUTH_CLIENT_SECRET` are set **and** `~/.claude/ba-tools/state/gmail-token.json` exists | the email text goes straight to the file and never through the chat |
  | **Connector** (*Connector route* below) | otherwise — the normal case for a new BA | needs only the Gmail connector: no keys, no Google app, no sign-in script |

  If the script stops with a sign-in error (401, `invalid_grant`, keys not set), say so in one line and
  carry on with the connector route. If neither works — no keys and no Gmail connector in the session —
  send the BA to `ba-setup` (Connectors).

## Connector route

Uses the Gmail connector's tools (`search_threads`, `get_thread`; load them with ToolSearch if they are
deferred). Read only: never label, send, reply, forward or trash anything.

1. **Find the threads.** `search_threads` with the same query the script builds:
   `from:(<include joined with OR>) -from:(<exclude joined with OR>) newer_than:<window>` (window default
   `14d`; the BA may give another). `view: THREAD_VIEW_MINIMAL`, `pageSize: 50`; follow `pageToken` up
   to 100 threads.
2. **Mark the ones already fetched.** A thread is already imported when a file in `docs/BA/intake/` has
   `-gmail-` in its name and ends with the thread id's last 8 characters
   (`…-<last 8>.md`). The connector's thread ids are the same as the Gmail API's, so files from either
   route match.
3. **Show the list** exactly as in *Workflow* step 3 (date, subject, sender, message count,
   `[already imported]`) and ask which to fetch. Stop on `n`.
4. **Fetch and write each picked thread.** `get_thread` with `messageFormat: PLAIN_TEXT`. Write
   `docs/BA/intake/<last message date>-gmail-<slug>-<last 8 of thread id>.md` with the Write tool, in the
   *Output format* below:
   - `<slug>`: the subject, lower case, a leading `Re:`/`Fwd:`/`Fw:` dropped, every run of other
     characters turned into `-`, cut to 60 characters.
   - Dates in UTC (`YYYY-MM-DD HH:MM UTC` in the body, ISO in the front matter).
   - Each message's text as it is, minus the quoted history: cut from an `On … wrote:` line (or a
     `From:` header block) when the rest is mostly `>` lines, and drop trailing `>` lines. Never
     shorten, summarise or reword what the client wrote — triage reads the words.
   - `labels`: the thread's label ids as the connector gives them. `attachments`: name and type for each
     attachment (the connector gives no size: leave `size_bytes` out, and write "size not known" in the
     *Attachments referenced* list); never download one.
   - `participants`: every address in From, To and Cc across the thread, once each.
   - Skip a thread whose file already exists, unless the BA asked to refresh it.
5. **Summarise and offer triage** as in *Workflow* step 5.

Long threads cost chat space on this route. When the BA picks more than about 15 threads, or one thread
has more than about 30 messages, say so and offer to split the run.

## Why two-step?

A BA's Gmail inbox is mostly noise. Pulling "all emails in last 14 days" is unusable. Instead:

1. **Initiation (per project, one-time)**: BA tells the skill which client email addresses are signal-bearing. Skill scans those senders in a chosen window, presents the BA with a picklist of recent threads, and applies a project-scoped Gmail label (`BA-intake/{project_slug}`) to the chosen ones.
2. **Subsequent runs**: skill scans only `label:BA-intake/{project_slug}` — fast, predictable, no inbox-wide guesswork. BA picks which labeled threads to actually pull as intake files. New threads can be added to the corpus by either re-running initiation OR by hand-applying the label in Gmail.

## Per-project namespacing

The Gmail label is hierarchical: `BA-intake/{project_slug}`. The slug comes from `_bmad/<module>/config.yaml` `project_slug:` field (set once per project). One BA working on multiple projects sees a collapsible `BA-intake` parent in their Gmail sidebar with one child per project — zero cross-contamination.

For Acme: `project_slug: acme` → `BA-intake/acme`.

## Prerequisites — script route only

Not needed for the connector route. The keys are worth it only for a BA who fetches a lot of email and
wants the text kept out of the chat.

### One-time Google Cloud setup (~15 min)

**At Relevant, do not create a Google app:** ask the lead BA for the shared BA Intake app's client ID and
secret, and to make sure your account may sign in to it (see `ba-setup` → `references/me.md` → Gmail).
The steps below are for a company with no shared app. With an "External" app, Google lets only the
listed test users sign in, and their sign-in stops working after 7 days while the app is in testing —
choose "Internal" whenever the Google Workspace allows it.

1. **Create / pick a Google Cloud project** at [console.cloud.google.com](https://console.cloud.google.com).
2. **Enable Gmail API**: APIs & Services → Library → search "Gmail API" → Enable.
3. **Configure OAuth consent screen**: APIs & Services → OAuth consent screen → choose "External" (unless your Workspace allows internal-only) → fill in app name, your email, scopes (`https://www.googleapis.com/auth/gmail.modify`) → save. Add yourself as a test user.
4. **Create OAuth credentials**: APIs & Services → Credentials → Create Credentials → OAuth client ID → Application type "Desktop app" → name it "fetch-gmail" → Create. Copy the client ID and client secret.
5. **Add to `~/.claude/settings.json`** under the `env` block:

   ```json
   {
     "env": {
       "GMAIL_OAUTH_CLIENT_ID": "1234567890-abc...apps.googleusercontent.com",
       "GMAIL_OAUTH_CLIENT_SECRET": "GOCSPX-xxx..."
     }
   }
   ```

6. **Start a new session** (New session in the desktop app) so the scripts see the key. `ba-setup me` does steps 5–6 for you.

### One-time consent flow

After env vars are set, run:

```bash
node "<skills>/fetch-gmail/scripts/fetch.mjs" init-auth
```

The script:
- Spins up a temporary local loopback server on a random port.
- Prints a Google consent URL — open it in your browser.
- After you approve, Google redirects back to the loopback; the script captures the auth code and exchanges it for a refresh token.
- Saves the refresh token to `~/.claude/ba-tools/state/gmail-token.json` (user-level, not project-specific — your Gmail account is one across projects).

Re-run `init-auth` only if the token expires (rare — refresh tokens are long-lived) or if you need to re-grant.

### Per-project initiation

After auth is set up, in the project root run:

```bash
node "<skills>/fetch-gmail/scripts/fetch.mjs" init-project
```

The script:
- Reads `project_slug` from `_bmad/*/config.yaml` (errors clearly if missing).
- Asks: "Which email addresses should I track? (comma-separated)"
- Asks: "Default time window? (7d, 14d, 30d, or custom — Gmail-search syntax accepted)"
- Builds a Gmail query: `from:(addr1 OR addr2) newer_than:Xd -label:BA-intake/{slug}` (excludes already-labeled to avoid re-prompting).
- Lists matched threads (paginated, 50 most-recent per page).
- BA picks: `1,3,5` / `1-10` / `all` / numbers / `m` for more / `n` to cancel.
- Confirms: "About to apply `BA-intake/{slug}` to N threads. [Y/n]"
- Applies label via `threads.modify`.
- Saves `docs/BA/.fetch-gmail-config.yaml` with `senders:`, `window:`, `label:`, `project_slug:`.

## Workflow (subsequent runs)

1. **Verify auth + project init.** Check that `~/.claude/ba-tools/state/gmail-token.json` exists; if not, tell the BA to run `init-auth` first. Check that `docs/BA/.fetch-gmail-config.yaml` exists; if not, run `init-project`.

2. **List labeled threads.**

   ```bash
   node "<skills>/fetch-gmail/scripts/fetch.mjs" list
   ```

   Default behaviour: scans `label:BA-intake/{project_slug} newer_than:{config.window}`, returns thread metadata. Output JSON: `{count, threads: [{id, subject, snippet, participants, lastDate, messageCount, alreadyImported, intakePath}, ...]}`.

   Override flags:

   | Flag | Effect |
   |---|---|
   | `--window <duration>` | Override config window (e.g. `--window 7d`) |
   | `--include-imported` | Don't filter out threads already written to `docs/BA/intake/` (useful with `--refresh`) |

3. **Show the list to the BA**, numbered, with already-imported flagged:

   ```
   Found 8 labeled threads in last 14 days (BA-intake/acme):

     1. 2026-05-08  "CreditCo outbound retry behavior"     alice@clientco.com (4 msgs)
     2. 2026-05-07  "Q2 roadmap follow-up"             bob@clientco.com (2 msgs)        [already imported]
     3. 2026-05-05  "Salary deduction edge case"       alice@clientco.com (6 msgs)
     ...

   Which to fetch? [all / 1,3 / numbers comma-separated / n to cancel]
   Other actions: [U] unlabel <numbers>, [E] edit tracked senders, [R] re-run initiation
   ```

   On `n` or empty: stop. On numeric pick: proceed. On `[U]`, `[E]`, `[R]`: dispatch to `unlabel` / `init-project --reinit` / `init-project --reinit` accordingly.

4. **Fetch each picked thread.**

   ```bash
   node "<skills>/fetch-gmail/scripts/fetch.mjs" fetch <thread-id>[,<thread-id>...]
   ```

   Per thread: GETs full thread (all messages, all parts), renders markdown, writes to `docs/BA/intake/{lastDate}-gmail-{thread-id-fragment}.md`. Idempotent: if file exists and `--refresh` not passed, skipped with a note.

5. **Summarize and offer to chain into triage.**

   ```
   Wrote N intake files:
     - docs/BA/intake/2026-05-08-gmail-18f8b3c2.md (CreditCo outbound retry, 4 msgs)
     - docs/BA/intake/2026-05-05-gmail-18f8a1b9.md (Salary deduction edge case, 6 msgs)
   Skipped 1 (already imported, use --refresh):
     - thread 18f8b2d1 → docs/BA/intake/2026-05-07-gmail-18f8b2d1.md

   Run /intake-and-triage now? [Y/n]
   ```

   On `Y`: invoke `/intake-and-triage`. On `n`: stop.

## Output format

Each fetched intake file:

```markdown
---
source: gmail
date: 2026-05-08
thread_id: 18f8b3c2d4e5...
subject: "CreditCo outbound retry behavior"
participants:
  - alice@clientco.com
  - ba@example.com
message_count: 4
first_message: '2026-05-05T14:23:00Z'
last_message: '2026-05-08T09:11:00Z'
labels:
  - INBOX
  - BA-intake/acme
attachments:
  - { name: "CreditCo-error-log.pdf", size_bytes: 245678, mimetype: "application/pdf" }
processed: false
---

# CreditCo outbound retry behavior

**Subject:** CreditCo outbound retry behavior
**Participants:** alice@clientco.com, ba@example.com
**Started:** 2026-05-05 14:23 UTC
**Last activity:** 2026-05-08 09:11 UTC
**Messages:** 4
**Labels:** INBOX, BA-intake/acme

## Messages

### Message 1 — alice@clientco.com — 2026-05-05 14:23 UTC

[plain-text body of first message]

### Message 2 — ba@example.com — 2026-05-05 16:40 UTC

[reply body, with quoted text from message 1 stripped where possible]

### Message 3 — alice@clientco.com — 2026-05-08 08:55 UTC

[…]

### Message 4 — ba@example.com — 2026-05-08 09:11 UTC

[…]

## Attachments referenced

- `CreditCo-error-log.pdf` — 240 KB, application/pdf — _not downloaded; pull manually from Gmail if needed_
```

Triage doesn't care about the source — it ingests whatever's in `docs/BA/intake/` and reasons over it.

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `GMAIL_OAUTH_CLIENT_ID / SECRET not set` | Env vars missing | Add to `~/.claude/settings.json`, then start a new session |
| `Refresh token not found at state/token.json` | Auth not initialized | Run `init-auth` |
| `Gmail API 401: invalid_grant` | Refresh token expired or revoked | Re-run `init-auth` |
| `Gmail API 403: insufficient permissions` | Scope mismatch | Re-run `init-auth` (script requests `gmail.modify`) |
| `project_slug not found in _bmad/*/config.yaml` | BMAD config missing the field | Add `project_slug: <slug>` to the config |
| `.fetch-gmail-config.yaml not found and init-project not run` | Project not initialized | Run `init-project` |
| `Gmail API 429: rate limit` | Quota exceeded | Wait ~1 min, retry; quota is generous so this is rare |
| Google: "Access blocked … has not completed the Google verification process" | the Google app is in testing and this account is not a test user | use the connector route; or ask the app's owner to add you as a test user, or to make the app Internal |
| Gmail connector tools missing | the connector is off in this session, or not connected | `ba-setup` (Connectors) |

## Notes for colleagues sharing this skill

- **Most BAs need nothing but the Gmail connector** (Claude desktop app → Settings → Connectors → Gmail).
  The keys below are optional.
- The skill is installed per project from ba-tools; the sign-in is **personal** and lives in `~/.claude/ba-tools/state/gmail-token.json`, never in the project.
- The project config (`docs/BA/.fetch-gmail-config.yaml`) is **per-project** and git-trackable. Senders + window are project-specific.
- The Gmail label (`BA-intake/{project_slug}`) is namespaced per project, so one BA on multiple projects has no cross-contamination.
- Setup per BA on the script route: ~15 min Google Cloud setup + ~1 min consent flow. Per project: ~2 min `init-project` (pick senders, pick threads, apply label).
