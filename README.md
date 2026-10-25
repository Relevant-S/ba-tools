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
| `skills/figma-build/` | Builds in Figma: reproduces shipped screens, designs new features as concepts, sets up and changes design systems. Reads the product's design profile. |
| `skills/fetch-fireflies/`, `fetch-gmail/`, `fetch-slack/` | Pull client calls, emails and Slack threads into `docs/BA/intake/` — only the project's own, using the client emails and channels in the profile. |
| `skills/intake-and-triage/` | Turns intake into a triage report: new specs, Jira edits, dashboard items, notes — and carries out what the BA approves. |
| `skills/fetch-jira-backlog/` | Turns existing open tickets into spec stubs for `ba-spec`. |
| `skills/clarification-page/` | Builds and publishes the page the client answers questions on. |
| `skills/ba-dashboard/` | The project's BA dashboard, one page at one link with two tabs: **Map** (product → area → feature → items, coloured by stage) and **Board** (features by Jira release). Every feature with its clarification page, what is waiting on whom, your to-dos, the next call's agenda. Offered right after the project brief. |
| `skills/data-dictionary/` | The data dictionary: every entity and field with type, required, min/max and screen label, generated from the code, plus the collisions that confuse people. |
| `skills/messages/` | The messages catalogue: every email, in-app, push and SMS message the system sends, with trigger, recipients and content. |
| `skills/jira/`, `skills/confluence/`, `skills/feature-brief/` | Jira helpers (comment, search, field edit, release folders), Confluence publishing, and client briefs on Confluence. |
| `skills/ba-spec/` | Writes one spec in the template and takes it through the ready gate to its hand-off (Jira ticket or PRD). |
| `skills/ba-spec/assets/spec-template.md` | The spec template — the only copy that is ever edited. |
| `profile/` | The profile layout, a blank example, the real project profiles for Acme Lending and NWE, and their design profiles (`examples/design/`). |
| `docs/` | How the BA work runs: the guide (`our-ba-approach.pdf`, built from `guide-src/`), the setup manual, a new project, and the day-to-day loop. |
| `scripts/install.py` | Installs or updates every skill and the template in a project. |

Still to do: package it as a BMad module, so it installs like the rest of BMad.

## First day

Read [`docs/new-ba-onboarding.md`](docs/new-ba-onboarding.md). In short:

1. Install Claude Code, Git, Node 22 and uv.
2. Clone this repo, e.g. to `C:\dev\ba-tools`.
3. Install it into your project: `uv run --with pyyaml python C:/dev/ba-tools/scripts/install.py <project folder>`.
4. Start Claude Code in the project and say **"ba-setup"**. It checks everything and tells you what to
   do next.

## Getting an update into a project

1. `git -C C:/dev/ba-tools pull`
2. `uv run --with pyyaml python C:/dev/ba-tools/scripts/install.py <project folder>` — replaces the
   ba-tools skills and the template, sets the profile's version, never touches other skills, never
   commits. Add `--dry-run` to see what would change first.
3. `git status` in the project, then commit.

`ba-setup check` tells you when a project is behind your ba-tools clone, and prints the command.

## Changing something

1. Change it here, never in a project.
2. Bump `ba_tools_version` in the template header and the example profiles; add a line to
   `CHANGELOG.md`.
3. Push, then update each project as above.
