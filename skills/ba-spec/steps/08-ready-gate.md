# Step 8 — The ready gate (section 16)

Tick the template's section 16 boxes **by checking, not by assuming**:

| Box | How to check |
|---|---|
| Section 9 empty, or every item knowingly accepted | read section 9 |
| Every section 8 assumption confirmed or accepted | read section 8 |
| Section 4 answered or `n/a` on every row | count the rows (skip at xs if section 4 was dropped) |
| Conflict check actually run | section 7 starts with "Checked against:" and names real things |
| Every rule has a source tag | `grep -c '^- \*\*R[0-9]' <spec>` equals the number of lines ending in `]` |
| Design exists for every screen, or "still to draw" is listed | section 13, or "no screens" |
| Section 14 checked against a named commit | the "Checked at … @ <sha>" line exists |
| `size` and `downstream` set | the header |

**If every box ticks:** set `status: ready`.

**How to ask the BA anything at this gate.** Never ask about a rule number, an edge-case code or an
open-question id on its own ("confirm R6–R12?", "accept O-1?"). The BA does not hold those in their
head. For every item, write out **what it says**, in plain words, and **where it happens** (page → tab →
control). If it is wording, quote the exact text. A question the BA cannot answer without opening the
spec is a failed question — rewrite it.

**If a box does not tick:** refuse to call it ready. Show the BA the unticked boxes. The BA can either
fix them, or accept them — and then **each accepted box is written into the header** under
`accepted_risks`, one line each: which box, why it was accepted, who decided, date. Accepting a
blocker you can name is a decision; letting one through silently is not.

**Change-request lane:** even when ready, the spec is not filed until the client has approved it. Stop
here and tell the BA what goes on the clarification page for the client to approve. If the project
also shows the client a feature brief or Figma designs (`client_representations`), check their
comments first — an unanswered comment there is an open question.

**Then show the BA the whole spec and ask for an explicit yes to hand it off.** Nothing goes to Jira or the PRD before
that yes.
