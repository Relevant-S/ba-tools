# New BA — the setup manual

From a clean laptop to writing your first spec. About **two hours of your time**, spread over a day or
two because some steps wait on other people. You do not need to know Claude Code or BMad yet.

**The one idea to hold:** most of the setup is *connecting Claude to the tools you already use* —
Jira, Confluence, Figma, Fireflies, Gmail, Slack. Each connection is either a **key** (a long secret
code you copy into one settings file) or a **connector** (you click *Connect* in the Claude app and log
in). This manual tells you, tool by tool, where to get each one and who to ask when you cannot.

**Two people you may need:**

| Who | For what |
|---|---|
| **The lead BA** | the shared Gmail and Slack app settings (steps 4.4 and 4.5), and questions about the tools |
| **admin@relevant.software** | anything that says *"needs admin approval"* or *"blocked by your organisation"* in a Relevant tool (Google, Slack, Figma) |

---

## Step 1 — Ask for access (do this first: it is the part that waits on others)

Send these on day one. You can carry on with steps 2–3 while you wait.

| Access | Ask whom | What to write |
|---|---|---|
| A Claude account with Claude Code | your lead | — |
| GitHub: the project's docs repo, its code repos, and `Relevant-S/ba-tools` | your lead | *"Please add me (GitHub: <your username>) to <repo names> and to Relevant-S/ba-tools."* |
| The client's Jira and Confluence | the project's Jira admin — usually **on the client's side** | *"Please give <your email> access to the Jira project(s) <keys> and the Confluence space <name>, with permission to create and edit issues and pages."* |
| The project's Figma files, **with an edit seat** | the Figma file owner; the seat from admin@relevant.software | *"Please give me edit access to <file names>. I need a Figma edit seat — a view-only seat cannot build screens."* |
| Fireflies, and invites to the client calls | your lead | — |
| The project's Slack channels (if the project has them) | the channel owner | *"Please add me to #<channel>."* |
| Edit access to the project's published pages (the BA dashboard, the clarification pages) | the BA who made them | these pages keep one link, and only an editor can update them |

---

## Step 2 — Install the programs

| Program | What it is for | How |
|---|---|---|
| Claude Code | runs everything | claude.com/claude-code — the desktop app or the command line |
| Git | the specs live in git | git-scm.com → Download for Windows → accept every default |
| Node 22 | the fetch and Jira scripts | nodejs.org → the **LTS** installer |
| uv | BMad and ba-tools helper scripts | open **PowerShell** and paste: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |

---

## Step 3 — Get the project and the tools

1. Clone the project's docs repo (your lead tells you where, and which branch the BAs work on — for Easy
   Payday it is `ba-tools`).
2. Clone `https://github.com/Relevant-S/ba-tools` to `C:\dev\ba-tools`.
3. If the project does not have the BA tools yet, install them — in PowerShell:
   `uv run --with pyyaml python C:/dev/ba-tools/scripts/install.py <the project folder>`

---

## Step 4 — Connect the tools

Open the project folder in Claude Code and type **`ba-setup`**. It checks everything and shows one table
— ✅ works, ❌ missing — and tells you what to do next. Then type **`ba-setup me`** and it walks you
through the ❌ rows one at a time. This section is the same walk-through on paper.

### How to add a key (you will do this four or five times)

1. Open your settings file. In PowerShell: `notepad $env:USERPROFILE\.claude\settings.json`
   (if Notepad says the file does not exist, create it with the content below).
2. Keys go inside the `"env"` block, one per line, each line ending with a comma except the last:

   ```json
   {
     "env": {
       "JIRA_BASE_URL": "https://example.atlassian.net",
       "JIRA_EMAIL": "you@relevant.software",
       "JIRA_API_TOKEN": "paste-your-token-here"
     }
   }
   ```

3. Save, then **quit and restart Claude Code** — a running session does not see new keys.
4. Type `ba-setup` again to check.

⚠️ **Never paste a key into the chat with Claude.** Chats are stored. Keys go in this file only.
⚠️ **A missing comma breaks the whole file.** If Claude Code complains after an edit, check the comma at
the end of the line above the one you added.

### 4.1 Jira and Confluence — you can do this alone

1. Go to **id.atlassian.com → Security → API tokens → Create API token**. Name it *Claude Code*.
2. Copy it straight away — Atlassian shows it only once.
3. Add three keys: `JIRA_BASE_URL` (the client's site, e.g. `https://example.atlassian.net`),
   `JIRA_EMAIL` (the email you log in with), `JIRA_API_TOKEN` (the token). Confluence uses the same three.

If `ba-setup` says a Jira project is not visible, your access from step 1 has not come through yet.

### 4.2 Fireflies — you can do this alone

1. **app.fireflies.ai → Settings → Developer settings → API key → copy**.
2. Add `FIREFLIES_API_KEY` and `FIREFLIES_USER_EMAIL` (the email Fireflies has for you).

Only calls you were invited to, or that were shared with you, will show up.

### 4.3 The Atlassian and Figma connectors — you can do this alone

In the **Claude app** (not Claude Code): **Settings → Connectors → Atlassian → Connect**, log in with the
account from 4.1. Then the same for **Figma**. No keys. Restart Claude Code afterwards.

### 4.4 Gmail — ask the lead BA for two values, then sign in once

Relevant already has a Google app for this, so you do **not** create one.

1. Ask the lead BA for the **BA Intake Gmail client ID and client secret** (shared privately — never in a
   public channel).
2. Add `GMAIL_OAUTH_CLIENT_ID` and `GMAIL_OAUTH_CLIENT_SECRET`. Restart Claude Code.
3. Ask Claude: **"run the Gmail sign-in"**. A browser page opens; choose your Relevant account and
   approve. You stay signed in — you will not need to do this again.

If Google says the app is blocked or *"needs admin approval"*, email **admin@relevant.software** with a
screenshot.

### 4.5 Slack — ask the lead BA to add you, then install for yourself

Relevant already has a *BA Intake* Slack app, so you do **not** create one.

1. Ask the lead BA to add you as a **collaborator on the BA Intake app**.
2. Open **api.slack.com/apps → BA Intake → OAuth & Permissions → Install to Workspace** and approve.
3. Copy the **User OAuth Token** — it starts with `xoxp-`. (Not the Bot token.) Add it as
   `SLACK_USER_TOKEN`. Restart Claude Code.
4. Make sure you are a member of each client channel — the token only sees channels you are in.

If Slack says the install *needs approval*, email **admin@relevant.software**.
*(This route is new — if it does not work as written, tell the lead BA so the manual gets fixed.)*

### 4.6 The starter defaults — say yes

At the end, `ba-setup me` offers two things. Both only **add** to your settings; nothing is removed, and
both files are backed up first.

- **Instructions** that make Claude answer in plain words and always ask before anything reaches other
  people (a push, a ticket, a Slack or Confluence post, an email).
- **Permissions** so that reading and searching run without asking you each time, anything that changes
  a file, a ticket or a message still asks, and a few hard-to-undo commands are blocked.

---

## Step 5 — Check, and you are done

Restart Claude Code, type **`ba-setup`**, and wait for a table with no ❌. If a row stays red, its *what
to do* column says why — and the table below covers the usual causes.

| What you see | What it means | Fix |
|---|---|---|
| Jira: `401` | wrong email or token | make a new token (4.1); check `JIRA_EMAIL` is the login email |
| Jira: project not visible | access not granted yet | chase the request from step 1 |
| Fireflies: email differs | `FIREFLIES_USER_EMAIL` is not the email Fireflies has | copy the email the check shows |
| Gmail: "sign-in no longer works" | the sign-in was revoked | ask Claude to run the Gmail sign-in again |
| Slack: "not a user token" | you copied the Bot token | copy the **User** OAuth Token (`xoxp-`) |
| Slack: channel not found | you are not in that channel | join it in Slack |
| A connector row is ❌ | not connected, or connected before the last restart | connect it in the Claude app, then restart Claude Code |
| `GITHUB_TOKEN` warning | an old token that breaks the BMad installer | remove that line from your settings file |
| Everything red after an edit | the settings file has a typo | check the commas (see *How to add a key*) |

---

## Things to leave alone

| Don't | Why |
|---|---|
| Edit `docs/BA/specs/_template.md` in a project | it is a copy from ba-tools; project differences go in the project profile |
| Paste a key or token into the chat | chats are stored; keys go in the settings file only |
| Switch on the *fdw* plugin | retired; its skills compete with ba-tools |
| Run `bmad-project-context` in an existing project | it rewrites the project's hand-written `AGENTS.md` |

---

## Your first week

- [`flow-ongoing-project.md`](flow-ongoing-project.md) — the weekly loop: a client call → intake →
  triage → spec → client review on the clarification page → ready → ticket.
- [`flow-new-project.md`](flow-new-project.md) — for a brand-new client: brief → feature specs →
  PRD phase by phase.

**Getting updates:** when the lead BA says ba-tools has a new version, run `git -C C:/dev/ba-tools pull`,
then the install command from step 3. `ba-setup` also tells you when a project is behind.
