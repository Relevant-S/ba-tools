# New BA — the setup manual

From a clean laptop to writing your first spec. About **two hours of your time**, spread over a day or
two because some steps wait on other people. You do not need to know Claude Code or BMad yet.

**The one idea to hold:** most of the setup is *connecting Claude to the tools you already use* —
Jira, Confluence, Figma, Fireflies, Gmail, Slack. Each connection is either a **key** (a long secret
code you type into one settings file) or a **connector** (you click *Connect* in the Claude app and log
in). Claude does the technical part; you only sign in and type your own keys. This manual tells you, tool by tool, where to get each one and who to ask when you cannot.

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
| A Claude account with Claude Code (you will use the Claude desktop app) | your lead | — |
| GitHub: the project's docs repo, its code repos, and `Relevant-S/ba-tools` | your lead | *"Please add me (GitHub: <your username>) to <repo names> and to Relevant-S/ba-tools."* |
| The client's Jira and Confluence | the project's Jira admin — usually **on the client's side** | *"Please give <your email> access to the Jira project(s) <keys> and the Confluence space <name>, with permission to create and edit issues and pages."* |
| The project's Figma files, **with an edit seat** | the Figma file owner; the seat from admin@relevant.software | *"Please give me edit access to <file names>. I need a Figma edit seat — a view-only seat cannot build screens."* |
| Fireflies, and invites to the client calls | your lead | — |
| The project's Slack channels (if the project has them) | the channel owner | *"Please add me to #<channel>."* |
| Edit access to the project's published pages (the BA dashboard, the clarification pages) | the BA who made them | these pages keep one link, and only an editor can update them |

---

## Step 2 — Install the Claude desktop app

You work in the **Claude desktop app**, on its **Code** tab. Claude does the technical steps for you
there: it installs programs, gets the repos, and runs the setup checks. You will not need PowerShell.

1. Download the app from **claude.com/download** and install it. Sign in with the Claude account from
   step 1.
2. Open the **Code** tab. Choose a folder to work in — `C:\dev` is a good one (create it if it is not
   there).
3. If the app asks to install **Git for Windows**, say yes. Claude Code needs it on Windows.

---

## Step 3 — Get the project and the tools

In the Code tab, paste this (fill in the repo your lead gave you):

> *Install Node LTS and uv if they are missing. Clone `<the project's docs repo>` and
> `https://github.com/Relevant-S/ba-tools` into `C:\dev`. Switch the project to the branch the BAs work
> on (`<branch>`). If the project does not have the BA tools yet, install them with
> `uv run --with pyyaml python C:/dev/ba-tools/scripts/install.py <the project folder>`.*

Claude asks before each install. The first time it talks to GitHub, a browser window asks you to sign in
to GitHub — do it. (For Acme Lending the branch is `ba-tools`.)

Then start a **new session** on the project folder: **New session** in the sidebar → choose the project
folder. New programs are only found in a new session.

---

## Step 4 — Connect the tools

In the project session, type **`ba-setup`**. It checks everything and shows one table — ✅ works,
❌ missing — and tells you what to do next. Then type **`ba-setup me`** and it walks you through the ❌ rows
one at a time. This section is the same walk-through on paper.

There are two kinds of connection:

| Kind | What you do | Used by |
|---|---|---|
| **Connector** | click *Connect* in the Claude app and sign in. Once, for every session | Atlassian and Figma (needed); Fireflies, Slack and Gmail (nice to have, for quick questions) |
| **Key** | type a secret code into your settings file, which Claude opens for you | the fetch scripts (Fireflies, Gmail, Slack) and the Jira and Confluence scripts |

Why both? The fetch skills write whole transcripts and threads straight to files. Doing that through a
connector would push all that text through the chat, which is slow and costly. So they use keys.

### 4.1 Connectors — you can do this alone

In the Claude desktop app: **Settings → Connectors → Browse connectors**. Connect **Atlassian** (sign in
with the account you use for the client's Jira) and **Figma**. Fireflies, Slack and Gmail are optional.

A connector you connected is in every new session. If one shows as switched off, Claude can switch it on
for you, or you can: the **+** button in the message box → **Connectors**.

### How a key gets into your settings (you will do this once or twice)

1. Claude asks you for the parts that are not secret: the Jira site and your email.
2. Claude adds a line for each missing key to your settings file, with a placeholder that starts with
   `PASTE-` and says what goes there. Then it opens the file in Notepad.
3. You replace each `PASTE-…` text with the real value. Keep the quotes. Save and close Notepad, and
   tell Claude.
4. Claude checks the keys straight away. Then you start a **new session** so the scripts can use them.

⚠️ **Never paste a key into the chat with Claude.** Chats are stored. Keys go in the settings file only.

### 4.2 Jira and Confluence — you can do this alone

1. Go to **id.atlassian.com → Security → API tokens → Create API token**. Name it *Claude Code*.
2. Copy it straight away — Atlassian shows it only once.
3. Give Claude the client's Jira site (e.g. `https://example.atlassian.net`) and the email you log in
   with. Put the token into the file. Confluence uses the same values.

If `ba-setup` says a Jira project is not visible, your access from step 1 has not come through yet.

### 4.3 Fireflies — you can do this alone

1. **app.fireflies.ai → Settings → Developer settings → API key → copy**.
2. Give Claude the email Fireflies has for you. Put the API key into the file.

Only calls you were invited to, or that were shared with you, will show up.

### 4.4 Gmail — ask the lead BA for two values, then sign in once

Relevant already has a Google app for this, so you do **not** create one.

1. Ask the lead BA for the **BA Intake Gmail client ID and client secret** (shared privately — never in a
   public channel). Put both into the file.
2. In the new session, Claude offers to run the **Gmail sign-in**. A browser page opens; choose your
   Relevant account and approve. You stay signed in — you will not need to do this again.

If Google says the app is blocked or *"needs admin approval"*, email **admin@relevant.software** with a
screenshot.

### 4.5 Slack — ask the lead BA to add you, then install for yourself

Relevant already has a *BA Intake* Slack app, so you do **not** create one.

1. Ask the lead BA to add you as a **collaborator on the BA Intake app**.
2. Open **api.slack.com/apps → BA Intake → OAuth & Permissions → Install to Workspace** and approve.
3. Copy the **User OAuth Token** — it starts with `xoxp-`. (Not the Bot token.) Put it into the file.
4. Make sure you are a member of each client channel — the token only sees channels you are in.

If Slack says the install *needs approval*, email **admin@relevant.software**.
*(This route is new — if it does not work as written, tell the lead BA so the manual gets fixed.)*

### 4.6 The starter defaults — say yes

At the end, `ba-setup me` offers two things. Both only **add** to your settings; nothing is removed, and
both files are backed up first.

- **Instructions** that make Claude answer in plain words and always ask before anything reaches other
  people (a push, a ticket, a Slack or Confluence post, an email).
- **Permissions** so that reading and searching run without asking you each time, anything that changes
  a file, a ticket or a message still asks, and a few hard-to-undo actions (such as sending email) are
  blocked.

---

## Step 5 — Check, and you are done

Start a **new session** on the project folder, type **`ba-setup`**, and wait for a table with no ❌. If a
row stays red, its *what to do* column says why — and the table below covers the usual causes.

| What you see | What it means | Fix |
|---|---|---|
| "New session" warning | keys were saved after this session started | start a new session |
| Jira: `401` | wrong email or token | make a new token (4.2); check the email is the one you log in with |
| Jira: project not visible | access not granted yet | chase the request from step 1 |
| A key says "placeholder" | a `PASTE-…` text was not replaced | ask Claude to open the file again |
| Fireflies: email differs | the email Fireflies has for you is different | give Claude the email the check shows |
| Gmail: "not signed in yet" or "sign-in no longer works" | the sign-in is missing or was revoked | let Claude run the Gmail sign-in |
| Slack: "not a user token" | you copied the Bot token | copy the **User** OAuth Token (`xoxp-`) |
| Slack: channel not found | you are not in that channel | join it in Slack |
| A connector row is ❌ | not connected, switched off, or needs a new sign-in | Claude says which; connect it under Settings → Connectors, then a new session |
| A plugin's Atlassian or Figma says "needs authentication" | a copy from another plugin | leave it — the connector is the one that counts |
| `GITHUB_TOKEN` warning | an old token that breaks the BMad installer | ask Claude to remove that line from your settings |
| Everything red after an edit | the settings file has a typo | ask Claude to check the file — most often a missing comma or quote |

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

**Getting updates:** when the lead BA says ba-tools has a new version, ask Claude: *"Pull the latest
ba-tools and install it into this project."* `ba-setup` also tells you when a project is behind.
