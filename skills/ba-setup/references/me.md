# ba-setup me — the BA's own keys, connectors and programs

Everything here is personal. It lives on the BA's machine or in their Claude account, never in a repo.

The BA works in the **Claude desktop app, Code tab**. You run every command. The BA clicks *Connect*,
signs in, approves, and types their own keys into the settings file you open for them.

## Programs

Ask, then run the install yourself. `winget` comes with Windows 11. On a Mac use Homebrew; if `brew` is
missing, the BA installs it first from brew.sh.

| Program | What it is for | Windows | Mac |
|---|---|---|---|
| Git | the specs live in git repos | `winget install --id Git.Git -e` | `brew install git` |
| Node (LTS, 22 or newer) | the fetch and Jira scripts | `winget install --id OpenJS.NodeJS.LTS -e` | `brew install node@22` |
| uv | BMad and ba-tools helper scripts | `winget install --id astral-sh.uv -e` | `brew install uv` |

A program installed now is found only in a **new session**. If the install tool is missing or an install is
blocked by company policy, give the BA the download page (git-scm.com, nodejs.org, docs.astral.sh/uv) and
ask them to install it with the default choices.

## Connectors (from the BA's Claude account — no key)

| Connector | Needed? | What it is for |
|---|---|---|
| Atlassian ("Atlassian Rovo") | yes | filing Jira tickets and reading Confluence from inside a skill |
| Figma | yes | reading and building designs, screenshots for clarification pages |
| Gmail, Slack | yes, unless the BA has the keys | fetch-gmail and fetch-slack work through them when there are no keys |
| Fireflies | nice to have | asking Claude about one call on the spot |

**To connect one:** in the Claude desktop app, **Settings → Connectors → Browse connectors** → the
connector → **Connect**, and sign in with the work account. It then shows up in every new session.

**Already connected but switched off for this session:** you can switch it on (`set_session_connector_enabled`,
after a yes). The BA can do the same from the **+** button in the message box → **Connectors**.

**Which fetch skill uses what:**

| Skill | Without a key | With a key |
|---|---|---|
| fetch-gmail, fetch-slack | works through the connector — the normal way for a new BA | a script writes the text straight to a file, keeping it out of the chat. Worth it only for a BA who fetches a lot |
| fetch-fireflies | does not work: call transcripts are too long to pass through the chat | needed |

So a new BA needs **no Gmail or Slack keys**. If Gmail or Slack shows ❌, connect the connector — never
start on the keys. The *Gmail* and *Slack* sections below are only for a BA who asks for keys by name
(`keys-add gmail slack --ba-asked`).

## Keys

**Where keys go:** the `env` block of `~/.claude/settings.json` (on Windows
`C:\Users\<you>\.claude\settings.json`, on a Mac `/Users/<you>/.claude/settings.json`). Never in the chat, never in a repo.

**How, in the desktop app:**

1. Ask the BA for the values that are not secret: the Jira site, the email they sign in with.
2. Run `keys-add <tools> --set JIRA_BASE_URL=… --set JIRA_EMAIL=…`. It adds one line per missing key,
   with a placeholder that starts `PASTE-` and says what goes there. It keeps what is already there and
   backs the file up.
3. Open the file with the `open_with` command it prints (Notepad on Windows, TextEdit on a Mac).
4. Tell the BA: *"Replace each PASTE-… text with the real value. Keep the quotes around it. Save and
   close Notepad, then tell me."*
5. Run `check-me`. It reads the saved file, so it tests the new keys right away.
6. The BA starts a **new session** (New session in the sidebar), so the fetch scripts see the keys too.

The file looks like this when done (fake values):

```json
{
  "env": {
    "JIRA_BASE_URL": "https://example.atlassian.net",
    "JIRA_EMAIL": "you@relevant.software",
    "JIRA_API_TOKEN": "ATATT3x…"
  }
}
```

### Jira (also used for Confluence)

What it is for: the scripts that read and edit tickets, list releases, and publish Confluence pages.

1. Go to **id.atlassian.com → Security → API tokens → Create API token**. Name it "Claude Code".
2. Copy it once — Atlassian will not show it again.
3. Values: `JIRA_BASE_URL` (for example `https://example.atlassian.net` — not secret), `JIRA_EMAIL` (the
   email you sign in with — not secret) and `JIRA_API_TOKEN` (the token — secret, typed into the file).

Confluence uses the same three values. Only add the `confluence` keys (`keys-add confluence`) if
Confluence is on a different site.

You also need **access** to the project's Jira projects and Confluence space. If `check` says a
project is not visible, ask the project's Jira admin.

### Fireflies

What it is for: pulling client call notes and transcripts.

1. **app.fireflies.ai → Settings → Developer settings → API key → copy**.
2. Values: `FIREFLIES_API_KEY` (secret) and `FIREFLIES_USER_EMAIL` = the email Fireflies has for you,
   the one in your meetings' participant lists (not secret).

Fireflies only sees calls it recorded or that were shared with you. Which calls belong to which
project is decided by the project's client email list, not here.

### Gmail (optional — the Gmail connector is enough)

What it is for: pulling client email threads without passing them through the chat. Only on request.

**At Relevant, reuse the shared Google app — do not create one.**

1. Ask the lead BA for the **BA Intake Gmail client ID and client secret** (shared privately). Both go
   into the file, not the chat.
2. **Sign in once, in the new session** (the sign-in script needs the keys loaded, and this session
   started without them). `check` there shows Gmail as "keys set, but you have not signed in yet". Run
   `node "<skills>/fetch-gmail/scripts/fetch.mjs" init-auth` yourself. A browser tab opens; the BA chooses
   the Relevant account and approves. The sign-in is saved to `~/.claude/ba-tools/state/gmail-token.json`
   and does not expire.
3. If Google says the app is blocked or needs approval → **admin@relevant.software**.

*Only if there is no shared app (another company):* console.cloud.google.com → a project → enable the
Gmail API → OAuth consent screen (Internal) → Credentials → OAuth client ID → Desktop app → copy the ID
and secret, then steps 1–2.

### Slack (optional — the Slack connector is enough)

What it is for: pulling client channel threads without passing them through the chat. Only on request.

**At Relevant, reuse the BA Intake Slack app — do not create one.**

1. Ask the lead BA to add the BA as a **collaborator on the BA Intake app**.
2. **api.slack.com/apps → BA Intake → OAuth & Permissions → Install to Workspace** → approve.
3. Copy the **User OAuth Token** (starts with `xoxp-`, not the Bot token) → `SLACK_USER_TOKEN`.
4. **Join each client channel** — the token only sees channels the BA is in.
5. If the install needs approval → **admin@relevant.software**. This route is new: if it fails, tell the
   lead BA so the manual is corrected.

*Only if there is no shared app:* api.slack.com/apps → Create New App → From scratch → User Token Scopes
`channels:history`, `channels:read`, `groups:history`, `groups:read`, `users:read` → Install → copy the
User OAuth Token.

## Command line instead of the desktop app

Everything above works the same, with two differences. Connectors are checked by calling
`atlassianUserInfo` and Figma's `whoami` (there is no connector list). And "a new session" means quitting
`claude` and starting it again.

## Warnings `check` may raise

| Warning | What it means | Fix |
|---|---|---|
| New session | keys were saved after this session started; the check tested them, but the scripts will not see them here | start a new session |
| `GITHUB_TOKEN` is set | An old or invalid token here makes the BMad installer fail with "401" | Remove it from the `env` block unless a tool you use needs it |
| fdw plugin switched on | A retired plugin whose skills compete with ba-tools ("write the spec", "new call came in") | In `settings.json`, set `"fdw@fdw": false` under `enabledPlugins` |
| Fireflies email differs | Your call list will be empty or wrong | Set `FIREFLIES_USER_EMAIL` to the email shown in the check |
| A plugin's Atlassian / Figma / Slack shows "needs authentication" | a copy from another plugin, not the connector ba-tools uses | leave it; the connector rows count |
