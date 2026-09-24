# Step 5 — Existing code to reuse (section 14)

Required on every product that already ships. This is its own step because the old workflow banned
file references, and the section is what turns a spec into a build order.

**Where to look:** the repos in the profile's `code.repos` (paths relative to the project root), with
the `area` each covers. If the code this spec touches is in a repo the profile does not list, ask the
BA where it is and suggest adding it to the profile.

**Before looking:**

```bash
git -C <repo> fetch origin
```

Then read the branch the developers merge into — `origin/<code.dev_branch>` — never the local
checkout:

```bash
git -C <repo> grep -n '<term>' origin/<dev_branch> -- <paths>
git -C <repo> show origin/<dev_branch>:<path>
```

Also check `origin/<code.live_branch>` when the question is "what is live today" (a bug fix, a gap in
shipped code). If a feature branch for this work already exists, check it too.

**Write, starting with one line per repo you looked in:**

`Checked at <repo> @ <short sha> (<branch>, <date>)`

Then the four lists from the template: **already built and reused**, **to extend**, **do not touch**,
**nothing found**. Give `path:line` for each. If you looked and found nothing, write
"checked, nothing exists yet" — a reader cannot otherwise tell that from nobody having looked.

**If the code shows the work is smaller than it looked, or already done, stop and tell the BA** before
writing more. That is the most valuable thing this step finds.
