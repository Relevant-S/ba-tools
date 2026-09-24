---
name: figma-build
description: Build or change screens and design-system components in Figma for any project — reproduce a screen the product already ships (from the frontend code), design a new feature or change as a concept (from the spec), or set up and change a product's design system (from the brand or the code). Reuse-first — clone the nearest finished screen, change only what differs, design-system components only, one screenshot. Reads every project value from the product's design profile. Use when the BA says "build this screen", "draw this in Figma", "figma-build", "make a concept for", "design this feature", "add this to the design system", or when a spec reaches its design step.
---

# figma-build

One method for every project. Everything that differs between products — Figma files, the design
system and its component keys, colours, fonts, frame sizes, how pages are organised, product traps —
is in the product's **design profile**. This skill never names a project's keys or colours.

## Step 0 — every run

1. **Setup check.** Run `uv run --with pyyaml python ../ba-setup/scripts/setup.py stamp-status`. With no
   passing stamp, run `ba-setup check` first and continue only when nothing is ❌.
2. **Load Figma's own `figma-use` skill** before the first `use_figma` call — it is required by the
   Figma connector and holds the current API rules.
3. **Find the design profile.** The project profile (`docs/BA/specs/.ba-profile.yml`) gives each
   product a `design_profile` path. Pick the product from the BA's request or the screen; ask if it is
   unclear. No design profile → stop and send the BA to `ba-setup design`.
4. **Read `references/rules.md`** — the rules every mode follows — and the profile's `traps`.
5. **Read `references/plugin-gotchas.md` section 0 and the quick index** before writing a script; look
   up the rest when an operation is in doubt.

## Pick the mode

| Mode | When | Source of truth | Read |
|---|---|---|---|
| **reproduce** | a screen the product already ships — audits, and the base a change is drawn on | the frontend code | `references/reproduce.md` |
| **concept** | a new feature or a change — the design step after a thin spec | the spec + the design system | `references/concept.md` |
| **design-system** | set up a design system for a new product, or change a component | the brand guide, or the code | `references/design-system.md` |

Say which mode you are in, in one line, before the first call.

## The default is the quick method

Clone the nearest finished frame, change only what differs, use design-system instances, read only the
one piece of source that differs, one screenshot. **Escalate to the full, spec-first method only for a
genuinely new or complex screen — and say so before spending**, because it costs several times more.

## Finding frames

Use the product's generated **frame inventory** (the profile's `inventory`). If it is missing or a
page is not in it, regenerate it (`references/inventory.md`) — never conclude a screen does not exist
because one listing call missed it.

## When done

- Report where the result is: **Figma page name → Section → frame name**, and a link. Never a bare
  node id.
- Update the concepts register (concept mode) or the registry (design-system mode) in the same pass.
- A rule learned the hard way goes into ba-tools — `plugin-gotchas.md` if it is about the Figma API,
  `rules.md` if it is about how screens are built, the design profile's `traps` if it belongs to one
  product.
