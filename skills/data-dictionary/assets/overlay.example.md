# Data dictionary — the authored layer

This file holds what the code cannot say. Everything else in the dictionary is generated from the code and
rebuilt on every run. **Edit this file, then rebuild with the data-dictionary skill.**

Entry format — an H3 heading is the key, then `key: value` lines:

    ### field:Customer.firstname
    display: First name
    description: The customer's given name, as on their ID
    min: 1
    max: 50
    required: yes — the application form will not submit without it
    means-not: not the employer contact's first name

| Key | Used on | What it does |
|---|---|---|
| `display` | `field:` | the UI label, when the generated one is missing or wrong |
| `description` | `field:` | what the field IS, when the code has no `///` comment |
| `min` / `max` | `field:` | length or value limits the screen enforces |
| `required` | `field:` | when the screen requires more than the database does |
| `means` | `word:` | the one job this word is allowed to do |
| `means-not` | any | the confusion this entry exists to prevent |
| `use-instead` | `word:` | the word to reach for when you meant the other thing |
| `accepted` | `word:` / `field:` / `label:` | a ruling that a flagged collision is deliberate, with the reason |
| `status` | `enum:` / `model:` / `field:` | `shipped` · `planned` · `partial` · `retired` |
| `source` | anything planned | which spec reserved the name |
| `note` | `enum:` / `model:` | free text carried into the registry |
| `where` / `who` | `screen:` | where a screen lives and who reaches it |

---

## Reserved words

## Fields

## Screens

## Planned terms
