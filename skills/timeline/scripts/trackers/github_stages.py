"""Helpers for the github-bmad tracker: stage dates from GitHub — the BA specs, the BMAD stories and the app's
branches (Vadim, 5 Nov 2026). Moved here from NWE's docs/BA/timeline/github_stages.py on 6 Nov.

No Jira. A feature moves through the stages like this:

  Spec          the BA spec file exists (docs/BA/specs/<product>/<PREFIX>FR-<n>-….md or <PREFIX>TKT-<n>-….md)
  Ready         the spec's `status:` becomes `ready` (the day, from the spec file's git history)
  In dev        the first of the feature's stories goes in-progress (or review, or done)
  In QA         every story of the feature is done, and its code is on `dev` (the test environment), not on `main`
  Done          the code is on `main` (production): the day of the first production merge that took it

Which stories belong to a feature: each phase's `epics.md` has an "FR Coverage Map" (feature → epic); every story
of a mapped epic counts for that feature, so features that share an epic start together (Vadim: accepted).
Phases without a map: a story's own `**FR:**` line, else the FRs named in the phase line of sprint-status.yaml.

Where a story's code is: the app commit in its sprint-status comment ("# app 69e5058, accepted …") when it has
one; otherwise the tip of `dev` on the day the story was accepted (worked out, not read; shown like any other date).

Stories are read from the docs repo's `origin/main` (the BA branch is behind); everything is read only
(`git fetch` and reads; nothing is written to either repo).
"""
import re, subprocess

import yaml
from collections import defaultdict

IA = "_bmad-output/implementation-artifacts"
ORDER = ["backlog", "ready-for-dev", "in-progress", "review", "done"]


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8")


def norm_key(s):
    """'FR-127' / 'FR127' / 'NWE-FR-127' -> 'FR-127'; 'TKT-8' / 'TKT-08' -> 'TKT-08'."""
    m = re.search(r"(FR|TKT)-?(\d+)", s or "", re.I)
    if not m:
        return None
    return "TKT-%02d" % int(m.group(2)) if m.group(1).upper() == "TKT" else "FR-%d" % int(m.group(2))


def fid_of(key):
    """'FR-127' -> 'fr127', 'TKT-08' -> 'tkt08' (the dashboard's feature ids)."""
    return key.replace("-", "").lower()


def specs_info(docs_repo, spec_dir, prefix="NWE-"):
    """{key: {title, status, opened, specDay, readyDay, file}} for every BA spec; dates from the file's git history."""
    out = {}
    for p in sorted(spec_dir.rglob(prefix + "*.md")):
        key = norm_key(p.stem)
        if not key:
            continue
        text = p.read_text(encoding="utf-8")
        head = text.split("\n---", 1)[0] if text.startswith("---") else text[:2000]   # the front matter
        item = item_fields(text)
        field = lambda n: (re.search(r"^%s:\s*(.*?)\s*(?:#.*)?$" % n, head, re.M) or [None, ""])[1].strip().strip("'\"")
        rel = p.relative_to(docs_repo).as_posix()
        log = _git(docs_repo, "log", "--follow", "--reverse", "-p", "--format=@@%ad", "--date=short", "--", rel).stdout
        day, first, ready = None, None, None
        for line in log.splitlines():
            if line.startswith("@@") and not line.startswith("@@ "):
                day = line[2:].strip()
                first = first or day
            elif line.startswith("+status:") and ready is None and re.match(r"\+status:\s*ready\b", line):
                ready = day
        status = field("status").split()[0] if field("status") else ""
        if status == "ready" and not ready:
            ready = first
        covers = [norm_key(k) for k in re.findall(r"(?:FR|TKT)-?\d+", field("covers"))]
        out[key] = {"title": item.pop("_title", None) or field("title"), "status": status, "opened": field("opened") or first, "covers": covers,
                    "specDay": min(x for x in (field("opened"), first) if x) if (field("opened") or first) else None,
                    "readyDay": ready, "file": rel, **item}
    return out


def item_fields(text):
    """The item fields of a spec (the one item model, 11 Nov 2026): type, baseline, parent, refs, tags, figma,
    commits, story, done, resolution from the front matter, and the bullets of its `## Summary` section."""
    fm = {}
    if text.startswith("---"):
        try:
            raw = text[3:].split("\n---", 1)[0]
            # a bare "-" (e.g. `needed_by: -`) is the template's "none", not a list: read it as text
            raw = re.sub(r"^([A-Za-z_]\w*):[ \t]+-[ \t]*(#.*)?$", r"\1: '-'", raw, flags=re.M)
            fm = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            fm = {}
    out = {k: fm.get(k) for k in ("type", "baseline", "parent", "refs", "tags", "figma", "figma_where", "commits",
                                   "story", "stages", "done", "resolution") if fm.get(k) not in (None, "", [], "-")}
    for st in out.get("stages") or []:
        if isinstance(st, dict) and st.get("from") and not isinstance(st["from"], str):
            st["from"] = st["from"].isoformat()
    if out.get("parent"):
        out["parent"] = norm_key(str(out["parent"])) or str(out["parent"])
    if out.get("done") and not isinstance(out["done"], str):
        out["done"] = out["done"].isoformat()
    for r in out.get("refs") or []:
        if isinstance(r, dict) and r.get("date") and not isinstance(r["date"], str):
            r["date"] = r["date"].isoformat()
    # the Summary is the list right under its heading: it ends at the first line that is not a bullet
    m = re.search(r"^## Summary[ \t]*\n", text, re.M)
    if m:
        bullets = []
        for l in text[m.end():].splitlines():
            if re.match(r"\s*[-*]\s+", l):
                bullets.append(re.sub(r"^\s*[-*]\s+", "", l).strip())
            elif l.strip() or bullets:
                break
        if bullets:
            out["summary"] = bullets
    if isinstance(fm.get("title"), str):
        out["_title"] = fm["title"]
    return out


_CACHE = {}


def _phase_stories(docs_repo, ref):
    """{phase: {"cov": {key: {epic}}, "header": [keys], "stories": {story: {...}}}} read from `ref`."""
    if (str(docs_repo), ref) in _CACHE:
        return _CACHE[(str(docs_repo), ref)]
    _CACHE[(str(docs_repo), ref)] = out = _read_phases(docs_repo, ref)
    return out


def story_titles(docs_repo, ref, phase):
    """{story key: (number, title)} from each story file's "# Story 2.1: …" line."""
    out = {}
    base = "%s/phase-%s/" % (IA, phase)
    for l in _git(docs_repo, "grep", "-m1", "-E", r"^# Story", ref, "--", base).stdout.splitlines():
        parts = l.split(":", 2)
        if len(parts) < 3:
            continue
        sk = parts[1].rsplit("/", 1)[-1][:-3]
        m = re.match(r"^# Story ([\d.]+[a-z]?):\s*(.*)$", parts[2].strip())
        if m:
            out[sk] = (m.group(1), m.group(2).strip())
    return out


def unmapped_stories(docs_repo, ref, phase, used):
    """The stories of one phase that count for no feature: [(story key, story)]."""
    d = _phase_stories(docs_repo, ref).get("phase-" + phase) or {}
    return [(sk, s) for sk, s in d.get("stories", {}).items() if (phase, sk) not in used]


def _read_phases(docs_repo, ref):
    phases =[l.strip().rstrip("/").split("/")[-1] for l in _git(docs_repo, "ls-tree", "-d", "--name-only", ref, IA + "/").stdout.splitlines()]
    out = {}
    for ph in phases:
        base = "%s/%s" % (IA, ph)
        epics = _git(docs_repo, "show", "%s:%s/epics.md" % (ref, base)).stdout
        cov = defaultdict(set)
        sec = re.search(r"#+ *FR Coverage Map(.*?)(?:\n#+ |\Z)", epics, re.S)
        for row in (sec.group(1).splitlines() if sec else []):
            if not row.startswith("|"):
                continue
            cells = [c.strip() for c in row.strip("|").split("|")]
            eps = set()
            for c in cells[1:4]:
                eps |= set(re.findall(r"Epic\s*(\d+)", c))
            for k in re.findall(r"\b(?:FR|TKT)-?\d+", cells[0]):
                cov[norm_key(k)] |= eps
        status_path = "%s/sprint-status.yaml" % base
        cur = _git(docs_repo, "show", "%s:%s" % (ref, status_path)).stdout
        # the phase line names the phase's features, e.g. "# Phase 2.3 — Partners full experience (FR-75 + FR-76)."
        hm = re.search(r"^#\s*Phase [\d.]+.*$", cur, re.M)
        header = sorted({norm_key(k) for k in re.findall(r"\b(?:FR|TKT)-?\d+", hm.group(0))}) if hm else []
        stories = {}
        for m in re.finditer(r"^\s+((\d+)-(\d+[a-z]?)-[\w-]+):\s*\"?([\w-]+)\"?(.*)$", cur, re.M):
            sha = re.search(r"\bapp\s+([0-9a-f]{7,40})\b", m.group(5))
            stories[m.group(1)] = {"epic": m.group(2), "status": m.group(4), "sha": sha.group(1) if sha else None, "first": {}}
        # the day each story first reached each status, from the file's history
        # --follow: the MVP's file lived elsewhere before 17 Aug, and its history (from 11 Jun) is there
        # (git cannot combine --follow with --reverse, so the commits are put oldest-first here)
        log = _git(docs_repo, "log", ref, "--follow", "-p", "--format=@@%ad", "--date=short", "--", status_path).stdout
        blocks = []
        for line in log.splitlines():
            if line.startswith("@@") and not line.startswith("@@ "):
                blocks.append((line[2:].strip(), []))
            elif blocks:
                blocks[-1][1].append(line)
        for day, lines in reversed(blocks):
            for line in lines:
                m = re.match(r"^\+\s+((\d+)-(\d+[a-z]?)-[\w-]+):\s*\"?([\w-]+)\"?", line)
                if m and m.group(1) in stories:
                    f = stories[m.group(1)]["first"]
                    if m.group(4) not in f or day < f[m.group(4)]:
                        f[m.group(4)] = day
        # stories with their own FR line (phases without a coverage map)
        own = defaultdict(set)
        if not cov:
            for l in _git(docs_repo, "grep", "-E", r"^\*\*FRs?:?\*\*", ref, "--", base + "/").stdout.splitlines():
                if l.count(":") < 2:
                    continue
                _, path, text = l.split(":", 2)          # "origin/main:<path>:<line>"
                sk = path.rsplit("/", 1)[-1][:-3]
                for k in re.findall(r"\b(?:FR|TKT)-?\d+", text):
                    own[sk].add(norm_key(k))
        out[ph] = {"cov": cov, "header": header, "stories": stories, "own": own}
    return out


def feature_stories(docs_repo, ref):
    """{key: [(phase, story key, story)]} — the stories that count for each feature."""
    feats = defaultdict(list)
    for ph, d in _phase_stories(docs_repo, ref).items():
        by_epic = defaultdict(set)
        for k, eps in d["cov"].items():
            for e in eps:
                by_epic[e].add(k)
        mapped = set(d["cov"])
        rest = [k for k in d["header"] if k not in mapped]
        for sk, s in d["stories"].items():
            keys = by_epic.get(s["epic"]) or d["own"].get(sk) or (set(rest) if rest else set())
            for k in keys:
                feats[k].append((ph.replace("phase-", ""), sk, s))
    return feats


class AppRepo:
    """Where a commit is: on dev, on main, and the day production took it. Read only."""

    def __init__(self, repo):
        self.repo = repo
        _git(repo, "fetch", "-q", "origin")
        self.deploys = [l.split(" ", 1) for l in _git(repo, "log", "origin/main", "--first-parent", "--merges", "--reverse",
                                                       "--format=%H %ad", "--date=short").stdout.splitlines() if l]
        self.dev_line = [l.split(" ", 1) for l in _git(repo, "log", "origin/dev", "--first-parent", "--reverse",
                                                        "--format=%H %ad", "--date=short").stdout.splitlines() if l]
        self._anc = {}

    def anc(self, c, ref):
        k = (c, ref)
        if k not in self._anc:
            self._anc[k] = _git(self.repo, "merge-base", "--is-ancestor", c, ref).returncode == 0
        return self._anc[k]

    def exists(self, c):
        return _git(self.repo, "cat-file", "-e", c + "^{commit}").returncode == 0

    def dev_tip_on(self, day):
        """The last commit on dev's main line made on or before `day`."""
        tip = None
        for h, d in self.dev_line:
            if d > day:
                break
            tip = h
        return tip

    def bug_commits(self):
        """{"BUG-028": [(sha, day), …]} — app commits on dev that name a bug, oldest first."""
        if not hasattr(self, "_bugs"):
            self._bugs = {}
            log = _git(self.repo, "log", "origin/dev", "--reverse", "--format=@@%H %ad", "--date=short", "--no-merges").stdout
            body = _git(self.repo, "log", "origin/dev", "--reverse", "--format=@@%H%n%B", "--no-merges").stdout
            days = dict(l[2:].split(" ", 1) for l in log.splitlines() if l.startswith("@@"))
            cur = None
            for l in body.splitlines():
                if l.startswith("@@"):
                    cur = l[2:].strip(); continue
                for b in set(re.findall(r"\bBUG-\d{3}\b", l)):
                    lst = self._bugs.setdefault(b, [])
                    if cur and (cur, days.get(cur, "")) not in lst:
                        lst.append((cur, days.get(cur, "")))
        return self._bugs

    def main_twin(self, c):
        """A commit on main with the same title as `c` — the same fix, copied to main under a new id (a
        cherry-pick or a rebase). None when there is none. (Vadim, 11 Nov 2026: fixes copied to main read as not
        on production.)"""
        if not hasattr(self, "_main_by_subject"):
            self._main_by_subject = {}
            for l in _git(self.repo, "log", "origin/main", "--no-merges", "--format=%H %s").stdout.splitlines():
                h, _, s = l.partition(" ")
                self._main_by_subject.setdefault(s.strip(), h)
        subject = _git(self.repo, "log", "-1", "--format=%s", c).stdout.strip()
        return self._main_by_subject.get(subject) if subject else None

    def prod_day(self, c):
        """The day of the first production merge that took commit `c` (or its copy on main), or None if it is not
        on main."""
        if not self.anc(c, "origin/main"):
            twin = self.main_twin(c)
            if not twin or twin == c:
                return None
            c = twin
        for h, d in self.deploys:
            if self.anc(c, h):
                return d
        return None


def stages_from_stories(items, app):
    """Stage list from a feature's stories: [{stage, from}], the current stage, and facts for the side panel."""
    if not items:
        return None
    started = []
    for _, _, s in items:
        days = [s["first"].get(x) for x in ("in-progress", "review", "done") if s["first"].get(x)]
        if days:
            started.append(min(days))
    n = len(items)
    done = [s for _, _, s in items if s["status"] == "done"]
    facts = {"stories": n, "storiesDone": len(done), "phases": sorted({p for p, _, _ in items})}
    if not started:
        return {"stages": [], "stage": "ready", **facts}
    st = [{"stage": "dev", "from": min(started)}]
    if len(done) < n:
        return {"stages": st, "stage": "dev", **facts}
    qa_day = max(s["first"].get("done") or min(started) for s in done)
    refs, inferred, lost = [], False, 0
    for s in done:
        c = s["sha"]
        if c and not app.exists(c):
            c = None
        if not c:
            c, inferred = app.dev_tip_on(s["first"].get("done") or qa_day), True
        if c:
            if not (app.anc(c, "origin/dev") or app.anc(c, "origin/main")):
                lost += 1           # rolled back: its code is no longer on dev
            refs.append(c)
    facts["inferred"] = inferred
    if lost:
        facts["lost"] = lost
        return {"stages": st, "stage": "dev", **facts}
    st.append({"stage": "qa", "from": qa_day})
    prod = [app.prod_day(c) for c in refs] if refs else [None]
    if all(prod):
        day = max(max(prod), qa_day)
        st.append({"stage": "done", "from": day})
        return {"stages": st, "stage": "done", "doneDate": day, **facts}
    return {"stages": st, "stage": "qa", **facts}


def qa_bugs(docs_repo, ref, app):
    """The QA bugs (docs/issues/INDEX.md and the bug files under _bmad-output/qa/runs/, on `ref`), with stages.

    Reported → Ready ("waiting for a fix"); a fix on dev → In QA; the fix on main → Done (its production day).
    The fix commit is read from the bug file ("Fixed on app `dev` @ `75739e4`"); with none, the file's status line
    (FIXED / FIX READY) and its last change date are used. Withdrawn bugs are left out.
    """
    index = _git(docs_repo, "show", "%s:docs/issues/INDEX.md" % ref).stdout
    files = {}
    for p in _git(docs_repo, "ls-tree", "-r", "--name-only", ref, "_bmad-output/qa/runs/").stdout.splitlines():
        m = re.search(r"/bugs/(BUG-\d+)[^/]*\.md$", p)
        if m:
            files.setdefault(m.group(1), p)
    out = {}
    for row in index.splitlines():
        if not row.startswith("| BUG-"):
            continue
        c = [x.strip() for x in row.strip("|").split("|")]
        if len(c) < 5:
            continue
        bid, sev, cat, title, found = c[:5]
        path = files.get(bid)
        head = _git(docs_repo, "show", "%s:%s" % (ref, path)).stdout[:3000] if path else ""
        first = head.splitlines()[0] if head else ""
        status = (re.match(r"^# \[BUG-\d+\]\s*\[([^\]]*)\]", first) or [None, ""])[1].upper()
        if "WITHDRAWN" in status or "withdrawn" in cat.lower():
            continue
        last = _git(docs_repo, "log", "-1", "--format=%ad", "--date=short", ref, "--", path).stdout.strip() if path else None
        sha = re.search(r"[Ff]ix(?:ed)?[^\n`]*?app\s*`?dev`?\s*@\s*`([0-9a-f]{7,40})`", head)
        sha = sha.group(1) if sha and app and app.exists(sha.group(1)) else None
        if not sha and not status.startswith(("FIX", "✅")) and app:
            # no status in the file: an app commit that names the bug, made after it was found, is its fix
            sha = next((h for h, day in app.bug_commits().get(bid, []) if day >= found), None)
        st = [{"stage": "ready", "from": found}]
        stage = "ready"
        if sha:
            fix_day = _git(app.repo, "log", "-1", "--format=%ad", "--date=short", sha).stdout.strip() or found
            st.append({"stage": "qa", "from": max(fix_day, found)}); stage = "qa"
            prod = app.prod_day(sha)
            if prod:
                st.append({"stage": "done", "from": max(prod, fix_day)}); stage = "done"
        elif "FIXED" in status and "READY" not in status:
            st.append({"stage": "done", "from": last or found}); stage = "done"
        elif "FIX READY" in status:
            st.append({"stage": "qa", "from": last or found}); stage = "qa"
        out[bid] = {"severity": sev, "category": cat, "title": title, "found": found, "stage": stage, "stages": st,
                    "fixSha": sha, "file": path}
    return out
