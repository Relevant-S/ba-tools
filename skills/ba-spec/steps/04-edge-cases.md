# Step 4 — Edge cases and failure paths (section 4)

Work the template's E1–E10 list, **every row**, in order. This is its own step because no earlier spec
workflow did it.

For each row write one of:

- what happens, in one or two sentences, with the rule it follows (`R3`), or
- `n/a` and, if not obvious, why — an empty cell reads as "nobody looked".

Pay most attention to:

- **E1 / E2** — fed by the cold walk in step 3.
- **E9 (not permitted)** — per role, using the product's real roles (SKILL.md hard rule 5). Say what the
  denied user sees: hidden, disabled with a reason, or an error. This is the most-missed row.
- **E3 (the write fails)** — when another system is involved (an accounting system, a CRM, a credit bureau, SMS, file storage), say
  whether the save fails, retries or half-succeeds.

Anything this step cannot answer goes to section 9 in step 6 — but only if someone else must answer it.

At size xs the template does not require section 4. Still run the list in your head; write the section
only if at least one row has a real answer.
