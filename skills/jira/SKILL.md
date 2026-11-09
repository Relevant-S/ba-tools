---
name: jira
description: Jira helper scripts for BA work — comment on a ticket, search with JQL, read or edit one field of a ticket (with a change check), list a project's releases, and rebuild the spec release folders from Jira versions. Reads the site and projects from the project profile. Use when the BA asks to comment on a ticket, look tickets up, update a ticket field, or refresh the release folders after a release. Not for filing new tickets — the ba-spec skill files those.
---

# JIRA

Posts comments on existing tickets, reads and edits single ticket fields, and keeps the local `docs/BA/specs/` release-folder tree in sync with the project's Jira versions. Wraps the Atlassian REST API. **New tickets are filed by the `ba-spec` skill**, not here.

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Use `jira.site` and `products[].jira_project`. For `refresh-specs`, pass `--projects KEY=folder,…` built from `products[]`.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Prerequisites

Three env vars:

| Var | Purpose |
|---|---|
| `JIRA_BASE_URL` | Atlassian Cloud subdomain, e.g. `https://example.atlassian.net` |
| `JIRA_EMAIL` | Account that owns the API token (used as the Basic-auth username) |
| `JIRA_API_TOKEN` | Token from https://id.atlassian.com/manage-profile/security/api-tokens |

**Recommended setup** — add to `~/.claude/settings.json` under `env` (user-global, never in repo):

```json
{
  "env": {
    "JIRA_BASE_URL": "https://yourcompany.atlassian.net",
    "JIRA_EMAIL": "you@yourcompany.com",
    "JIRA_API_TOKEN": "your-token-here"
  }
}
```

Start a new session after adding (New session in the desktop app): a session reads the keys only when it starts. `ba-setup me` adds these lines for you.

## Subcommands

### `file-spec` — retired (2026-09-24)

It pasted the whole spec into the ticket and blanked lists in the spec header when it wrote back.
Tickets are filed by the **`ba-spec` skill (step 9)**, written from its `assets/ticket-template.md`: a
plain-language summary for developers, test steps for manual QA, and the spec link — never the spec
body. The subcommand now stops with that message.

### `comment <issue-key> <markdown>`

Post a comment on an existing ticket.

```bash
node ".../jira.mjs" comment ACME-1640 "Update from 2026-05-15: BA call rescheduled to next week."
node ".../jira.mjs" comment BOND-873 "@docs/BA/specs/bond-portal/release-1-18-0-.../followup-comment.md"
```

The markdown argument can be a quoted string or `@<path>` to read from a file. Markdown → ADF conversion same as `file-spec`. Output JSON: `{ ok, issueKey, commentId, url }`.

### `refresh-specs`

Re-populate `docs/BA/specs/{acme|bond-portal}/` from current JIRA versions. Adds folders for any new fixVersion in ACME or BOND, regenerates `_releases.md` per project. Released versions go under `released/`. Non-destructive: existing spec files are never touched, only new directories with `.gitkeep` are added.

```bash
# from project root
node "<skills>/jira/scripts/jira.mjs" refresh-specs --projects ACME=acme,BOND=bond-portal   # from products[] in the profile
# or with explicit root
node ".../jira.mjs" refresh-specs "<project root>"
```

Output JSON: `{ ok, refreshed: [{project, active, released}], root }`.

### `versions <project>` — debug helper

List non-archived versions for a JIRA project.

```bash
node ".../jira.mjs" versions ACME
```

Output JSON: `{ project, count, versions: [{name, released, releaseDate, archived}] }`.

### `search <jql>` — debug helper

Run a JQL search.

```bash
node ".../jira.mjs" search "project = ACME AND fixVersion = Backlog AND status != Done"
```

Output JSON: `{ jql, count, issues: [{key, type, status, summary, fixVersions, assignee}] }`.

### `get-field <issue-key> <field> [--max <chars>]`

Fetch a single field's plain-text value from a JIRA issue. Used by `/intake-and-triage` step 03 §E to populate `current_excerpt` in `proposed_action: type: edit` blocks (drift-guard reference).

```bash
node ".../jira.mjs" get-field BOND-873 description --max 500
```

ADF (rich-text) fields are flattened to plain text. Output JSON: `{ issueKey, field, fullLength, excerptLength, excerpt }`. Default `--max` is 300.

### `update-field <issue-key> <field> --change-kind <append|prepend|replace> --value <text>|--value-file <path>`

PATCH a single field on a JIRA issue. Used by `/intake-and-triage` step 0.5 to materialize `proposed_action: type: edit` blocks once the agent has run the placeholder + drift guards.

```bash
# Append a markdown snippet to a description
node ".../jira.mjs" update-field BOND-873 description --change-kind append --value-file /tmp/append.md

# Replace summary with a literal string
node ".../jira.mjs" update-field ACME-1645 summary --change-kind replace --value "Disable salary-deduction verification on Top-up applications"
```

For ADF fields (`description`, custom rich-text fields) the script re-reads the live ADF doc and merges at the content-array level so existing formatting (headings, lists, marks) is preserved. For string fields the merge is raw-string concatenation with a blank-line separator.

Output JSON: `{ ok, issueKey, field, changeKind, fieldShape, bytesIn, url }`. Note: this is a low-level write — drift detection is the caller's responsibility; pair with `get-field` first.

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `JIRA env vars not set` | One of `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` missing | Add to `~/.claude/settings.json` env block, then start a new session |
| `Spec status must be "approved" before filing` | Frontmatter `status:` ≠ `approved` | Get BA approval first, set frontmatter to `approved`, then re-run |
| `Spec frontmatter missing jira_fixversion` | Required field absent | Add it to the spec frontmatter (must match a real JIRA fixVersion) |
| `fixVersion "X" not found in project Y` | Version doesn't exist or is archived | Run `versions <project>` to see valid names |
| `Auth failed (401)` | Token invalid or expired | Generate a new one, update settings, then start a new session |
| `Forbidden (403)` | Token lacks permission for the project | Check Atlassian project permissions |

## Rules that still apply

- **Spec before ticket** — a new ticket is only created by `ba-spec`, after the BA's yes.
- **Every ticket has a fixVersion at creation**; `Backlog` counts.
- **Task by default**; Bug only for a true regression.
- **`update-field` does not check for changes itself** — always read the field with `get-field` first,
  as `intake-and-triage` does.
