# Step 3 — Rules, and the cold walk (section 3)

**First, walk it cold.** Before writing a rule, answer these three in the draft's scratch notes:

1. Nothing exists yet — no records, no history. What does the user see on day one?
2. Where does the very first one come from?
3. What is already true in the world, or already in the database, that this feature does not know
   about and will get wrong on the day it ships?

Whatever this finds becomes a rule, an edge case (E1, E2 in step 4), or an open question.

**Then write the rules.**

- Numbered `R1`, `R2`, … Numbers never change meaning; a withdrawn rule is struck through and keeps its
  number.
- One testable statement each. If a tester could not check it without reading code, rewrite it.
- Every rule ends with its source tag: `[src: <file>#<line or timestamp>]`, `[design]`, `[BA]` or
  `[PROPOSED]`. Nothing enters without one.
- `[BA]` rules also go to section 8 as assumptions; `[PROPOSED]` rules also go to section 9.
- Group by entity or screen when there are more than about eight.

A rule that restates shipped behaviour (for example, what the screen already enforces) says so — it is
not new behaviour, and that matters for the quick-spec lane.
