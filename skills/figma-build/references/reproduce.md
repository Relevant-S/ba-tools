# Mode: reproduce — draw a screen the product already ships

Source of truth: **the shipped frontend code.** Figma is being made faithful to it, never the reverse.
Where the code and an old Figma frame disagree, the code wins. Where the code's intent and the running
app disagree (a class the component silently drops), the running app wins — check a screenshot of
production.

## Default: the quick method

1. **Clone the nearest finished sibling frame** — same page family, already correct. It brings the
   sidebar, header, tabs and card chrome with it. Move it to the right page (rules 1–2) and rename it.
2. **Change only what differs**: breadcrumb, active tab, the content of the card.
3. **Use design-system instances** for every control (rules 5–8). Keys come from the registry.
4. **Read only the one frontend container that holds the difference** — its real layout class (grid or
   flex, number of columns, gap), not the parent's. The repo and app root are in the design profile
   (`fe`); read `origin/<code.dev_branch>` from the project profile, not the local checkout.
5. **One screenshot.** Fix only what it shows is wrong.

## When to escalate to the full method

Use the full method only for a **genuinely new or complex screen** — no finished sibling to clone, or
heavy conditional logic. **Say so before starting**, because it costs several times more.

**Full method:**

1. **Find every frontend file** for the screen — the page, its features, shared components, the
   design-system primitives. List them.
2. **Read them fully, including what renders when**: every condition, every empty / loading / error
   branch, every disabled state. The most common miss is a section that looks conditional but always
   renders.
3. **Resolve every token** to a real value from the profile's `tokens.source`. Never assume a size or a
   colour.
4. **Map every element to a design-system component** by look, not name (rule 7). Note each gap.
5. **Write a short screen note** — sections, elements, sizes, components, conditions — and build from it.
6. **Screenshot each state**, read back the component properties you set, run the checks in rules
   15–17.

## Done means

- On the right page, in a Section, at the right frame size.
- Every control an instance; every label from the code.
- The build-state note or memory updated, and the registry updated if the design system changed.
