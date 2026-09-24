# Step 1 — Load and classify

**Read:**

- `assets/spec-template.md` in this skill — the whole file, every run.
- The profile (loaded in step 0) — you need `products`, `ids`, `prd`, `release_folders`, `downstream`.
- The source the BA points at: a triage `proposed_action: spec` block, an intake file, a PRD open item,
  a Jira ticket, or the BA's own words. Quote it; do not paraphrase it into something it did not say.
- The PRD (`prd.paths`) — find the FRs this touches (grep the FR headings and read the sub-heading).
- The next free id, by `ids.source`:
  - `register` — read `next_free` in `ids.register`.
  - `highest-existing` — find the highest number matching `ids.format` across every path in
    `ids.scan`, and add one. Check **all** of them: a PRD FR can exist with no spec.
- Existing specs on the same area: `grep -ril '<keyword>' docs/BA/specs`. If one already covers it,
  stop and tell the BA — update that spec instead of writing a second one.
- Jira, only when `downstream` includes `jira`: search open tickets in the product's `jira_project`
  for the same thing. If one exists, stop and tell the BA.

**Decide and tell the BA, in one short block:**

| Field | How |
|---|---|
| Lane | quick spec or change request (see SKILL.md) |
| `product` | a `key` from the profile's `products` |
| `id` | a **new capability** no existing FR covers → hold the next free id now (step 9 records it). Only **changes** existing FRs → `'-'` |
| `covers` | the existing FRs it changes or builds on, most relevant first |
| `size` | from the template's size table (xs · s · m · l; xl → split) |
| Folder | `release_folders: true` → `{product}/{release-slug}/`, `backlog` unless the BA names a release that exists in Jira. `false` → `{product}/` |
| Slug | kebab-case, what it is in plain words |

Prefer **change** over **new** when an existing FR's wording already covers the capability.

Stop here and let the BA correct any of these before step 2. A wrong size or a wrong `id` is cheap to
fix now and expensive later.
