---
name: messages
description: Keep the project's messages catalogue — every message the system sends by itself (emails, in-app and push notifications, SMS), each with an id, channel, trigger, recipients, subject, content, conditions, status and the spec behind it — as data in docs/BA/messages.yaml and a searchable page. Use when the BA says "which emails does it send", "what notification goes out when…", "add this message", "messages catalogue", when a spec adds, changes or retires an automatic message, and before a phase PRD goes to development.
---

# messages

**Every message the system sends by itself, in one place** — who gets what, when, and what it says. These
are the requirements most often missed: a feature ships and nobody wrote down the email that should have
gone with it, or two messages fire for one event. Testers, designers and the client all need the list.

The catalogue lives in **`docs/BA/messages.yaml`** (the data) and **`docs/BA/messages.html`** (the page, built
from it — never hand-edited). A spec names a message by its **id**: a rule ends in `[msg: M-012]`.

## Step 0 — every run

- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status` (`<skills>`
  = the folder this skill is installed in, one level up). No passing stamp → `ba-setup check`.
- The profile's `tools.messages` names the file (normally `docs/BA/messages.yaml`) and, if it is published,
  the page's link.

```
uv run --with pyyaml python <skills>/messages/scripts/messages.py <command>
```

## One message

| Field | What goes in it |
|---|---|
| `id` | `M-001`, `M-002`, … — given by `add`; never reused, never renumbered |
| `name` | what it is, in plain words ("Password reset", "Application approved") |
| `channel` | `email` · `in-app` · `push` · `sms` — one message per channel; the same event by email and push is two messages |
| `product` | a product from the catalogue's `products` list |
| `trigger` | the event that sends it, in the user's terms |
| `recipients` | who receives it — by role, and which one (the applicant, not "the user") |
| `conditions` | when it is **not** sent, or only sent (optional) |
| `subject` | the subject line or notification title (optional for SMS) |
| `content` | what it says — the text, or a summary with its variables |
| `status` | `live` (in the code today) · `planned` (a spec adds it) · `retired` |
| `spec` | the spec that added or last changed it |
| `source` | where it lives in the code — the template file and the service that sends it |
| `notes` | anything else, including where the entry was imported from |

## Commands

| To | Run |
|---|---|
| Start a catalogue | `init --title "<Project> — Messages" --products "A,B"` |
| See the next id | `next-id` |
| Add a message | write it to a small YAML file, then `add --item <file>` |
| Change one | `set M-012 --item <file>` (only the fields in the file change) |
| Build the page | `build` |
| Counts | `list` |

## From a spec

When a spec's rules make the system send something:

1. Look for the message in the catalogue first — the event may already send one.
2. New message → `add` it with `status: planned` and `spec: <the spec's path>`, and end the rule with
   `[msg: M-0nn]`. Changed message → `set` it and name the spec. Removed → `status: retired`.
3. When the feature ships, set `status: live` and fill `source` from the code.

## Filling it from what exists

A catalogue is usually started from what the code already sends: read the notification service and its
templates on the development branch, or import a document that did so — every imported entry keeps a
`notes` line naming where it came from. **Never invent a recipient or a trigger**: where the source does not
say, write "not stated in the source — check the code".
