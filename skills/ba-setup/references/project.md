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
4. **Figma** — ask for the link of each file the BA works in: the design file(s) and the design system.
   The file key is the part after `/design/` in the link. For each: `name`, `product`, `use`
   (`designs` or `design-system`) → `tools.figma.files`. Check each key with the Figma connector
   (`get_metadata` on the file) before writing it.
5. **Confluence** (only when the project uses it) — run `list-confluence-spaces`; the BA picks the space.
   Ask for the parent page link (new pages go under it); the page id is the number in the link →
   `tools.confluence`. If the project does not use Confluence, write `confluence: {}`.

## Part 3 — Write and check

1. Show the profile as a list of what is new or changed. Wait for a yes.
2. Write it. If a profile existed, back it up first (`.ba-profile.yml.bak-<date>`).
3. Copy `skills/ba-spec/assets/spec-template.md` from ba-tools to `docs/BA/specs/_template.md`.
4. Create any missing BA folders: `docs/BA/intake`, `docs/BA/triage`, `docs/BA/specs`,
   `docs/BA/clarifications`. Put a `.gitkeep` in each empty one.
5. Run `check-project` and show the table.
6. Do **not** commit. List the changed files and ask.

## Older per-tool config files

Projects set up before ba-tools 0.2.0 may still have `docs/BA/.fetch-gmail-config.yaml` and
`docs/BA/.fetch-slack-config.yaml`. Copy their senders and channels into the profile. Leave the files in
place until the fetch skills have moved into ba-tools and read the profile; then delete them.
