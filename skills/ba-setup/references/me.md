# ba-setup me — the BA's own keys, connectors and programs

Everything here is personal. It lives on the BA's machine, never in a repo.

**Where keys go.** Open `~/.claude/settings.json` (on Windows `C:\Users\<you>\.claude\settings.json`)
in any text editor. Add the lines inside the `"env": { … }` block — create the block if it is not
there. Save, then **restart Claude Code**. Never paste a key into the chat.

```json
{
  "env": {
    "JIRA_BASE_URL": "https://<site>.atlassian.net",
    "JIRA_EMAIL": "<your work email>",
    "JIRA_API_TOKEN": "<paste here — never in chat>"
  }
}
```

## Programs

| Program | What it is for | How to get it |
|---|---|---|
| Git | the specs live in git repos | git-scm.com → Download for Windows; accept the defaults |
| Node 22 | the fetch and Jira scripts | nodejs.org → the LTS installer |
| uv | BMad and ba-tools helper scripts | in PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |

## Connectors (in the Claude app, not a key)

| Connector | What it is for | How |
|---|---|---|
| Atlassian | filing Jira tickets and reading Confluence from inside a skill | Claude app → Settings → Connectors → Atlassian → Connect; sign in with the work account |
| Figma | reading and building designs, screenshots for clarification pages | Claude app → Settings → Connectors → Figma → Connect |

After connecting, restart Claude Code. `check` confirms each one by calling it.

## Keys, one tool at a time

### Jira (also used for Confluence)

What it is for: the scripts that read and edit tickets, list releases, and publish Confluence pages.

1. Go to **id.atlassian.com → Security → API tokens → Create API token**. Name it "Claude Code".
2. Copy it once — Atlassian will not show it again.
3. Add `JIRA_BASE_URL` (for example `https://example.atlassian.net`), `JIRA_EMAIL` (the email you sign
   in with) and `JIRA_API_TOKEN`.

Confluence uses the same three values. Only set `CONFLUENCE_BASE_URL` / `_EMAIL` / `_API_TOKEN` if
Confluence is on a different site.

You also need **access** to the project's Jira projects and Confluence space. If `check` says a
project is not visible, ask the project's Jira admin.

### Fireflies

What it is for: pulling client call notes and transcripts.

1. **app.fireflies.ai → Settings → Developer settings → API key → copy**.
2. Add `FIREFLIES_API_KEY`, and `FIREFLIES_USER_EMAIL` = the email Fireflies has for you (the one that
   appears in your meetings' participant lists).

Fireflies only sees calls it recorded or that were shared with you. Which calls belong to which
project is decided by the project's client email list, not here.

### Gmail

What it is for: pulling client email threads.

**At Relevant, reuse the shared Google app — do not create one.**

1. Ask the lead BA for the **BA Intake Gmail client ID and client secret** (shared privately).
2. Add `GMAIL_OAUTH_CLIENT_ID` and `GMAIL_OAUTH_CLIENT_SECRET`. Restart Claude Code.
3. **Sign in once:** run the fetch-gmail sign-in (`<skills>/fetch-gmail/scripts/fetch.mjs init-auth`). A
   browser page opens; choose the Relevant account and approve. The sign-in is saved to
   `~/.claude/ba-tools/state/gmail-token.json` and does not expire.
4. If Google says the app is blocked or needs approval → **admin@relevant.software**.

*Only if there is no shared app (another company):* console.cloud.google.com → a project → enable the
Gmail API → OAuth consent screen (Internal) → Credentials → OAuth client ID → Desktop app → copy the ID
and secret, then steps 2–3.

### Slack

What it is for: pulling threads from the project's client channels.

**At Relevant, reuse the BA Intake Slack app — do not create one.**

1. Ask the lead BA to add the BA as a **collaborator on the BA Intake app**.
2. **api.slack.com/apps → BA Intake → OAuth & Permissions → Install to Workspace** → approve.
3. Copy the **User OAuth Token** (starts with `xoxp-`, not the Bot token) → `SLACK_USER_TOKEN`.
   Restart Claude Code.
4. **Join each client channel** — the token only sees channels the BA is in.
5. If the install needs approval → **admin@relevant.software**. This route is new: if it fails, tell the
   lead BA so the manual is corrected.

*Only if there is no shared app:* api.slack.com/apps → Create New App → From scratch → User Token Scopes
`channels:history`, `channels:read`, `groups:history`, `groups:read`, `users:read` → Install → copy the
User OAuth Token.

## Warnings `check` may raise

| Warning | What it means | Fix |
|---|---|---|
| `GITHUB_TOKEN` is set | An old or invalid token here makes the BMad installer fail with "401" | Remove it from the `env` block unless a tool you use needs it |
| fdw plugin switched on | A retired plugin whose skills compete with ba-tools ("write the spec", "new call came in") | In `settings.json`, set `"fdw@fdw": false` under `enabledPlugins` |
| Fireflies email differs | Your call list will be empty or wrong | Set `FIREFLIES_USER_EMAIL` to the email shown in the check |
