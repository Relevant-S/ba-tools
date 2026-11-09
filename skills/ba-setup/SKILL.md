---
name: ba-setup
description: Set up, check or repair the BA toolset — the BA's personal keys and connectors (Jira, Confluence, Fireflies, Gmail, Slack, Figma), the project's area in each tool (Jira projects, Slack channels, client emails, Figma files, Confluence space), and starter defaults for newcomers (simple-language instructions, read-only permissions). Four modes — `check` (a green/red table, changes nothing), `me` (personal, once per machine), `project` (shared, once per project), `design` (a product's Figma files and design system, once per product). Use when the BA says "set up", "ba-setup", "check my setup", "why does fetch fail", "connect the Portal" (a one-time code from an Admin puts the Portal key in .env; never ask for a key), on a BA's first day, or when another ba-tools skill sends you here.
---

# ba-setup

Gets a BA from nothing to working, and tells them exactly what is missing when something stops
working. Written for someone who has never used Claude Code or BMad: plain words, one step at a time,
and never "just edit the config".

**Where BAs work: the Claude desktop app, Code tab.** That changes how setup goes:

- **You do the work.** You run every command yourself (installs, the Gmail sign-in, opening the settings
  file). The BA never opens PowerShell or a terminal. They only click *Connect*, sign in, approve, and
  type their own keys into the settings file you open for them.
- **Connectors come from the BA's Claude account.** Connected once under Settings → Connectors, they show
  up in every session. You can see them and switch them on for this session yourself (below).
- **"Restart" means a new session.** A session reads the settings file once, when it starts. After a
  change to it, the BA starts a new session (**New session** in the sidebar) and types `ba-setup` there.
  Quitting the app is only needed if a new session still does not see the change.

The same skill still works from the command line (`claude` in a terminal). Where a step differs, it says so.

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

`check-me`, `defaults-plan` and `defaults-apply` also take `--connectors '{"<name>": "<id>", …}'`: the
connectors from the session's connector list (see *Connectors* below). `keys-add <tool…>` writes placeholder
lines for missing keys (see *Mode: me*, step 3).

`connect` (a Portal key from a one-time code) needs two more packages:

```
uv run --with pyyaml --with httpx --with jsonschema python "<this skill>/scripts/setup.py" connect <project-root> --product "<product, or empty>" --code <code> [--replace]
```

## Rules

1. **Never ask the BA to paste a key, token or password into the chat.** Keys go into
   `~/.claude/settings.json` (the `env` block). You write placeholder lines there (`keys-add`) and open
   the file; the BA swaps each placeholder for the real value. A site address or an email is not a
   secret: the BA may give those in chat, and `keys-add --set` fills them in. The one exception is a **Portal key**: the
   BA never sees it. They give you a one-time **connect code** from an Admin, and `connect` puts the key in
   the repo's `.env` itself. A code is safe in chat: it works once, for 10 minutes.
2. **Keys are personal; areas are shared.** A key never goes into the project profile or a repo. An
   area (a channel name, a Jira project, a client address) always goes into the profile.
3. **After the settings file changes, the BA starts a new session** — this one does not see the new keys.
   Say so every time, and say to type `ba-setup` in the new session. (`check-me` reads the file too, so
   it can already test a saved key here, and shows a "New session" row while the session is behind.)
4. **Plain words.** Every row in a table says what it is for. "Slack — reads the client channels", not
   "SLACK_USER_TOKEN".
5. **Show before writing.** The profile, the settings file and CLAUDE.md are shown as a list of changes
   before anything is written, and backed up when they already exist.

## Mode: check

1. Run `check-me`, and `check-project <project root>` if the current folder is a project (it has a
   `docs/` folder or a `.git`).
2. Check the connectors yourself — the script cannot. See *Connectors* below. Pass what you found to
   `check-me` as `--connectors`, so `defaults_installed` also counts the desktop names of the connector rules.
   When the profile has `tools.portal`, `check-project` gives one row per Portal key ("Portal key: <product>",
   or "Portal key" with one product): ✅ when its `.env` variable is there, ❌ when it is missing. It reads only
   the variable names, never a key. For a missing key, "what to do" is: *ask an Admin for a connect code
   (Admin → Projects → the project → Publishing → Connect a repo), one per product, then run
   `ba-setup project` — it puts the key in `.env`.* Never tell the BA to copy a key into `.env`.
3. Show **one table**: tool · what it is for · state (✅ works · ⚠️ works with a warning · ❌ missing or
   broken · — not used here) · what to do. Group the rows under **You** and **This project**.
4. Then suggest the next step, in one line:

   | Result | Say |
   |---|---|
   | ❌ only under You | "Run `ba-setup me` — it walks you through each one." |
   | ❌ only under This project | "Run `ba-setup project`." (or `ba-setup design` when only a design profile is missing) |
   | ❌ in both | "Run `ba-setup me` first, then `ba-setup project`." Offer to start `me` now. |
   | only ✅ and ⚠️ | "All set." Explain each ⚠️ in one line. Run `stamp`. |

## Connectors

In the desktop app, call `session_connectors_status` (load it with ToolSearch if it is deferred). Read the
rows with kind `connector`:

| Connector | Needed? | What it is for |
|---|---|---|
| Atlassian (listed as "Atlassian Rovo") | yes | filing Jira tickets and reading Confluence inside a skill |
| Figma | yes | reading and building designs, screenshots for clarification pages |
| Fireflies, Slack, Gmail | no — nice to have | asking Claude about one call, thread or email on the spot. The fetch skills do **not** use them: they use the keys, so the BA needs both |

| What the list shows | State | What to do |
|---|---|---|
| status `connected` | ✅ | — |
| status `disabled` | ❌ | Ask, then switch it on with `set_session_connector_enabled` (it also becomes the default for new sessions). It works from your next turn. |
| status `needs_auth` | ❌ | The BA signs in: Settings → Connectors → the connector. Then a new session. |
| status `failed` | ❌ | Try `reconnect_session_connector`; if it fails again, the BA disconnects and connects it again under Settings → Connectors. |
| not in the list | ❌ | The BA adds it: Settings → Connectors → Browse connectors → the connector → Connect, signing in with the work account. Then a new session. |

**Plugin copies.** Rows of kind `plugin` for the same tools (for example
`plugin:product-management:atlassian`, status `needs_auth`) come from another plugin, not from ba-tools.
Leave them: the connector rows do the job. Mention them only if the BA asks why they see "needs
authentication".

Keep each connector's `name` and `id` from the list: `--connectors` takes them, for example
`'{"Atlassian Rovo": "3925e0a9-…", "Gmail": "ddbe65a1-…"}'`. In the desktop app a connector's tools are named
after its id (`mcp__<id>__…`), not `mcp__claude_ai_<Name>__…` as on the command line, so the starter
permissions need both names. Without them, the "never send email" rule blocks nothing in the desktop app.

**Command line** (no `session_connectors_status` tool): call `atlassianUserInfo` and Figma's `whoami`.
If a tool is missing or fails, that connector is not connected; the fix is the same Settings → Connectors
on claude.ai, then a new `claude` session. Leave out `--connectors`.

## Mode: me

Follow `references/me.md`. In order:

1. **Local programs** — Git, Node (LTS), uv. For each one `check-me` says is missing, ask, then run its
   `winget` install yourself (the command is in the row). A program installed now is found only in a new
   session: finish the other steps first, and check it there.
2. **Connectors** — as in *Connectors* above. Switch on what is off (after a yes); send the BA to
   Settings → Connectors only for what needs their sign-in.
3. **Keys** — only the tools `check-me` reported as missing or broken. For each, say what it is for and
   where to get the value, click by click (`references/me.md`). Then, once for all of them:
   1. Ask for the non-secret values in chat (the Jira site, the email they sign in with).
   2. Run `keys-add <tools> --set NAME=VALUE …`. It adds a line per missing key with a placeholder that
      starts `PASTE-` and says what goes there, keeps every value already there, and backs the file up.
   3. Open the file for them: run the `open_with` command it prints (Notepad). Tell the BA: *"Replace
      each PASTE-… text with the real value, keep the quotes, save and close."*
   4. When they say done, run `check-me` here: it reads the saved file, so it tests the keys now. A row
      still saying "placeholder" means one was missed. If `keys-add` says the file is not valid JSON, show
      the line number and help the BA fix it (most often a missing comma).
4. **Gmail sign-in** — it needs the Gmail keys loaded, so it happens in the new session (step 7): there
   `check` shows Gmail as "not signed in yet", and you offer to run the sign-in yourself
   (`references/me.md` → Gmail). A browser tab opens; the BA picks their work account and approves.
5. **Starter defaults** — run `defaults-plan --connectors …` and show, in plain words:
   - the instructions section that will be added to `~/.claude/CLAUDE.md`
     (`assets/starter-instructions.md`), and
   - the permissions that will be added: *reading and searching run without asking; anything that
     changes a file, a ticket or a message still asks; force-push, hard reset, `rm -rf` and sending
     email are blocked.* List the counts, and the full list on request.

   Ask. On yes, run `defaults-apply --connectors …` (the same list) and tell the BA where the backups
   are. Nothing is ever removed from their settings — only added. If they already have instructions of their own on the same
   topics, say so and let them choose.
6. **Warnings** — explain each ⚠️ from `check-me` (for example an old `GITHUB_TOKEN`, or the retired fdw
   plugin still switched on) and offer the fix. Never change these without a yes.
7. Ask the BA to start a new session and type `ba-setup` there. That run checks the programs, keys and
   connectors as the new session sees them, and writes the stamp when all is green.

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
   (`docs/BA/reference`, `docs/BA/intake`, `docs/BA/triage`, `docs/BA/specs`, `docs/BA/clarifications`),
   with the reference folder's index and `.gitignore` from `assets/`.
5. **Portal keys** — when the profile has `tools.portal` and `check-project` shows a Portal key missing
   (or the BA says "connect the Portal", or portal-publish or fetch-portal said the key was refused), connect
   the repo with a code. Never ask for a key. For each product with a missing key, one at a time:
   1. Ask: *"Please ask an Admin for a connect code for <product>'s Portal project: Admin → Projects → the
      project → Publishing → Connect a repo. It looks like K7P-4XM and works once, for 10 minutes. Paste it
      here."* (With one product, leave out "for <product>".) Each product's Portal project needs its own code.
   2. Run `connect <project root> --product "<product>" --code <code>` (`--product ""` when the row says just
      "Portal key").
   3. Say what it printed: *"Connected to Portal project "<name>". The key is in .env as <variable> (it ends
      in <last 4>)."* Show any warning and offer the fix. If it stops because `.env` is not ignored by git, offer to add `.env`
      to `.gitignore`, then run it again (the code still works: nothing was sent).
   4. If it says `.env` already has the variable, ask the BA: *"There is already a key for <product> in .env.
      Replace it with the new one?"* Only on yes, run it again with the same code and `--replace`. (When the
      Portal refused that key, it is already dead; otherwise an Admin can remove the old one under Connected
      repos.)
   5. If the code does not work, or there were too many wrong codes, say the message as it is and ask for a
      new code (or to wait). If the Portal is not reachable, say so and stop.

   Never print, open or show `.env`, and never repeat a key, even its middle part. Only the last 4
   characters are shown.
6. Run `check-project` and show the result. If it says the project has a brief but no dashboard, offer
   to start one now (`ba-dashboard` → *Starting one*). Do not commit — say what changed and ask.

## Mode: design

Follow `references/design.md`. It asks one question first — does the product already ship code the
design must match? — and then reads the profile out of the code and the Figma file (existing
product), or sets up a design system from a stock kit and the client's brand (new product).

## Other ba-tools skills

Every ba-tools skill starts with `stamp-status`. If there is no passing stamp for the installed
version, it runs **check** first and continues only when nothing is ❌ — so a new BA is sent here
automatically on their first run, and everyone is sent here once after an upgrade.
