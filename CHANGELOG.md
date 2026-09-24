# Changelog

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
