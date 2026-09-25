---
name: data-dictionary
description: Build and check the project's data dictionary — every entity and field the product has, with type, required, min/max, the label the screen shows, and what it means — generated from the code so it cannot go stale, plus a hand-written layer for meaning and "never confuse with". Reports the confusions that cause bugs — one name with several types, one screen label used for fields of different entities, a plain text column where a checked list exists. Use when the BA says "what is this field", "is this name taken", "which entity has…", "update the dictionary", "data dictionary", when a spec adds or renames a field, and before a phase PRD goes to development.
---

# data-dictionary

**One name, one meaning.** The dictionary is where a BA, the client, a developer — and Claude — check a
name *before* a spec or a screen uses it. It exists because the same word on two entities, or the same
screen label on two different fields, confuses everyone and ships as a bug.

It is **generated from the code** (the Prisma schemas, the shared enums, the UI copy) and rebuilt on every
run, so it describes the product as it is. What code cannot say — what a field means, what it must never be
confused with, a limit the screen enforces — is written by hand in the **overlay** and merged in.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status` (`<skills>`
  = the folder this skill is installed in, one level up). No passing stamp → `ba-setup check`.
- The project keeps three files, named in the profile as `tools.dictionary.config` (normally
  `docs/BA/data-dictionary.config.yaml`):

| File | What it is | Edited by |
|---|---|---|
| the **config** | which code to read: the schemas, the enum folders, the UI copy, and which screens speak for which entity | the BA, once per project |
| the **overlay** (`overlay:` in the config) | meaning, labels, min/max, required, "means NOT", rulings on collisions, planned names | the BA, as specs settle names |
| the **dictionary** (`out:` in the config) | the generated page | nobody — rebuild it |

- `git fetch` every repo the config names before building: schemas are read from the remote branch, never
  the local checkout.

## Build

```
uv run --with pyyaml python <skills>/data-dictionary/scripts/generate.py --root .
```

Add `--check` to only report whether the page is out of date. The output names every source it read.

## What the page holds

1. **Reserved words** — one word, one job (from the overlay).
2. **Collision report** — one field name with several types; one enum value in several lists; look-alike
   lists; the database and the shared contract disagreeing; a plain text column where a checked list
   exists; and **the screen and the schema using the same word for different things**.
3. **Enum registry** — every list, its values, and how the screen displays each value.
4. **Entity registry** — per entity: field, type, **required**, **min / max**, column, allowed values,
   **display name** (the UI label), description, notes.
5. **Screens** — screen names and where they live (from the overlay).
6. **Planned terms** — names a spec has reserved that are not built yet.

**Display names** come from the app's translation files, scoped to the screens that speak for an entity
(`labels.i18n` + `labels.model_namespaces`), or — where the app keeps its copy in constant files — from
`labels.strings_ts`, matched by name and shown as **suggested**: check a suggested label before relying
on it, and confirm or correct it in the overlay with `display:`.

## Using it while writing a spec (ba-spec step 6)

For every field or label a spec adds, renames or relies on:

1. Look it up in the dictionary (search the page for the name and for the label text).
2. **The name or label is already used for something else** → rename it, or record in the spec why the
   same word is right, and add an `accepted:` ruling to the overlay.
3. **A new field** → add it to the overlay as `### field:<Entity>.<name>` with `status: planned`,
   `source: <spec path>`, `display:`, `description:` and any `min:` / `max:` / `required:`. The row turns
   into a real one when the code ships.

## Starting one on a new project

1. Copy `assets/config.example.yaml` to `docs/BA/data-dictionary.config.yaml` and fill in the schema
   paths (and label sources, if the app has them). No code yet? Leave `schemas` empty and write the
   planned entities in the overlay — the page still builds.
2. Copy `assets/overlay.example.md` to the overlay path.
3. Build, and add `tools.dictionary.config` to the project profile.
