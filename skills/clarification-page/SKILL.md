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
4. **The page frame**: `name` (short feature name), `url` (the page's published link — it is how the
   page finds its stage in `docs/BA/mind-map/stages.json`, written by the dashboard build, so the page
   and the dashboard map always show the same stage; fill it in after the first publish), `round`
   ("Round V7 · sent 22 Oct 2026 by …"), `description` (1–2 sentences), `problem` and `solution`
   (1–3 sentences each). The side panel shows progress, the Send button and a timeline; "Back to the
   map" opens the dashboard on this feature. A project with no dashboard map yet shows the stage from
   the `events` and no Back button.
5. **Say what is already decided** in `decisions`, so the client is never asked twice: one entry per
   decision — `id`, `date`, `who`, `how`, `title`, `detail`. Put `who` only when a source names the
   person; never guess. They show collapsed under "Answered questions", where the client can request a
   change, and dated in the side panel's timeline. `events` add rounds sent, documents received and
   stage changes (`kind: stage`, `stage: concept|spec|ready|dev|qa|done`) to that timeline. An old page
   with only `settled:` still builds (each line becomes an undated decision with no person).
6. **Screens** — every screen gets an "Open in Figma" button to its frame. The Figma `node` id is the single source: it builds the link and names the file
   `screens/<slug>-<node with the colon as a hyphen>.png`. Pull each frame with the Figma connector's
   `get_screenshot` (`maxDimension: 1400`) and save it there.
7. **Generate:**

   ```
   cd docs/BA/clarifications
   uv run --with pyyaml --with pillow python <skills>/clarification-page/scripts/_generate.py <slug>-decisions.yaml
   ```

   It writes `<slug>-decisions.html` beside the YAML, embeds the screens (downscaled to 1200px WebP —
   without Pillow they embed full size), and prints each screen's file date. If the YAML will not
   parse because a value contains a colon, run `scripts/_fixyaml.py <file>` once.
8. **Never hand-edit the HTML.** Change the YAML and generate again. The template is
   `scripts/_template.html` in this skill — the only one; `docs/BA/clarifications/_generate.py` just
   runs this skill's script.

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
- **And run portal-publish** when the profile has `tools.portal`, in this order:
  1. Publish the Artifact (above).
  2. Put its real link in the YAML's `url:` line. The Portal links the page to its Dashboard Feature by
     that link; a placeholder is left out with a warning.
  3. Run `portal-publish page <slug>` (the YAML's `slug:`). It sends the page and its screens to the
     Relevant Clients Portal, where the Client answers it. It shows the BA what the Client will read and
     sends only after a yes; if the BA says no, nothing is sent. With two or more products, the page goes to
     the Portal project of its Feature's product (the Feature whose `clar.url` is the page's `url:`; "Both"
     sends it to every product's project, one yes or no each). A page no Feature links goes to the first
     product's project.
  4. When the link is new, run `portal-publish dashboard` too, so the Client's Dashboard links to the page.

  Each round needs its own `store_key` and `round:` line: a Round the Client has already answered
  cannot be replaced.
- **Always publish with `capabilities: {"db": {}}`, on every publish of a question page.** The
  **Send answers to Claude** button stays hidden unless the page may use its own small database. It
  saves the answers to collection `answers`, doc `latest`. A page first published without this never
  shows the button, and leaving the field out on a later publish only carries the missing setting
  forward. A publish warning that the page "refers to the `db` capability but doesn't declare it" means
  exactly this: publish again with the declaration. After the first publish with it, run one
  `ArtifactData list` on `answers` to confirm the store answers (empty is fine). A page with no open
  questions still lets the client request a change to a decision, so it keeps the declaration too;
  only a page with no questions and no decisions has no buttons.
- **There is no email button, and there cannot be** — an artifact page cannot open the reader's mail
  client. *Send answers to Claude* and *Copy all answers* are the whole mechanism.

## When the answers come back

1. Get the answers. Take the one path that fits how the page went out:
   - **The page went out through the Relevant Clients Portal** (the profile has `tools.portal`): run
     `fetch-portal`. It writes the Client's sent Answers to `docs/BA/intake/`, one file per page, and
     offers `/intake-and-triage`. Do not also read the artifact page's answers for this page.
   - **The page is an artifact page:** if someone pressed **Send answers to Claude**, read them with
     `ArtifactData get` (the page's link, collection `answers`, doc `latest`). Otherwise the client pastes
     them, usually in Slack or email, and the fetch skills pick them up as intake.
2. Put each answer into the spec's **Decisions** once (date, who, the answer, the source), whichever path
   it came by. Before adding one, check it is not there already. The artifact page's sent record also has
   `changes`: requests to change an earlier decision — treat each like a new answer. A Portal Answer that
   "Replaces the answer sent …" updates the earlier Decision instead of adding a second one.
3. Rebuild the page: answered questions move to `decisions` (with date and who), new questions take
   their place, add a `round` event, **and
   re-pull the screens** — a screenshot from two rounds ago is the one thing nobody thinks to check.
4. Repeat until nothing is open.
