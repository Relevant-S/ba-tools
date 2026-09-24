# Mode: design-system — set up or change a product's design system

Two jobs: **setting up** a design system for a product that has none (usually run through
`ba-setup design`), and **changing** an existing one.

## Setting up — a new product

**Start from a stock kit, then apply the client's brand.** Faster than building from nothing, and the
kit's components already work (NWE started this way from a copy of the shadcn community kit).

1. **Collect the brand**: primary and accent colours, text colours, fonts, logo, corner radius, and any
   existing brand guide or website. Record them in the design profile's `tokens` with `source:
   brand-guide`.
2. **Pick the kit.** Prefer the one that matches the frontend stack the developers will use (a React +
   Tailwind + shadcn stack → the shadcn kit). Duplicate it into the client's Figma team; that copy is
   the design-system file.
3. **Apply the brand as variables**, not raw colours: create colour, type and radius variables from the
   profile's tokens and bind the kit's components to them. Use Figma's own `figma-generate-library`
   skill for this when the frontend code exists; by hand from the brand guide when it does not.
4. **Publish the library** and enable it in the product's design file.
5. **Write the registry** — the list of components with their keys — to the profile's `registry` path,
   from the live library, not from memory.
6. Fill in the rest of the design profile (`figma`, `frames`, `page_convention`) and run
   `ba-setup check`.

**When the frontend already exists** (an existing product new to ba-tools), the tokens come from the
code — the Tailwind config or the CSS variables. Record the file in `tokens.path` and mirror it
exactly: never invent a colour, never merge two colours that look alike.

## Changing an existing design system

1. **Edit the component, not the screens.** A published component is changed in the design-system file
   (the profile's `figma.ds_file`); an attempt to change it inside a consuming file fails with *"New
   parent is an internal, read-only node"*.
2. **Values come from the source** — the code in a shipped product, the brand in a new one.
3. **Tell the BA before starting that two manual steps will be needed**: publish the library, then
   accept the update in every file that uses it (rule 19). Until both are done, new properties do not
   exist on existing instances (`Could not find a component property`).
4. **Only add, never rename or delete** properties when instances already use them — renames lose every
   override.
5. **Keep the file tidy** (rule 20) and **update the registry** in the same pass.
