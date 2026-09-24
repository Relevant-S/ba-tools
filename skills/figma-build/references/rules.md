# Figma rules — every project, every mode

The rules a build must never break. Each one cost a real correction. Project values (file keys,
component keys, colours, frame sizes, page names) are in the product's design profile, never here.

## Where things go

1. **Every screen is on the right page.** The design profile's `figma.page_convention` says how pages
   are organised (for example, one page per sidebar section under a role divider). A screen on the
   wrong page is a defect even if the screen is perfect.
2. **`clone()` puts the copy on the first page of the file, not beside the source.** After every
   clone or build: `targetPage.appendChild(node)`, reset `x`/`y`, then walk `node.parent` up to the
   `PAGE` and check its name. A screenshot will not show a wrong page.
3. **Group frames in transparent Sections** (`section.fills = []`): list views in one row with their
   sibling tabs; sub-flows left to right below the parent; states and modals in their own Sections.
   Children inside a Section use coordinates **relative to the Section**.
4. **Frames use the profile's `frames` sizes.** Grow the height for long content; never the width.

## What a screen is made of

5. **Every control is a design-system instance.** Buttons, inputs, selects, checkboxes, badges, tables,
   modal shells, icons. Raw frames are for layout only. Search the design system **before** drawing —
   and search for whole patterns (a filter bar, a list table) before atoms.
6. **Search the live library, not a list you remember.** Start from the profile's `registry`, but a
   registry can be stale: when it says something does not exist, check the live library
   (`search_design_system`, scoped to `figma.ds_library_key`, one word at a time).
7. **Match a component by what it looks like, not by its name.** Before using a component, compare its
   font, size, weight, colour, height and alignment with what the screen needs. The closest name can be
   visibly wrong. When nothing matches, build the unit once as a local component, use instances of it,
   and record the gap.
8. **A component slot takes only components from the project's own design system** — never from a
   vendor kit or an old library the project is moving away from. Copy a missing one into the design
   system first.
9. **Icons are colour-neutral and recoloured where they are used**, through a semantic colour token.
   Never make a green, a red and a blue version of the same icon. Never draw an icon from SVG when the
   design system has it.
10. **Modals sit over their page on a dimmed backdrop** — one frame holding a copy of the page the modal
    opens from, a full-frame scrim (the profile's `tokens.scrim`), and the modal panel centred on top.
    The frame is tall enough to show the whole modal.
11. **Replace placeholder icons.** A design-system button with its icon switched on often carries a
    stand-in glyph. Swap it for the real one every time.
12. **Only resize an instance on the axis the layout really constrains.** Leave the other axis at the
    main component's size, or content is cut off. Let auto-layout divide equal columns
    (`layoutSizingHorizontal = 'FILL'`); do not add up widths by hand.

## What a screen says

13. **No invented labels, columns, options or copy.** Sample *data* (names, amounts, dates) is fine;
    anything that is UI text — a column header, a button label, the choices in a dropdown, a
    component's default placeholder — must come from the source (the frontend code in `reproduce`, the
    spec in `concept`). When the source leaves a cell empty, the cell is empty.
14. **Check the source before drawing something new.** A queued screen, an old frame or an earlier
    session's notes are not evidence a thing exists. In `reproduce`, grep the frontend for it first.

## Checking work

15. **"Check the text" means every property of that text**: family, size, weight (per segment),
    colour (per range), line height, letter spacing, alignment, casing — in one pass.
16. **"Check this screen against the frontend" means every element and every attribute**: padding,
    gaps, order, alignment, widths and column spans, fonts, variant states, copy. Read the node values
    back; do not judge from a scaled screenshot.
17. **Form fields agree with each other.** Before calling a form done, read back every field's label
    size, font and colour, and every box height and width, and check they are uniform (or differ exactly
    where the source says they do).
18. **A fix to a frame does not reach the frames already cloned from it.** When you correct a frame,
    find its clones (the concepts register records them) and fix them in the same pass.

## Design-system edits

19. **Changing a published component needs two manual steps by the BA**: publish the library, then
    accept the update in each file that uses it. The plugin API can do neither. Plan the pause before
    starting, and say so.
20. **Keep the design-system file tidy after every edit**: components in aligned rows, grown component
    sets resized to fit their variants, no overlaps, scratch pages emptied.

## Cost

21. **No sub-agents or forks for routine builds or for reading the frontend** — read it yourself.
22. **A routine tab costs a handful of calls.** If you are past a dozen, stop and rethink.
23. **One screenshot at the end**, and fix only what it shows is wrong. Read values back when the
    screenshot cannot settle a question.
24. **Build only what was asked.** Ask before adding footers, extra states or forms nobody requested.
