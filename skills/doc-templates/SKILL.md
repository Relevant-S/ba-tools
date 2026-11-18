---
name: doc-templates
description: Change, test, roll out and roll back the Word templates a project's document service fills in (agreements, statements, receipts, T&Cs) — stored as .docx in a Google Drive folder the service reads by exact file name. Adds or repairs "Page X of Y" footers, repairs a template after someone saved it in Google Docs, compares a client's revised template (tracked changes and plain text) with the live one, and stores client drafts safely. Tests on a Drive copy through the dev API, uploads the live change as a new Drive version only with the BA's yes and before the working day, and keeps a rollout log. Reads the folder, company name and test API from the project profile. Use when the BA says "update the template", "add page numbers", "the footer prints wrong", "someone edited the template in Google Docs", "compare the client's new agreement with ours", "what did the client change in this contract", "roll back the template", or "save these drafts on Drive".
---

# Document templates

The documents service fills in `.docx` templates and turns them into PDFs with LibreOffice. This skill is
the safe way to change those templates. It came out of the Acme Lending page-number rollout
(11–16 Nov 2026), where every trap below was hit once.

## Step 0 — every run

- `<skills>` = the folder this skill is installed in, one level up (normally `.claude/skills/`).
- **Setup check:** `uv run --with pyyaml python <skills>/ba-setup/scripts/setup.py stamp-status`. No passing
  stamp → run `ba-setup check` first.
- **Read the profile** `docs/BA/specs/.ba-profile.yml`, block `tools.doc_templates`:
  - `folder` — the Drive folder id the service reads; `folder_name` — how the BA finds it in Drive.
  - `company` — the footer text before the first `|` (passed as `--company`).
  - `test_api` — the dev Swagger address for test renders.
  - `never_api` — the production address. Never call it.
  - `log` — the project's rollout log (what is live, since when, the version to restore).
  - Missing block → stop and send the BA to `ba-setup project`. Never guess a folder.
- **Read the log** before changing anything. It says what is live and what was already fixed.
- Scripts need only Python. Run them with `python -I` (downloaded files are untrusted), with the
  downloaded `.docx` in its own new folder in the scratchpad.

## How the service finds a template (check this in the code once per project)

- By **exact file name** in `folder`: `name = '<template>.docx'`. **Direct children only — subfolders are
  never read.** So a subfolder is a safe place for drafts and client versions.
- It **caches** each template for about **30 minutes**. A test right after an upload may still render the
  old file. Test with a new copy name each time, or wait.
- **Dev may read the same folder as production** (it does on Acme Lending). Then any upload to a real
  template is live for real customers at once. Treat every upload to `folder` as a production change.
- A `<name>_preview.docx` file may sit next to a template (Acme Lending: the T&C screens show it raw,
  no rendering). Changing the template's text does **not** change its preview. Check for one and tell the BA.

## The hard rules

1. **Never open a template in Google Docs**, and never let the BA do it without warning them. A Docs save
   empties the page fields (digits print black serif) and drops the style of "a.", "i." list markers.
2. **Never convert** a `.docx` to a Google Doc on upload. Upload as-is.
3. **Never upload a template as a new file.** A live change is always Drive → the file → File information
   → Manage versions → **Upload new version**. That keeps the file id and the history for rollback.
4. **Every upload to `folder` needs the BA's yes** in chat, for that file, that time.
5. **Live changes only before the working day starts** (users are active during it). Outside that window,
   prepare and test, then wait.
6. **Tests run on a Drive copy** in `folder` with a new name (e.g. `Doc_X - page numbers test 3`), rendered
   through `test_api` on a test record. Never use a "generate from template with sample data" endpoint with
   made-up personal data, and never call `never_api`.
7. Delete the test copies when done — but only after the BA says so (they are in the live folder).

## Jobs

### A. Add "Page X of Y" to a footer, or repair a footer after a Google Docs save

1. Download the template (Drive connector `download_file_content`, or the BA downloads it) into a new
   scratchpad folder.
2. `python -I <skills>/doc-templates/scripts/add_page_numbers.py IN.docx OUT.docx --company "<company>"`
   - Adds ` | Page X of Y` right after the company name, in the address part's style (never bold).
   - Repairs page fields Google Docs emptied; leaves working ones alone.
   - Keeps the "restart at 1" only on the first section (a later section restarting made "Page 1 of 5" on a
     4-page PDF).
   - Gives unstyled list levels the font, size and colour of their item text.
   - Stops with a plain error if a footer has a different shape. Nothing is guessed. Running it twice
     changes nothing.
3. Test (job D), then go live (job E).

### B. Review a client's revised template

The client often sends a clean copy plus a tracked-changes copy. They rarely differ only where the tracked
changes are.

1. `python -I <skills>/doc-templates/scripts/tracked_changes.py MARKUP.docx` — every tracked change, per
   paragraph, as `[-deleted-]` and `{+inserted+}`.
2. `python -I <skills>/doc-templates/scripts/insert_context.py MARKUP.docx` — where each inserted paragraph
   sits (two paragraphs before, one after, list numbering) and how many `{{ }}` template tags the file has.
3. `python -I <skills>/doc-templates/scripts/text_diff.py LIVE.docx CLEAN.docx` — every paragraph that differs
   between the live template and the client's clean copy, body and footers. This catches **untracked**
   changes: text that is not live yet, headings, spelling, a different footer, tags replaced by placeholders
   or the other way round.
4. Tell the BA, in a short table: what the tracked changes do (plain words), and every untracked difference.
   Never put the client's clean copy live as-is. Apply only what the BA approves, to the live template, in
   Word (or by script), then run job A again on the result.

### C. Store client drafts on Drive

Make a subfolder of `folder` named for the change and month, e.g. `Payment order revision 2026-11 (Client)`.
Upload as-is (no conversion), leave out `__MACOSX` and other junk, and check each size matches. The service
never reads subfolders, so nothing goes live.

### D. Test a change on dev

1. In Drive, copy the template in `folder` with a new name. Upload `OUT.docx` onto the copy as a new version.
2. In `test_api` Swagger, render the copy on a test record (Acme Lending: `POST /contracts/generate` with a dev
   test loan's `applicationguid` and `template` = the copy's name without `.docx`).
3. Open the PDF. Check: the counter on every page with the right total, the footer font and colour unchanged,
   list markers the right size, and the new text present. Multi-page templates need a record that makes
   several pages.
4. If a template cannot be rendered on dev (no route, needs a role you do not have), say so in the log —
   "not rendered on dev" — rather than marking it checked.

### E. Go live

1. Get the BA's yes for the file, before the working day.
2. Note the current live version's date and time (Manage versions) — that is the rollback point.
3. Upload `OUT.docx` as a new version of the live file.
4. After the cache time, render once on dev from the real template name to confirm.
5. Add a row to `log`: template, live since (date, time, time zone), how it was checked, the version to restore.

### F. Roll back

Drive → the template → File information → Manage versions → restore (or download and re-upload) the version
named in `log`, or delete the bad version. Live within the cache time. Update `log`.

## Keep the log current

`log` holds the rollout table and anything proven along the way (which folder dev reads, cache time, a
template's quirks). Update it in the same turn as any live change. It is the only record of what is live.
