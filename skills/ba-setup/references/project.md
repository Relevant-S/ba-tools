# ba-setup project — the project's profile and its area in each tool

Everything here is shared: it goes into `docs/BA/specs/.ba-profile.yml` and is committed, so the next
BA on the project gets it for free. What each key means: `profile/README.md` in ba-tools.

Work through the parts in order. For each value, **find it before asking**: read the repo, the code,
the existing specs, the Jira project. Ask the BA only for what cannot be found, and say where you
looked.

## Part 1 — Project facts

| Value | Where to find it before asking |
|---|---|
| `products` (key, name) | the repo's folders, `AGENTS.md`, the PRD |
| `roles` per product | the code — the role enum or role list in the backend. Record the file and branch in `checked_at`. Note traps (a word that looks like a role but is only a group) in `notes` |
| `downstream` | `jira` if specs become tickets one by one; `prd` if specs are grouped into a PRD per phase and then epics and stories |
| `cadence`, `release_folders` | a release train in Jira → `release` + `true`; phases → `phase` + `false` |
| `ids` | an existing register file → `register`; otherwise `highest-existing` with every folder ids appear in |
| `prd.paths` | `docs/prd.md`, or the BMad PRD folder (`…/planning-artifacts/prds`) |
| `code` | `git -C <repo> remote show origin` for the default branch; ask which branch developers merge into and which is production — they differ between projects |
| `spec_links` | the docs repo's remote URL, and the branch specs are committed on |
| `decider_model` | one client decision-maker → `single`; several people who can disagree → `multi` |

## Part 2 — Tool areas

Show each list as numbered lines; the BA answers with numbers.

1. **Jira** (only when `downstream` has `jira`) — run `list-jira-projects`. The BA picks one project
   per product → `products[].jira_project`. Fill the `jira` block: site from the list output, default
   issue type `Task`, and the priority names — read them from one ticket in the project rather than
   assuming.
2. **Slack** — run `list-slack-channels`. The BA picks the channels where the client talks →
   `tools.slack.channels`. If a channel they expect is missing, they are not a member — ask them to
   join it and run the list again.
3. **Client emails** — ask: *"Which email domains and addresses are the client? And any addresses to
   leave out, like a help desk or no-reply?"* → `tools.client_emails.include` / `exclude`. A domain is
   written with its `@` (`@client.com`). This one list decides which email threads **and** which
   recorded calls belong to this project.
4. **Client contacts** — ask: *"Who on the client side answers our questions? Name, and email or Slack name
   if you have them."* → `tools.client_contacts`, one `{ name, email, slack }` per person (`name` is
   required; leave out what you do not have). Look first in `docs/BA/dashboard-slack.yaml` (`client_owners`)
   and the `who` of awaiting items in `docs/BA/dashboard.yaml`. The Portal uses this list only to show a
   Client "Waiting on you"; it shows the names to nobody.
5. **Client Portal** (only when the project publishes to the Relevant Clients Portal) — ask for the
   Portal's address → `tools.portal.url` (for example `http://localhost:3000` while it runs locally; any
   other host must use `https://`). Then
   tell the BA where the key goes, and **never ask them to paste it into the chat**:
   - an Admin gets the Project's Publish key in the Portal at Admin → Projects → the Project → Publishing
     (it is shown in full once — "Regenerate key" makes a new one);
   - the BA puts it in a file `.env` at the repo root, as `PORTAL_PUBLISH_KEY=<key>`;
   - `.gitignore` must list `.env`. Check with `git check-ignore -q .env` (exit 0 = ignored); if it is not,
     add `.env` to `.gitignore`. Never commit `.env`.

   Not using the Portal: leave `tools.portal` out.
6. **Figma** — ask for the link of each file the BA works in: the design file(s) and the design system.
   The file key is the part after `/design/` in the link. For each: `name`, `product`, `use`
   (`designs` or `design-system`) → `tools.figma.files`. Check each key with the Figma connector
   (`get_metadata` on the file) before writing it.
7. **Confluence** (only when the project uses it) — run `list-confluence-spaces`; the BA picks the space.
   Ask for the parent page link (new pages go under it); the page id is the number in the link →
   `tools.confluence`. If the project does not use Confluence, write `confluence: {}`.

## Part 3 — The dashboard

If `docs/BA/dashboard.yaml` exists, record it and its published link as `tools.dashboard`. If not,
offer to start one with the `ba-dashboard` skill (*Starting one*) — it is where the BA will find every
clarification page. Not wanted yet: write `dashboard: {}`.

## Part 3a — Dictionary and messages

Start the data dictionary (`data-dictionary` skill, *Starting one*) and the messages catalogue
(`messages` skill, `init`), and record them as `tools.dictionary.config` and `tools.messages.file`. On a
project that already ships, fill the catalogue from the code's notification service.

## Part 3b — Design profiles

For each product with screens, run `ba-setup design` (or offer to run it now). It writes the product's
design profile and adds its path as `products[].design_profile`.

## Part 4 — Write and check

1. Show the profile as a list of what is new or changed. Wait for a yes.
2. Write it. If a profile existed, back it up first (`.ba-profile.yml.bak-<date>`).
3. Copy `skills/ba-spec/assets/spec-template.md` from ba-tools to `docs/BA/specs/_template.md`.
4. Create any missing BA folders: `docs/BA/reference`, `docs/BA/intake`, `docs/BA/triage`,
   `docs/BA/specs`, `docs/BA/clarifications`. Put a `.gitkeep` in each empty one. Into `docs/BA/reference/`
   copy `assets/reference-README.md` as `README.md` and `assets/reference-gitignore` as `.gitignore`
   (recordings stay out of git).
5. Run `check-project` and show the table.
6. Do **not** commit. List the changed files and ask.

## Older per-tool config files

Projects set up before ba-tools 0.2.0 may still have `docs/BA/.fetch-gmail-config.yaml` and
`docs/BA/.fetch-slack-config.yaml`. Copy their senders and channels into the profile. Leave the files in
place until the fetch skills have moved into ba-tools and read the profile; then delete them.
