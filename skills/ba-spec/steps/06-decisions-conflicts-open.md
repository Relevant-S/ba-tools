# Step 6 — Out of scope, decisions, conflicts, assumptions, open (sections 5–9, and 10–13)

Write only the sections the size needs (template size table). In order:

**5. Out of scope** — two lists: *not in this spec* (what a reader might assume is included) and
*deliberately removed* (what exists today and this drops, with where that was decided). Retired vs
deferred.

**6. Decisions** — date, who, decision, source. Include the `[BA]` calls made while writing. Keep
closed questions here.

**7. Conflicts** — start with **"Checked against:"** and list what you actually compared, across every
product in the profile's `conflict_scope` (including the data dictionary, for names and labels): the FRs in
`covers`, other specs found in step 1, shipped code from step 5. Then "no collision", or each conflict
with both sides quoted. Record near-misses too.

**8. Assumptions** — *confirmed* (client agreed, date, source) and *assumed* (every `[BA]` rule). Every
assumed line also appears in section 9, unless the BA accepts it now.

**9. Open** — only questions the client or a developer must answer. Owner, critical or not, date
raised. Before adding one, check it is not already answered in the source, the PRD, or another spec.
"None" is a valid, meaningful entry.

**When their trigger applies:**

- **10. Data model** — new or changed stored data: real field names, new/changed/unchanged, migration
  or "no migration — all net-new". **Check every field name and screen label against the data
  dictionary** (the `data-dictionary` skill, *Using it while writing a spec*): a name or label already
  used for something else is renamed, or the reason it is the same is recorded here. New fields go into
  the dictionary's overlay as planned.
- **11. Roles** — behaviour differs by role: the template's full matrix, one column per role in the profile's `products[].roles.list`, a row for what
  the denied user sees; every `?` also goes to section 9.
- **12. NFRs** — only what differs from the platform default (the PRD's Non-Functional Requirements
  section is the default).
- **13. UX** — where the designs are (file, page, frame **name**), what is still to draw.

Then show the BA the section 9 list on its own and ask: "Anything here you can answer now?" Move every
answer into section 6.
