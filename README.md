# ba-tools

The BA toolset used across Relevant's client projects: the spec template, the skills that run it, and
the per-project settings they read.

## The one rule

**The template and the skills are the same in every project. Only the project profile differs.**

A project never edits the template or a skill. Everything that really is different between projects —
products, roles, how ids are numbered, where a finished spec goes, Jira, which code branch to read,
how the client reviews — lives in one file per project: `docs/BA/specs/.ba-profile.yml`
([what each key means](profile/README.md)).

If a project seems to need a different template, the difference is either a profile value, or a
change to the template for every project. Make that change here, bump the version, and reinstall
everywhere.

## What is in here

| Path | What it is |
|---|---|
| `skills/ba-spec/` | Writes one spec in the template and takes it through the ready gate to its hand-off (Jira ticket or PRD). |
| `skills/ba-spec/assets/spec-template.md` | The spec template — the only copy that is ever edited. |
| `profile/` | The profile layout, a blank example, and the real profiles for Acme Lending and NWE. |
| `scripts/check-project.py` | Checks a project: profile complete, template copy unchanged. |

Still to move in: `intake-and-triage`, the fetchers (`fetch-fireflies`, `fetch-gmail`, `fetch-slack`,
`fetch-jira-backlog`), `jira`, `confluence`, `feature-brief`. Then package it all as a BMad module
with a setup skill, so it installs like the rest of BMad.

## Installing in a project (for now, by hand)

From the project root:

1. **The skill.** Copy `skills/ba-spec/` to `.claude/skills/ba-spec/`.
2. **The template.** Copy `skills/ba-spec/assets/spec-template.md` to `docs/BA/specs/_template.md`.
   It is a read-only copy for people to read; the skill uses its own.
3. **The profile.** Copy `profile/ba-profile.example.yml` to `docs/BA/specs/.ba-profile.yml` and fill
   it in — or start from the matching file in `profile/examples/`.
4. **Check it.**

   ```
   uv run --with pyyaml python <ba-tools>/scripts/check-project.py <project-root>
   ```

## Changing something

1. Change it here, never in a project.
2. Bump `ba_tools_version` in the template header and the example profile; add a line to
   `CHANGELOG.md`.
3. Reinstall in each project, update its profile's `ba_tools_version`, and run the check.
