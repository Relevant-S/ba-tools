# Step 7 — Write the spec file

1. Copy the header block from `assets/spec-template.md` and fill every field. The `jira_*` fields
   are filled only when the profile's `downstream` includes `jira`; otherwise `-`. `status` is `draft`,
   or `eliciting` if section 9 has a question waiting on someone. `jira_ticket: -` until step 9.
2. Keep **only** the sections the size needs (template size table). Section 16 is always kept.
3. Lead with the title, then the lane line if it is a quick spec
   (*"Quick spec — <bug fix | internal-only>. <why no change request is needed>."*).
4. Check the length against the size's rough length. If it runs over, cut before adding — sections 4,
   7 and 14 are where specs grow; "n/a" is a whole entry.
5. Write it to `docs/BA/specs/{product}/{release-slug}/{slug}.md`.

Before moving on, re-read the file once as a developer who has never seen the source: can they build
it from this alone? Anything they would have to ask is either a missing rule or a section 9 question.
