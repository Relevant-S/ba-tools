# Jira ticket description — the storefront of a spec

The ticket is **the storefront of the feature**, not a copy of the spec. Two readers use it:

- **Developers** build from the spec (with BMad). From the ticket they need a plain summary of what
  must be done, so they know what they are picking up before they open the spec.
- **Manual QA** test from the ticket. It must hold everything a tester needs to set up the data, run
  the checks and know what "passed" looks like — without reading the spec.

Write it in plain words, short sentences, in the order below. **Never paste the spec body** — no rule
numbers, no edge-case table, no decision log. A section with nothing to say is left out (except
*How to test*, which every ticket has).

---

```markdown
## What and why

<2–4 sentences. Who has the problem, what it is, and what changes for them. Say who asked for it and
when — "Asked for by <name> on the <date> call".>

## Where

<The click path, outermost first, in the words on screen: Admin → Applications → Disbursements → the
filter bar → Xero bill status. One line per screen when there are several.>

## What changes

- <One bullet per visible behaviour: what the user sees or can do afterwards.>
- <The exact labels, options and messages, quoted, when the change adds or renames any.>
- Nothing else changes: <the nearby things a reader might expect to move and that do not>.

For developers: <1–3 sentences pointing at the files or modules to change, named plainly, and any step
that is easy to forget (regenerate the API client, run the migration with --create-only). Not a build
plan — the spec has that.>

## How to test

**Before you start (test data):** <the role to log in as, the environment, and every record the test
needs, with how to create it. If a case cannot be set up through the product, say so and who can set it
up (for example "needs a developer").>

**Steps**

1. <Action.> → <Expected result.>
2. <Action.> → <Expected result.>

**Regression:** <what already worked and must still work — the neighbouring filters, buttons or flows.>

**Not allowed:** <for a change that depends on the role: log in as a role that must not see or do it,
and what that user sees instead. Leave this out when every role is unchanged.>

## Known limits (not bugs for this ticket)

- <Existing behaviour a tester will run into and should not file against this ticket, with the reason.>

## Spec

[<spec path>](<spec_links.repo_url>/blob/<spec_links.branch>/<spec path>)
<Figma: [<page → frame name>](<link>) — when there are screens.>
```

---

## Where the content comes from

| Ticket part | Spec section |
|---|---|
| What and why | 1 Need, 6 Decisions (who asked, when) |
| Where / What changes | 3 Rules, 13 UX — rewritten as behaviour, without the `R` numbers |
| For developers | 14 Existing code — the files to extend, in a sentence or two |
| Test data | 4 Edge cases E1–E2 (what exists on day one), 14 (how records are created) |
| Steps | one or more steps per rule in 3, each with its expected result |
| Regression | 5 Out of scope, 14 "do not touch" |
| Not allowed | 4 E9, 11 Roles |
| Known limits | 4 Edge cases that stay as they are, 5 Out of scope |

## Before creating it

Read the *How to test* part as a tester who has never seen the product's code: can every record in
*Before you start* actually be made the way it says? Check the code when unsure — a test-data step that
cannot be done is the most common mistake in this section.
