---
name: clarification-page
description: Build, update and publish a client clarification page — one page per feature holding the questions the client still has to answer, each with its options and their consequences, the settled answers, and the screens the questions are about. It is the page the BA shares with the client on the call and collects the answers on. Generated from a YAML file per feature; answers come back by copy and paste and go into the spec's Decisions. Use when the BA says "make a clarification page", "put these questions to the client", "update the clarification page", "V2 of the … page", or when a spec's open questions need the client.
---

# clarification-page

**The clarification page is where the client answers** — in every project (`client_review` in the
project profile). The BA shares it on the call; the client picks options and writes notes; the answers
come back by *Copy all answers*. The feature brief and the Figma designs show the requirements; the
clarification page settles the questions.

**The page is a surface, never the record.** Every answer goes into the spec's Decisions section,
dated and attributed. If an answer only lives on the page, the spec rots and the two disagree.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`
  (`<skills>` = the folder this skill is installed in, one level up). No passing stamp → `ba-setup check`.
- The project keeps its pages in **`docs/BA/clarifications/`**: one `<slug>.yaml` per feature, the
  generated `<slug>.html` beside it, screenshots in `screens/`, and a `README.md` with the table of live
  pages and their links. Create the folder and the README table on the first page.
- Read the project profile for the products and the Figma files (`tools.figma.files`).

## Build a page

1. **Copy the shape of `assets/example-probate-decisions.yaml`** (the reference page) to
   `docs/BA/clarifications/<slug>-decisions.yaml` and replace the content. Give it its own `store_key`.
2. **Every page opens with a `design:` block** — one paragraph saying what the feature is in the
   client's terms (under 700 characters), plus the **one** screen the hardest question lands on
   (`hero: true`). The rest go behind the disclosure. **No design yet?** Ship the block with a summary
   and no screens. Never invent a screenshot, and never link a frame that does not cover the question.
3. **Questions** — only what the client must answer. Per question: the title, the context, the options
   (`v` · `t` · `d`), and for each option **the consequence**, not just the choice. Where we have a view,
   mark one `rec: true` and say it is ours. Put contradictions in the `snag` box, plainly.
4. **Say what is already decided** in `settled`, so the client is never asked twice.
5. **Screens** — the Figma `node` id is the single source: it builds the link and names the file
   `screens/<slug>-<node with the colon as a hyphen>.png`. Pull each frame with the Figma connector's
   `get_screenshot` (`maxDimension: 1400`) and save it there.
6. **Generate:**

   ```
   cd docs/BA/clarifications
   uv run --with pyyaml --with pillow python <skills>/clarification-page/scripts/_generate.py <slug>-decisions.yaml
   ```

   It writes `<slug>-decisions.html` beside the YAML, embeds the screens (downscaled to 1200px WebP —
   without Pillow they embed full size), and prints each screen's file date. If the YAML will not
   parse because a value contains a colon, run `scripts/_fixyaml.py <file>` once.
7. **Never hand-edit the HTML.** Change the YAML and generate again.

## Publish

- Publish the HTML as an artifact to the **same file path every round**, so the link never changes.
  Label each round (V2, V3). Publish straight over the live page (`force: true`) — nobody hand-edits
  these pages; the generated page names its own screens in a `DESIGN SCREENS` comment at the top.
- **The share pin does not move by itself.** After a new round, tell the BA to move it from the
  artifact's share menu, or the client keeps seeing the old version.
- **Put it on the dashboard — every time, as part of publishing.** Run the `ba-dashboard` script:
  `set-clar --feature "<the feature's area>" --url <this page's link> --label "Clarification page — V<n>, <k> questions"`
  with `--open <file>` holding the page's open questions (one line each, the client's words), and
  `--new <file>` the first time, when the feature has no row yet. Then `build` and publish the
  dashboard to its link (`tools.dashboard.url`). **The dashboard is the register of clarification
  pages** — this is how a BA finds a page after it is created.
- **There is no email button, and there cannot be** — an artifact page cannot open the reader's mail
  client. *Copy all answers* is the whole mechanism.

## When the answers come back

1. The client pastes the answers — usually in Slack or email, which the fetch skills pick up as intake.
2. Put each answer into the spec's **Decisions** (date, who, the answer, the source).
3. Rebuild the page: answered questions move to `settled`, new questions take their place, **and
   re-pull the screens** — a screenshot from two rounds ago is the one thing nobody thinks to check.
4. Repeat until nothing is open.
