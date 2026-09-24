---
name: confluence
description: Publish or update a Confluence Cloud page from a local markdown file via the REST API (token-light — the page body is read from disk, never pasted through the agent's context). Use when posting/syncing a PRD, brief, spec, or any markdown doc to Confluence. The API path is far cheaper than the Atlassian MCP, which requires inlining the full body in every call.
---

# Confluence (token-light publisher)

Creates/updates Confluence Cloud pages by reading a markdown file **from disk** and POSTing it via the REST API v2. The body never passes through the model's context — only a small JSON result is printed. This is the cheap counterpart to the Atlassian MCP `createConfluencePage`/`updateConfluencePage`, which require inlining the entire page body (tens of KB) in every tool call.

Companion to the `jira` skill — same Atlassian account + API token, same script-wraps-REST pattern.

## Step 0 — every run (ba-tools)

- `<skills>` in the commands below is the folder this skill is installed in, one level up — normally
  the project's `.claude/skills/`.
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. With no
  passing stamp for this version, run the `ba-setup` skill (`check` mode) first.
- **Read the project profile** `docs/BA/specs/.ba-profile.yml`. Use `tools.confluence.space` as `--space` and `tools.confluence.parent` as the default `--parent`. If `tools.confluence` is `{}`, stop: this project does not use Confluence.
  Never use a value from another project, and never guess one the profile does not have — send the BA
  to `ba-setup project` instead.


## Prerequisites

Reuses the Atlassian API token. It checks `CONFLUENCE_*` first, then falls back to the `jira` skill's vars:

| Var | Fallback | Purpose |
|---|---|---|
| `CONFLUENCE_BASE_URL` | `JIRA_BASE_URL` | Atlassian Cloud subdomain, e.g. `https://example.atlassian.net` (the script appends `/wiki`) |
| `CONFLUENCE_EMAIL` | `JIRA_EMAIL` | Account that owns the API token (Basic-auth username) |
| `CONFLUENCE_API_TOKEN` | `JIRA_API_TOKEN` | Token from https://id.atlassian.com/manage-profile/security/api-tokens (account-wide — the same token works for Jira and Confluence) |

If the `jira` skill already works in this session, this skill works with no extra setup. The token's account needs **space permission** to create/edit pages in the target space.

One dependency (`marked`, for markdown→storage conversion) is vendored in `scripts/node_modules`. If missing, run `npm install` in `scripts/`.

## Subcommands

### `upsert <file.md> --space <KEY> [options]` — primary use case

Finds a page **by title** in the space; **updates** it (version auto-increments) if it exists, else **creates** it. Reads the markdown from disk, strips a leading YAML frontmatter block, converts to Confluence **storage** format, and posts it.

```bash
node "<skills>/confluence/scripts/confluence.mjs" upsert \
  "C:/Projects/nwe/_bmad-output/planning-artifacts/prds/prd-NWE-2026-06-03/prd.md" \
  --space Northwind \
  --title "Northwind — Product Requirements Document (PRD)" \
  --strip-h1 \
  --note "**Status:** DRAFT — for review. Please comment inline." \
  --message "Sync from prd.md"
```

| Flag | Effect |
|---|---|
| `--space <KEY>` | **Required.** Space key (e.g. `Northwind`). Resolved to the numeric space id. |
| `--title "..."` | Page title. **Pass it explicitly when updating** so it matches the existing page — otherwise the title is taken from the file's first `# H1` (or the filename), and a *different* title creates a **new** page. |
| `--parent <id\|home>` | Parent page id; `home` = the space homepage. Omit to leave parent unchanged (update) or default (create). |
| `--strip-h1` | Drop the first `# H1` line from the body (use when the page title already carries it, to avoid a duplicate heading). |
| `--note "..."` | Prepend a one-line markdown blockquote (status banner) above the body. |
| `--message "..."` | Version message recorded on the page history. |
| `--dry-run` | Resolve space + title + byte count and print, without writing. |

Output JSON: `{ action: created|updated, id, version, title, url, bytes }`.

**Title is the upsert key.** There is no content diffing — every `upsert` that finds the page writes a new version. Keep the title stable across runs.

### `get <pageId>` — cheap verification

```bash
node ".../confluence.mjs" get 1507330
```
Output: `{ id, title, status, version, spaceId, url }`. Use to confirm a publish landed / check the live version without fetching the (large) body.

### `space <KEY>` — debug helper

```bash
node ".../confluence.mjs" space Northwind
```
Output: `{ id, homepageId, name }`.

## Markdown → storage notes

`marked` (GFM) renders headings, paragraphs, **bold**/*italic*, `inline code`, fenced code, blockquotes, horizontal rules, nested bullet/ordered lists, tables, and links — all accepted by Confluence storage. Confluence validates storage XHTML on write, so a malformed body fails fast with a `400`. Confluence-specific macros (panels, status lozenges, expands) are **not** emitted — if you need those, author them in the markdown as raw storage HTML or use the MCP for that page.

## Why this exists (vs the MCP)

The Atlassian MCP `create/updateConfluencePage` tools require the **full page body inline in the tool call** every time — for a large PRD that is ~25–30k tokens per publish, and the create response echoes the whole stored page back (another oversized payload). This script keeps the body on disk: the agent spends a one-line command and reads a tiny JSON back. For an actively-iterated doc (a PRD under review) that is the difference between a few hundred tokens and tens of thousands per update.

## Errors

| Error | Meaning | Fix |
|---|---|---|
| `Atlassian env vars not set` | No token vars present | Set `JIRA_*` (or `CONFLUENCE_*`) in `~/.claude/settings.json` env, restart session |
| `401 Unauthorized` | Token invalid/expired | Regenerate the API token, update settings, restart |
| `403 Forbidden` | Token's account lacks space permission | Grant create/edit on the target space |
| `Space "X" not found` | Wrong key or no access | Run `space <KEY>`; check the key and permissions |
| `400 ... storage` | Markdown produced storage XHTML Confluence rejected | Simplify the offending markdown (often a raw-HTML snippet); re-run |

## Related skills

- `jira` — files BA specs / comments to Jira via the same API-token pattern.
- Atlassian MCP (`product-management:atlassian`) — richer Confluence features (inline comments, panels, ADF), but token-heavy for large bodies. Prefer this skill for publishing/syncing whole markdown docs.
