# ba-tools

The BA toolset used across Relevant's client projects: the spec template, the skills that run it, and
the per-project settings they read.

## The one rule

**The template and the skills are the same in every project. Only the project profile differs.**

A project never edits the template or a skill. Everything that really is different between projects —
products, roles, id numbering, where a finished spec goes, Jira, which code branch to read, the
project's Slack channels, client emails and Figma files — lives in one file per project:
`docs/BA/specs/.ba-profile.yml` ([what each key means](profile/README.md)).

If a project seems to need a different template, the difference is either a profile value, or a
change to the template for every project. Make that change here, bump the version, and reinstall
everywhere.

## What is in here

| Path | What it is |
|---|---|
| `skills/ba-setup/` | Setup, check and repair: your own keys and connectors (`me`), the project's area in each tool (`project`), and a green/red table of both (`check`). Also installs starter defaults for newcomers. |
| `skills/ba-spec/` | Writes one spec in the template and takes it through the ready gate to its hand-off (Jira ticket or PRD). |
| `skills/ba-spec/assets/spec-template.md` | The spec template — the only copy that is ever edited. |
| `profile/` | The profile layout, a blank example, and the real profiles for Acme Lending and NWE. |
| `docs/` | How the BA work runs: first day, a new project, and the day-to-day loop. |

Still to move in: `intake-and-triage`, the fetchers (`fetch-fireflies`, `fetch-gmail`, `fetch-slack`,
`fetch-jira-backlog`), `jira`, `confluence`, `feature-brief`, and the clarification-page generator.
Then package it all as a BMad module with its own installer.

## First day

Read [`docs/new-ba-onboarding.md`](docs/new-ba-onboarding.md). In short:

1. Install Claude Code, Git, Node 22 and uv.
2. Clone this repo, e.g. to `C:\dev\ba-tools`.
3. In your project, copy `skills/ba-setup/` and `skills/ba-spec/` into `.claude/skills/`.
4. Start Claude Code in the project and say **"ba-setup"**. It checks everything and tells you what to
   do next.

## Changing something

1. Change it here, never in a project.
2. Bump `ba_tools_version` in the template header and the example profile; add a line to
   `CHANGELOG.md`.
3. Reinstall in each project, update its profile's `ba_tools_version`, and run `ba-setup check`.
