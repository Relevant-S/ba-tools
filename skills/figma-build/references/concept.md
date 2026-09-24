# Mode: concept — design a new feature or a change

Source of truth: **the spec** (at least the thin spec — need and outcome), **the design system**, and
the product's design principles. There is no frontend code for it yet, so rule 13 reads "no labels the
spec does not give" — and every label you had to invent is marked as a proposal.

This is step 5 of the new-project flow and the design half of every change request: thin spec →
concept → client review on the clarification page → full spec.

## Where it lives

- **One concept page per feature, inside the product's design file**, next to the screens it changes —
  named `<profile concept_page_prefix><parent area> · <feature>` (for example
  `_Concept · Loans · Payoff confirmation`). A brand-new area: `<prefix><feature>`.
- On the page: an **Explorations** Section (`v1`, `v2`, `v3` … — nothing deleted) and one
  **For review** frame — the current candidate. The clarification page links to the For review frame.
- A row in the product's **concepts register** (the profile's `concepts_register`): concept, Figma page,
  parent page, spec, status, and which frames were cloned from which.

Status: **Exploring → In review → Approved → Shipped**, or **Parked / Rejected**.

## Building it

1. **Start from the real screen it changes.** Clone the current master frame (reproduce mode gives you
   one if it does not exist) and change it. A concept drawn from scratch drifts from the product.
2. **Design-system components only**, as in every mode. When the feature needs something the design
   system does not have, you may draw it — but name the layer `DS gap · <what it is>`, list it in the
   register row, and never style it to pass as an existing component.
3. **Write open questions on the frame itself**, in the profile's `concept_question_style` (amber note
   by default), so a design review cannot approve an open question by accident. The same questions go
   on the clarification page.
4. **One screenshot of the For review frame**, then update the register.

## After the client answers

- Update the frame and the register. Answers go into the spec's Decisions, not only into Figma.
- A correction to a frame goes into every frame cloned from it (rule 18).

## Promotion — when the feature has shipped

Promotion means **updating the master design**, not parking the concept frames beside it. It is done
when no master screen still shows the old state.

1. Re-check the concept against what is live (`origin/<code.live_branch>`). The master can be right and
   the concept stale.
2. Find **every** surface the change touches — list states, modal frames whose backdrop is a copy of the
   changed page, component instances.
3. If the change is to a shared component, **change the component**, not the screens — and first check
   no other screen depends on it behaving the old way.
4. Add new frames only for genuinely new states; update the rest in place.
5. Register row → Shipped, pointing at the master. Name a Figma version by hand.
6. **Archive the concept page, do not delete it** — rename it `_Archive · … — shipped <date>` and move it
   under the profile's `archive_divider`.
7. Screenshot a master screen that was **not** part of the concept and check it shows the change.
