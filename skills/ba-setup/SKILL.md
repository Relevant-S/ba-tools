---
name: ba-setup
description: Set up, check or repair the BA toolset — the BA's personal keys and connectors (Jira, Confluence, Fireflies, Gmail, Slack, Figma), the project's area in each tool (Jira projects, Slack channels, client emails, Figma files, Confluence space), and starter defaults for newcomers (simple-language instructions, read-only permissions). Four modes — `check` (a green/red table, changes nothing), `me` (personal, once per machine), `project` (shared, once per project), `design` (a product's Figma files and design system, once per product). Use when the BA says "set up", "ba-setup", "check my setup", "why does fetch fail", on a BA's first day, or when another ba-tools skill sends you here.
---

# ba-setup

Gets a BA from nothing to working, and tells them exactly what is missing when something stops
working. Written for someone who has never used Claude Code or BMad: plain words, one step at a time,
and never "just edit the config".

Four modes. With no argument, run **check**.

| Mode | What it covers | Who it belongs to | Changes anything? |
|---|---|---|---|
| `check` | everything below, as one table | — | no (writes the setup stamp when all is green) |
| `me` | personal keys and connectors, local programs, starter defaults | this BA, this machine | yes — the BA's own settings, after asking |
| `project` | the project's area in each tool, and the project profile | everyone on the project | yes — `docs/BA/specs/.ba-profile.yml`, after showing it |
| `design` | one product's design profile: Figma files, design system, tokens, frame sizes, traps | everyone on the project | yes — `docs/BA/design-system/<folder>/design-profile.yml`, after showing it |

The helper script does the calls; it never prints a key:

```
uv run --with pyyaml python "<this skill>/scripts/setup.py" <command> [project-root]
```

## Rules

1. **Never ask the BA to paste a key, token or password into the chat.** Keys go into
   `~/.claude/settings.json` (the `env` block), which the BA edits themselves. Show them the exact lines
   to add with a placeholder, and where to get the real value.
2. **Keys are personal; areas are shared.** A key never goes into the project profile or a repo. An
   area (a channel name, a Jira project, a client address) always goes into the profile.
3. **After the BA changes `~/.claude/settings.json`, they must restart Claude Code** — a running session
   does not see new keys. Say so every time, and pick up with `check` after the restart.
4. **Plain words.** Every row in a table says what it is for. "Slack — reads the client channels", not
   "SLACK_USER_TOKEN".
5. **Show before writing.** The profile, the settings file and CLAUDE.md are shown as a list of changes
   before anything is written, and backed up when they already exist.

## Mode: check

1. Run `check-me`, and `check-project <project root>` if the current folder is a project (it has a
   `docs/` folder or a `.git`).
2. Check the two connectors yourself — the script cannot:
   - **Atlassian** — call `atlassianUserInfo`. If the tool does not exist or fails, the connector is
     not connected.
   - **Figma** — call `whoami`. Same rule.
3. Show **one table**: tool · what it is for · state (✅ works · ⚠️ works with a warning · ❌ missing or
   broken · — not used here) · what to do. Group the rows under **You** and **This project**.
4. Then suggest the next step, in one line:

   | Result | Say |
   |---|---|
   | ❌ only under You | "Run `ba-setup me` — it walks you through each one." |
   | ❌ only under This project | "Run `ba-setup project`." (or `ba-setup design` when only a design profile is missing) |
   | ❌ in both | "Run `ba-setup me` first, then `ba-setup project`." Offer to start `me` now. |
   | only ✅ and ⚠️ | "All set." Explain each ⚠️ in one line. Run `stamp`. |

## Mode: me

Follow `references/me.md`. In order:

1. **Local programs** — Git, Node 22, uv. Missing ones are installed by the BA; give the link and the
   one command.
2. **Connectors** — Atlassian and Figma, in the Claude app: Settings → Connectors. Check each one as in
   `check`.
3. **Keys** — one tool at a time, only the ones `check-me` reported as missing or broken. For each:
   what it is for, where to get the value (click by click), the lines to add to the `env` block.
   Collect all the lines first, so the BA edits the file once and restarts once.
4. **Starter defaults** — run `defaults-plan` and show, in plain words:
   - the instructions section that will be added to `~/.claude/CLAUDE.md`
     (`assets/starter-instructions.md`), and
   - the permissions that will be added: *reading and searching run without asking; anything that
     changes a file, a ticket or a message still asks; force-push, hard reset, `rm -rf` and sending
     email are blocked.* List the counts, and the full list on request.

   Ask. On yes, run `defaults-apply` and tell the BA where the backups are. Nothing is ever removed
   from their settings — only added. If they already have instructions of their own on the same
   topics, say so and let them choose.
5. **Warnings** — explain each ⚠️ from `check-me` (for example an old `GITHUB_TOKEN`, or the retired fdw
   plugin still switched on) and offer the fix. Never change these without a yes.
6. Ask the BA to restart Claude Code, then run `check`.

## Mode: project

Follow `references/project.md`. In short:

1. If the project has no profile, start one from `profile/ba-profile.example.yml` in ba-tools. If it
   has an older one (`profile_version` below 2), keep every value and add what is new.
2. Walk the **project facts** — products, roles, ids, PRD, code branches, where specs go. Read them from
   the repo and the code wherever you can; ask only what the code cannot tell you.
3. Walk the **tool areas**, picking from real lists wherever there is one:
   - Jira projects — `list-jira-projects`
   - Slack channels — `list-slack-channels` (only channels the BA is in)
   - Confluence space and parent page — `list-confluence-spaces`
   - Figma files — the BA pastes the links; take the file key from each
   - Client emails — the BA types the client domain(s) and any single addresses, plus addresses to leave
     out (no-reply, help desk). The same list decides which Gmail threads **and** which Fireflies calls
     belong to this project.
4. Show the finished profile as a list of changes. On yes, write it, copy the template to
   `docs/BA/specs/_template.md`, and create the BA folders that are missing
   (`docs/BA/intake`, `docs/BA/triage`, `docs/BA/specs`, `docs/BA/clarifications`).
5. Run `check-project` and show the result. Do not commit — say what changed and ask.

## Mode: design

Follow `references/design.md`. It asks one question first — does the product already ship code the
design must match? — and then reads the profile out of the code and the Figma file (existing
product), or sets up a design system from a stock kit and the client's brand (new product).

## Other ba-tools skills

Every ba-tools skill starts with `stamp-status`. If there is no passing stamp for the installed
version, it runs **check** first and continues only when nothing is ❌ — so a new BA is sent here
automatically on their first run, and everyone is sent here once after an upgrade.
