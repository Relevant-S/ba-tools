# The dashboard page (Map + Board)

The files that build the BA dashboard page. The skill's `SKILL.md` says when and how to use them;
this file says what each one does.

| File | What it does |
|---|---|
| `build.py` | Joins `docs/BA/dashboard.yaml`, the clarification YAMLs and the Jira files into `docs/BA/mind-map/mind-map.html`, and writes `docs/BA/mind-map/stages.json` for the clarification pages. `--refresh` re-reads Jira first. |
| `template.html` | The page. `build.py` puts the data in place of `/*DATA*/null`. |
| `jira-tickets.mjs` | Reads every ticket the dashboard mentions: status, component, parent, finish date. |
| `jira-areas.mjs` | Reads every component (area) in the projects, with its open tickets and last finished ones. |
| `jira-releases.mjs` | Reads every release, every ticket in a release, and every open ticket with no release (for the Board). |
| `sync.py` | Writes the notes and "Resolved" ticks saved on the map back into `dashboard.yaml`. |

The Jira scripts only read. They need `node` and `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`.
`build.py --refresh` runs them with the projects from the profile.

What lands in the project's `docs/BA/mind-map/` folder: `refs.json`, `tickets.json`, `areas.json`,
`releases.json` (the Jira files), `stages.json` and `mind-map.html`. Commit them with `dashboard.yaml`.

## Rules the page follows

- Six stages, same on every project: Concept (grey), Spec & design (purple), Ready for dev (blue),
  In dev (magenta), In QA (amber), Done (green, tick in the middle). No red for stages.
- A feature with several tickets takes the stage of its slowest open ticket.
- A parent's ring is split by its children's stages, each sector sized by how many are in it.
  A bubble with no children is one colour.
- Red badge = open client questions. Orange badge = items waiting over 30 days.
- An area is active when it has dashboard work, a ticket being built or tested, or a ticket
  finished in the last 30 days. The rest fold into "Quiet areas".
- "Hide done > 2 weeks" is on by default.
- On the Board, a card is the dashboard feature a ticket belongs to; else its Jira epic; else "Other
  tickets" in its area. A feature with tickets in two releases has a card in each. The release named
  "Backlog" counts as no release.
- A ticket that two features both claim goes to the later feature in `dashboard.yaml`. Give each
  feature its own `tickets:` list to avoid that.
