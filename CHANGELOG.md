# Changelog

## 0.4.0 — 2026-09-24

Every BA skill now lives in ba-tools and reads the project profile.

- **Moved in** from the lead BA's personal config: `fetch-fireflies`, `fetch-gmail`, `fetch-slack`,
  `fetch-jira-backlog`, `intake-and-triage`, `jira`, `confluence`, `feature-brief` — and the
  clarification-page generator as a new skill, `clarification-page`. No personal paths left; each
  skill starts with the setup check and reads its area from the profile.
- **Fetchers read the profile.** Fireflies keeps only calls with a client participant
  (`--clients`); Gmail lists client threads straight from `tools.client_emails` with no label or
  saved config; Slack takes `tools.slack.channels` as `--channels`. The old per-tool config files
  still work as a fallback. `project_slug` is no longer needed.
- **Gmail sign-in moved** to `~/.claude/ba-tools/state/gmail-token.json` — never inside a skill folder
  a project commits. The old location is still read.
- **Jira scripts** take `--projects KEY=folder,…` instead of the hard-coded ACME/BOND. `jira file-spec`
  is retired (it pasted the spec into the ticket and blanked header lists) — `ba-spec` files tickets.
  `jira` gained its missing name/description header.
- **Triage fixes**: a spec counts as approved when its status is `ready` or `filed` (the "goes against
  something approved" check could never fire on template specs); Jira is read with the `jira` skill;
  the pointer to a missing design document, the stale "test mode only" status and the retired
  downstream skills are gone; it reminds the BA that the dashboard page is updated by hand.
- **`feature-brief`** is generic (no NWE wording) and records that the brief is how the client sees
  the requirements, while the clarification page is where they answer.
- **`scripts/install.py`** installs or updates everything in a project; `ba-setup check` warns when a
  project is behind the local ba-tools clone and prints the command.

## 0.3.1 — 2026-09-24

- **Default: the design system lives inside the product's own Figma file** — components on their own
  pages beside the screens, live at once, no publish and accept. A separate library file only when two
  or more design files share the components (Acme Lending + Bond Portal keep theirs for that reason).
  Rule 19, the design-system mode and `ba-setup design` now handle both setups; the one-file setup gets
  a screenshot check of a few screens after a component change instead of a publish review.

## 0.3.0 — 2026-09-24

- **`skills/figma-build`** — moved from the lead BA's personal commands and made the same for every
  project. Three modes: `reproduce` (a shipped screen, from the code), `concept` (a new feature or
  change, from the spec), `design-system` (set up or change a design system). The quick clone-first
  method is the default; the spec-first method is only for a genuinely new or complex screen, and the
  skill says so before starting. Loads Figma's own `figma-use` skill first.
- `references/rules.md` — 24 build rules gathered from the Acme Lending build rules and the lead BA's
  memory, with every project value taken out.
- `references/plugin-gotchas.md` — one file of Figma plugin traps: Acme Lending's 488 lines and the
  ~25 NWE recorded separately, merged.
- `references/inventory.md` — the frame inventory is generated from the live file, never hand-kept
  (NWE's config had grown a 4,200-line frame list).
- **Design profiles** — one per product (`docs/BA/design-system/<folder>/design-profile.yml`): Figma
  files, design-system library, tokens, frame sizes, product traps. Real ones for Acme Lending, the
  Bond Portal and NWE in `profile/examples/design/`. The project profile points at them
  (`products[].design_profile`).
- **`ba-setup design`** — writes a design profile: read out of the code and Figma for a shipped
  product, or set up from a stock kit and the client's brand for a new one. `check` now reports a
  missing or incomplete design profile.
- A new concept may draw what the design system lacks, but only as a layer named `DS gap · …`, listed
  in the concepts register.

## 0.2.0 — 2026-09-24

- **`skills/ba-setup`** — new. `check` shows one table of everything a BA needs; `me` walks the BA's
  own keys, connectors and programs; `project` fills the project's area in each tool into the profile.
  `me` also offers starter defaults for newcomers: a simple-language section in `~/.claude/CLAUDE.md`
  and read-only permissions (reading runs without asking; changes still ask; force-push, hard reset,
  `rm -rf` and sending email are blocked). Nothing is removed from the BA's settings; both files are
  backed up.
- **Profile version 2** — new `tools:` block (client emails, Slack channels, Figma files, Confluence),
  and `client_representations`. `client_review` is `clarification-pages` in every project: the page the
  BA shares with the client on the call. The feature brief and Figma show the requirements; comments on
  them are extra client input.
- **`ba-spec`** — runs the setup check before its first step, so a new BA is sent through `ba-setup`
  automatically; change requests are approved on the clarification page.
- `scripts/check-project.py` folded into `ba-setup` (`check-project`), and now ignores Windows line
  endings. `.gitattributes` keeps every file on LF.
- `docs/` — the three flow documents.

## 0.1.0 — 2026-09-24

First release: the spec step, made the same for every project.

- `skills/ba-spec` — the spec skill, moved from acme-docs (`.claude/skills/ba-spec`, branch
  `ba-tools`). Every Acme Lending fact taken out and read from the project profile instead: products,
  roles, id numbering, spec folders, Jira, code repos and branches, spec links, client review route.
  Hand-off now follows the profile's `downstream` — a Jira ticket, the PRD, or both.
- `skills/ba-spec/assets/spec-template.md` — the approved template (acme-docs `ba-tools` @
  8cc4893d), made universal: the header, section 11 (roles), section 14 (code branch) and "How it is
  used" now point at the profile. Carries `ba_tools_version`.
- `profile/` — the profile layout (`README.md`), a blank example, and the two real profiles:
  Acme Lending + Bond Portal, and NWE (built from NWE's existing `.ba-profile.yml`, with the facts
  its 24 Sep local template edits had added).
- `scripts/check-project.py` — fails when a project's profile is missing a key or its template copy
  differs from ba-tools.
