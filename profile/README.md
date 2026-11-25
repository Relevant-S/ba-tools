# The project profile — `docs/BA/specs/.ba-profile.yml`

**One rule: the template and the skills are the same in every project. Everything that differs lives
here.** If you want to change the template for one project, stop — the difference is a profile value,
or it is a change to the template for every project.

Each project keeps one profile at `docs/BA/specs/.ba-profile.yml`. The skills read it at the start of
every run. If a value they need is missing, they ask you, and you add it here — they do not guess.

`ba-setup project` writes and fills it for you. To do it by hand, copy [`ba-profile.example.yml`](ba-profile.example.yml). Two real ones are in
[`examples/`](examples/): Acme Lending + Bond Portal, and NWE.

## The keys

| Key | What it says | Acme Lending | NWE |
|---|---|---|---|
| `profile_version` | Layout of this file. The skills refuse a version they do not know. | `2` | `2` |
| `ba_tools_version` | The ba-tools release installed in this project. | `0.12.0` | `0.12.0` |
| `project` | Display name. | Acme | NWE (Northwind) |
| `products` | One entry per product in the repo: `key` (the spec's `product:` value and folder name), `name`, `jira_project` (or `-`), and `roles`. | two products | one |
| `products[].design_profile` | Path to the product's design profile — Figma files, design system, tokens, frame sizes, traps. Read by `figma-build`; written by `ba-setup design`. | two, one per product | one |
| `products[].roles.checked_at` | The code file the role list was checked against, and the branch. | `ROLE_NAMES` in acme-app | `enum AdminRole` in the app schema |
| `products[].roles.list` | Every real role: on-screen `name` and `code` name, in the order the section 11 matrix uses. | 7 roles | 6 |
| `products[].roles.notes` | Traps. For example, whether "Staff" is a real role or only a group name. | "Staff" is not a role | "Staff" *is* a role |
| `decider_model` | `single` — one client voice. `multi` — several that can disagree: record both, apply the newest, tell whoever was overruled. | single | multi |
| `downstream` | Where a ready spec goes: `[jira]` (a ticket that links the spec) or `[prd]` (the PRD, then epics and stories). | `[jira]` | `[prd]` |
| `cadence` | `release` (a release train) or `phase`. | release | phase |
| `release_folders` | `true`: specs live at `<product>/<release-slug>/<slug>.md`, the release matching a real Jira fixVersion. `false`: `<product>/<slug>.md`. | true | false |
| `conflict_scope` | Which products the conflict check (section 7) runs across. Use more than one when products share code. | both | nwe |
| `sizes_requiring_ux` | Sizes that must have section 13. | m, l | m, l |
| `ids.format` | How a new capability's id is written. `{n}` is the number. | `FR{n}` | `NWE-FR-{n}` |
| `ids.source` | `register`: take `next_free` from `ids.register`, then bump it. `highest-existing`: one above the highest id found in `ids.scan`. | register | highest-existing |
| `prd.paths` | Where the phase PRDs live (one per phase, from that phase's ready specs). `frozen: true` marks an older whole-system PRD kept as a record. | phase PRDs; `docs/prd.md` frozen at 6.0 | the BMad PRD run folders |
| `code.repos` | Repos section 14 reads, relative to the project root, with the area each covers. | 7 repos | `app` |
| `code.dev_branch` | The branch developers merge into. Section 14 reads `origin/<this>`, never the local checkout. | `main` | `dev` |
| `code.live_branch` | What is in production — read when the question is "what is live today". | `prod` | `main` |
| `jira` | Only when `downstream` has jira: site, default issue type, the priority names this Jira has, and the ticket rule. | example, Task | — |
| `spec_links` | How a ticket or brief links a spec: repo URL and branch. | acme-docs @ ba-tools | northwind/docs @ docs |
| `client_review` | Where the client answers — the page the BA shares on the call and collects answers on. Always `clarification-pages`. | clarification-pages | clarification-pages |
| `client_representations` | How the client *sees* the requirements. Comments left on these are extra client input. | figma | feature-brief, figma |
| `tools.client_emails` | `include` / `exclude` — whose email and whose recorded calls count as client input. A domain is written `@client.com`. | `@acme.example`, minus the help desk | to fill in |
| `tools.client_contacts` | The client people who answer questions: `name` (required), `email`, `slack` (a Slack name or member id). `portal-publish` sends the list with every Dashboard; the Portal uses it only to show a Client "Waiting on you" and shows it to nobody. Missing → `portal-publish` uses `client_owners` from `docs/BA/dashboard-slack.yaml` (names only). | to fill in | to fill in |
| `tools.portal` | `url` — the Relevant Clients Portal's address; `portal-publish` sends the Dashboard there, and `fetch-portal` fetches the Client's Answers from the same address with the same key. The Project's Publish key is **not** here: it goes in `.env` at the repo root as `PORTAL_PUBLISH_KEY`, and `.gitignore` must list `.env`. Nobody copies it by hand: `ba-setup project` swaps an Admin's one-time connect code for a key and writes it there. `products` — only when the repo has two or more products: each product is its own Portal project, and this maps each product name (as the dashboard writes it) to the `.env` variable that holds its key, e.g. `{AcmeLending: PORTAL_PUBLISH_KEY_ACME, Bond Portal: PORTAL_PUBLISH_KEY_BOND}`; pages and `fetch-portal` use the first one for now. Leave `tools.portal` out when the project does not use the Portal. | not yet | not yet |
| `tools.slack.channels` | The channels where the client talks. The BA must be a member. | 3 channels | to fill in |
| `tools.figma.files` | Each Figma file the BA works in: `key` (from the URL), `name`, `product`, `use` (`designs` or `design-system`). | 3 files | 1 file |
| `tools.dashboard` | `file` (the dashboard's data, `docs/BA/dashboard.yaml`), `url` (its published page — one link, never changes), `page` (`docs/BA/mind-map/mind-map.html`, the Map + Board page that gets published) and optional `map` (`products`: Jira project → product name; `stage_of_status`: Jira status → stage). Or, instead of `url`, `timelines` (product → `{data, url}`): the Timeline pages are then the dashboard, and the Map + Board page is built but never published. Where a BA finds every feature and clarification page. Started right after the project brief. | the live Map + Board page | none yet |
| `tools.dictionary` | `config` — the data dictionary's config (which code it reads); the `data-dictionary` skill builds the page. | set | set |
| `tools.messages` | `file` — the messages catalogue (`docs/BA/messages.yaml`); the `messages` skill builds its page. | 28 Bond Portal emails imported | empty |
| `tools.doc_templates` | For the `doc-templates` skill: `folder` (the Drive folder id the documents service reads templates from, by exact name, direct children only), `folder_name` (how the BA finds it in Drive), `company` (the footer text before the first `\|`), `test_api` (the dev Swagger for test renders), `never_api` (the production address, never called), `log` (the rollout log). Leave it out when the project has no document templates. | set | not used |
| `tools.confluence` | `space` and `parent` page for published pages. `{}` = not used. | not used | Northwind |
| `briefs_dir`, `confluence_*`, `figma_*`, `briefs`, `brief_parents` | Settings for the `feature-brief` skill. | — | yes |

**Keys, tokens and passwords never go in the profile** — the profile is committed and shared. They go in
each BA's own `~/.claude/settings.json` (see `ba-setup me`).

## Adding a key

A new key is a ba-tools change: add it here, to the example, to both real profiles, and to the skill
that reads it, and bump `profile_version` if an old profile would now be read wrongly. Record it in
the CHANGELOG.
