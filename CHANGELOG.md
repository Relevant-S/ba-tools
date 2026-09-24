# Changelog

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
