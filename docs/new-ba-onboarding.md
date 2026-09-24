# New BA — first day

From a clean laptop to writing your first spec. About two hours, most of it waiting for accounts.
You do not need to know Claude Code or BMad yet: `ba-setup` walks you through, and tells you what is
missing at every step.

## 1. Ask for access (do this first — it takes the longest)

| Ask | From | What it is for |
|---|---|---|
| A Claude account with Claude Code | your lead | runs everything |
| GitHub access to the project's docs repo and code repos, and to `Relevant-S/ba-tools` | your lead | specs live in git; the skills live in ba-tools |
| Jira and Confluence on the client's Atlassian site | the project's Jira admin | tickets, releases, published pages |
| Membership of the project's Slack channels | the channel owner | client threads |
| Edit access to the project's Figma files | the design owner | designs and screenshots |
| Access to the Fireflies workspace, and to be invited to client calls | your lead | call notes |
| Edit access to the project's published pages (the BA dashboard, the clarification pages) | the BA who made them | these pages keep one link, and only an editor can update them |

## 2. Install the programs

| Program | Get it |
|---|---|
| Claude Code | claude.com/claude-code — the desktop app or the command line |
| Git | git-scm.com — accept the defaults |
| Node 22 | nodejs.org — the LTS installer |
| uv | in PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |

## 3. Get the project and the tools

1. Clone the project's docs repo, and the code repos inside it where the project says so. Check out
   the branch the BAs work on (it is `spec_links.branch` in the project profile — for Acme Lending,
   `ba-tools`).
2. Clone `https://github.com/Relevant-S/ba-tools` to, for example, `C:\dev\ba-tools`.
3. Copy `skills/ba-setup/` and `skills/ba-spec/` from ba-tools into the project's `.claude/skills/`.
   (Skip this if the project already has them.)

## 4. Run the setup

Open the project folder in Claude Code and type **ba-setup**.

It checks everything and shows one table: what works, what is missing, what to do. Then it offers
the next step:

- **`ba-setup me`** — your own keys and connectors: Jira, Confluence, Fireflies, Gmail, Slack, the
  Atlassian and Figma connectors. For each one it tells you where to click and which lines to add to
  your settings file. You paste the keys into the file yourself — never into the chat.
  It also offers **starter defaults**:
  - instructions that make Claude answer in plain words and always ask before anything reaches other
    people;
  - permissions so that reading and searching run without asking you, anything that changes a file,
    a ticket or a message still asks, and a few hard-to-undo commands are blocked.
- **`ba-setup project`** — the project's area in each tool: which Jira projects, which Slack channels,
  which client email addresses, which Figma files. On a project that is already set up this is done;
  you only run it on a new project.

After you change your settings file, **restart Claude Code**, then type **ba-setup** again until the
table is all green.

## 5. Things to leave alone

| Don't | Why |
|---|---|
| Edit `docs/BA/specs/_template.md` in a project | It is a copy from ba-tools. Project differences go in the profile. Changes go into ba-tools, for every project. |
| Paste a key or token into the chat | Chats are stored. Keys go in `~/.claude/settings.json` only. |
| Switch on the fdw plugin | Retired; its skills compete with ba-tools. |
| Set a `GITHUB_TOKEN` you do not need | An invalid one breaks the BMad installer. |
| Run `bmad-project-context` in an existing project | It rewrites the project's hand-written `AGENTS.md`. |

## 6. Your first week

Read [`flow-ongoing-project.md`](flow-ongoing-project.md) — the loop you will run every week. For a
brand-new client, [`flow-new-project.md`](flow-new-project.md).
