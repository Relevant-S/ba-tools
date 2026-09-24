# ba-setup design — a product's design profile

Writes `docs/BA/design-system/<folder>/design-profile.yml` for one product: its Figma files, its design
system, its tokens, its frame sizes and its traps. `figma-build` reads it on every run. Start from
`skills/figma-build/assets/design-profile.example.yml`; three real ones are in
`profile/examples/design/` in ba-tools.

Run it once per product. Ask which product first if the project has more than one.

## Which path

Ask one question: **does this product already ship, with frontend code the design must match?**

- **Yes → Path A, existing product.** The code is the source of truth; the profile is read out of it.
- **No → Path B, new product.** The design leads; the design system is set up from a kit and the brand.

## Path A — existing product

1. **Figma files.** Ask for the link of the design file (where screens are built) and the
   design-system file (may be the same). The key is the part after `/design/`. Check each with the Figma
   connector (`get_metadata` on the file).
2. **Library key.** Run `get_libraries` on the design file. Show the subscribed libraries; the BA picks
   the design system. Record its key as `ds_library_key` and every other one under `ignore_libraries`
   — search results mix libraries otherwise.
3. **Pages.** List the pages with `use_figma` (`figma.root.children` — `get_metadata` without a node
   id misses some). Describe how they are organised in one or two sentences → `page_convention`.
   Generate the frame inventory (`skills/figma-build/references/inventory.md`) → `inventory`.
4. **Frame sizes.** Measure two or three finished screens of each kind (desktop, mobile, auth) →
   `frames`.
5. **Tokens.** Find the source in the frontend repo — the Tailwind config or preset, or the CSS
   variables file — on `origin/<code.dev_branch>`. Copy colours, type sizes, radius and the modal
   backdrop **exactly** → `tokens`, with `source: code` and the file in `path`. Never invent a value,
   never merge two that look alike.
6. **Frontend.** Repo, app root, shared component package → `fe`.
7. **Registry.** If the product has a component list with keys, point `registry` at it. If not, build
   one from the live library (component sets and standalone components, name + key) and save it.
8. **Traps.** Ask: *"Any component or rule in this product that has caught you out?"* Add what the BA
   says, one line each. Add anything found while doing steps 1–7.

## Path B — new product

1. **Brand.** Ask for the brand guide or website, and collect: primary and accent colours, text and
   background colours, fonts, logo, corner radius. Record them as `tokens` with `source: brand-guide`.
2. **Kit.** Ask which frontend stack the developers plan (a React + Tailwind + shadcn stack → the
   shadcn kit). Recommend starting from a stock kit; the BA duplicates it into the client's Figma team.
   That copy is the design-system file.
3. **Apply the brand** — run `figma-build` in design-system mode (`references/design-system.md` there):
   variables from the tokens, the kit's components bound to them, the library published.
4. **Design file.** A new file for screens, with the library enabled — or the same file, if the BA
   prefers one file. Set up pages by product area → `page_convention`.
5. Fill in `frames` (ask the target devices), `registry` (from the live library), `concepts_register`
   (a new empty register), `inventory`.

## Then

1. Show the profile as a list of values. On yes, write it.
2. Add its path to the product in the project profile (`products[].design_profile`).
3. Run `check-project`. Do not commit — list the changed files and ask.
