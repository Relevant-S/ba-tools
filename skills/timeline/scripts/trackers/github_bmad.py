"""Tracker plug-in: GitHub + BMAD (no Jira). Moved here from NWE's docs/BA/timeline/build.py on 6 Nov 2026.

  Spec    the BA spec file exists                   Ready   its `status:` becomes ready
  In dev  the first story of the feature starts     In QA   all its stories done, their code on `dev`
  Done    the code is on `main` (production)

Work done without stories: `code_commits:` in the data file (all on main → Done, any only on dev → In dev).
Rows not on the dashboard: specs (`github.spec_areas` gives the area) and the MVP's stories (`github.mvp`).
Changes (`github.changes`) and QA bugs (`bug-parents.yaml` next to the data file) go under their features.

The data file's `github:` block:
  docs_ref        where the stories live (default origin/main)
  repo_url        e.g. https://github.com/northwind/docs — for links to stories and specs
  spec_branch     the branch the BA specs are on (default docs)
  spec_prefix     the spec file prefix (default "<PRODUCT>-", e.g. "NWE-")
  spec_areas, titles, skip, aliases, mvp {phase, epic_areas, story_areas}, changes, doc_subject, change_prefix
and top level: code_repo (the app checkout, from the docs repo root), code_commits.
Everything is read only: `git fetch` and reads; nothing is written to either repo.
"""
import datetime as dt, re, sys
from pathlib import Path

import yaml

from . import Base
from . import github_stages as gs


def iso(d):
    return d if isinstance(d, str) else d.isoformat()


class Tracker(Base):
    name = "github-bmad"
    title = "GitHub"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.ghc = ctx.tl.get("github") or {}
        self.ref = self.ghc.get("docs_ref") or "origin/main"
        url = (self.ghc.get("repo_url") or "").rstrip("/")
        self.work_link = url + "/blob/main/" if url else ""
        self.spec_url = url + "/blob/%s/" % (self.ghc.get("spec_branch") or "docs") if url else ""
        self.prefix = self.ghc.get("spec_prefix") or (str(ctx.product["clarifications"]).upper() + "-")
        self.alias = {v: k for k, v in (self.ghc.get("aliases") or {}).items()}     # dashboard id -> spec key
        self.app_repo = (ctx.repo / ctx.tl["code_repo"]).resolve() if ctx.tl.get("code_repo") else None

    # ---------- reading
    def prepare(self, dashboard_features):
        docs = self.ctx.repo
        self.specs = gs.specs_info(docs, self.ctx.ba / "specs" / str(self.ctx.product["clarifications"]), self.prefix)
        self.stories = gs.feature_stories(docs, self.ref) if self.app_repo else {}
        self.app = gs.AppRepo(self.app_repo) if self.app_repo else None
        # the one item model (11 Nov 2026): every spec is an item; dashboard ids reach theirs through `aliases`
        self.items = {gs.fid_of(k): dict(s, key=k) for k, s in self.specs.items()}
        for k, dash_id in (self.ghc.get("aliases") or {}).items():
            if gs.norm_key(k) in self.specs:
                self.items[str(dash_id)] = self.items[gs.fid_of(gs.norm_key(k))]
        commits = dict(self.ctx.tl.get("code_commits") or {})
        for fid, it in self.items.items():
            if it.get("commits"):
                commits[fid] = [str(c) for c in it["commits"]]
        self.codest = self._code_stages(commits) if self.app_repo else {}
        self.baseline_by_story = {str(s["story"]): k for k, s in self.specs.items() if s.get("baseline") and s.get("story")}
        self.child_rows = []
        self.titles = {}
        print("GitHub: %d specs, %d features with stories" % (len(self.specs), len(self.stories)))

    def _code_stages(self, commits_by_feature):
        """{feature id: {stage, first, done}} from the commits listed in the data file (work without stories)."""
        def git(*a):
            return gs._git(self.app_repo, *a)
        out = {}
        for fid, commits in (commits_by_feature or {}).items():
            days, on_main, deployed = [], True, []
            for c in commits:
                r = git("log", "-1", "--format=%ad", "--date=short", c)
                if r.returncode:
                    print("Commit %s (%s) is not in the app repo" % (c, fid)); continue
                days.append(r.stdout.strip())
                # on main itself, or copied there under a new id (same commit title)
                prod = self.app.prod_day(c)
                if prod or self.app.anc(c, "origin/main"):
                    deployed.append(prod or days[-1])
                else:
                    on_main = False
            if days:
                out[fid] = {"stage": "done" if on_main else "dev", "first": min(days),
                            "done": max(deployed) if on_main and deployed else None}
        return out

    def _title(self, ph, sk):
        if ph not in self.titles:
            self.titles[ph] = gs.story_titles(self.ctx.repo, self.ref, ph)
        return self.titles[ph].get(sk, (None, sk))

    def key_of(self, fid):
        if fid in self.alias:
            return self.alias[fid]
        return gs.norm_key(fid) if re.fullmatch(r"(?:fr|tkt)\d+", fid or "") else None

    def item_of(self, fid):
        """The spec item behind a row id (fr56, tkt08, a dashboard alias), or None."""
        return self.items.get(fid)

    def apply_item_status(self, row, item):
        """Stage dates written in the item itself win: `stages:` in full, or `done:` as the closing date."""
        if not item:
            return
        if item.get("stages"):
            st = [{"stage": x["stage"], "from": str(x["from"])} for x in item["stages"]]
            row.update(stages=st, stage=st[-1]["stage"], basis="recorded")
            row["since"] = row.get("since") or st[0]["from"]
            if st[-1]["stage"] in ("done", "live"):
                row["doneDate"] = st[-1]["from"]
        elif item.get("done"):
            day = str(item["done"])
            st = [x for x in row.get("stages") or [] if x["from"] < day and x["stage"] not in ("done", "live")]
            st.append({"stage": "done", "from": day})
            row.update(stages=st, stage="done", doneDate=day, basis="recorded")

    def pin_for_ref(self, ref):
        """A pin for an item's outside reference ({source, key, kind, who, date, asked}); returns its id or None."""
        if not isinstance(ref, dict) or not ref.get("date"):
            return None
        kind = ref.get("kind") or "doc"
        subject = None
        if kind == "email" and ref.get("asked"):
            subject = str(ref["asked"]).split(" — ")[0]
        if kind == "doc" and self.ghc.get("doc_subject"):
            day = dt.date.fromisoformat(iso(ref["date"]))
            subject = "%s — rows added %s" % (self.ghc["doc_subject"], day.strftime("%#d %b" if sys.platform == "win32" else "%-d %b"))
        return self.ctx.add_pin(iso(ref["date"]), kind, ref.get("who"), subject)

    def stories_for(self, key):
        """A feature's stories, with those of the features its spec owns (NWE-FR-115 covers FR-116).
        A spec owns a group only when it lists itself too; a spec that names only others is a change to them."""
        cov = (self.specs.get(key) or {}).get("covers", [])
        keys = [key] + ([c for c in cov if c != key and c not in self.specs] if key in cov else [])
        seen, items = set(), []
        for k in keys:
            for it in self.stories.get(k, []):
                if (it[0], it[1]) not in seen:
                    seen.add((it[0], it[1])); items.append(it)
        return items

    def work_of(self, items):
        out = []
        for ph, sk, s in items:
            num, title = self._title(ph, sk)
            out.append({"id": "Story %s" % num if num else sk, "title": title if num else "", "status": s["status"],
                        "url": self.work_link + "%s/phase-%s/%s.md" % (gs.IA, ph, sk) if self.work_link else None,
                        "done": s["first"].get("done") if s["status"] == "done" else None})
        return out

    def stages_of(self, key, since):
        """{stages, stage, doneDate, phases, items} for a feature from its spec and its stories, or None."""
        spec, items = self.specs.get(key), self.stories_for(key)
        if not spec and not items:
            return None
        res = gs.stages_from_stories(items, self.app) if items and self.app else None
        out = []

        def add(stage, day):
            if not day:
                return
            while out and out[-1]["from"] > day:      # keep the dates in order: a later stage wins
                out.pop()
            out.append({"stage": stage, "from": day})
        spec_day = spec and spec.get("specDay")
        if since and (not spec_day or since < spec_day):
            add("concept", since)
        add("spec", spec_day)
        if spec and spec["status"] == "ready" or (res and res["stages"]):
            add("ready", spec and spec.get("readyDay"))
        for s in (res or {}).get("stages", []):
            add(s["stage"], s["from"])
        if res and res["stages"]:
            stage = res["stage"]
        elif spec and spec["status"] in ("ready", "resolved"):
            stage = "ready" if spec["status"] == "ready" else "done"
        elif res:
            stage = res["stage"]                      # stories planned, none started
        else:
            stage = "spec"
        return {"stages": out, "stage": stage, "doneDate": (res or {}).get("doneDate"),
                "phases": (res or {}).get("phases") or [], "items": items}

    # ---------- hooks
    def feature_work(self, f):
        key = self.key_of(f["id"])
        return self.work_of(self.stories_for(key)) if key else []

    def feature(self, f, out, first):
        fid = f["id"]
        key = self.key_of(fid)
        ghs = self.stages_of(key, out["since"]) if key else None
        if ghs:
            out.update(stages=ghs["stages"], stage=ghs["stage"], basis="tracker", work=self.work_of(ghs["items"]))
            if ghs["doneDate"]:
                out["doneDate"] = ghs["doneDate"]
            if ghs["phases"]:
                out["tags"] = ghs["phases"]
        cs = self.codest.get(fid)
        if cs and not (ghs and ghs["items"]):
            # code on production = Done; code only on dev = In dev (Vadim, 5 Nov) — only for work without stories
            st = [{"stage": "spec", "from": out["since"]}] if out["since"] and out["since"] < cs["first"] else []
            st.append({"stage": "dev", "from": cs["first"]})
            if cs["stage"] == "done":
                st.append({"stage": "done", "from": cs["done"] or cs["first"]})
                out["doneDate"] = cs["done"] or cs["first"]
            out.update(stages=st, stage=cs["stage"], basis="code")
        self.apply_item_status(out, self.item_of(fid))

    def tags_of_work(self, work):
        return []

    def extra_rows(self, on_dashboard):
        rows = {}
        on_dash = {self.key_of(fid) for fid in on_dashboard} - {None}
        # a change, improvement or bug changes what it covers; it never hides it. Before the item model, the same was
        # read from a spec-name prefix (`github.change_prefix`, e.g. "TKT-").
        chg = self.ghc.get("change_prefix")
        is_change = lambda k: ((self.specs.get(k) or {}).get("type") not in (None, "feature")) or bool(chg and k.startswith(chg))
        covered = {c for k, s in self.specs.items() for c in s.get("covers", [])
                   if c != k and c not in self.specs and not is_change(k)}
        skip = set(self.ghc.get("skip") or [])
        # specs (and features with stories) that are not on the dashboard
        for key in sorted(set(self.specs) | set(self.stories), key=lambda k: (k[:2], int(k.split("-")[1]))):
            if key in on_dash or key in skip or key in covered:
                continue
            spec = self.specs.get(key) or {}
            if spec.get("baseline"):
                continue                              # a baseline item is drawn from its MVP story, below
            area = (self.ghc.get("spec_areas") or {}).get(key)
            if spec.get("parent"):
                area = "__child__"                    # sits under its parent; its area is its top parent's
            if not area:
                print("No area for %s in github.spec_areas: left out" % key); continue
            ghs = self.stages_of(key, None)
            if not ghs or not (ghs["stages"] or spec.get("stages") or spec.get("done")):
                continue
            if not ghs["stages"]:
                ghs["stages"] = [{"stage": "spec", "from": spec.get("specDay")}]
            label = (self.ghc.get("titles") or {}).get(key) or spec.get("title") or key
            rows.setdefault(area, []).append({
                "id": gs.fid_of(key), "label": label + (" (parked)" if spec.get("status") == "parked" else ""),
                "stage": ghs["stage"], "doneDate": ghs["doneDate"], "since": ghs["stages"][0]["from"],
                "desc": "", "clar": None, "clarLabel": None, "guess": False, "origin": "spec", "basis": "tracker",
                "stages": ghs["stages"], "work": self.work_of(ghs["items"]), "tags": ghs["phases"], "who": [],
                **({"kind": "change"} if is_change(key) else {})})
            # commits listed in the data file count for a spec row too, when it has no stories (Vadim, 11 Nov 2026)
            cs = self.codest.get(gs.fid_of(key))
            if cs and not ghs["items"]:
                row = rows[area][-1]
                st = [x for x in row["stages"] if x["from"] < cs["first"] and x["stage"] in ("concept", "spec", "ready")]
                st.append({"stage": "dev", "from": cs["first"]})
                if cs["stage"] == "done":
                    st.append({"stage": "done", "from": cs["done"] or cs["first"]})
                    row["doneDate"] = cs["done"] or cs["first"]
                row.update(stages=st, stage=cs["stage"], basis="code")
            self.apply_item_status(rows[area][-1], spec)
            if area == "__child__":
                self.child_rows.append(rows.pop(area)[-1])
        # the MVP: one row per story (no BA specs, and its stories name no feature)
        mvp = self.ghc.get("mvp") or {}
        if mvp and self.app:
            ph = str(mvp["phase"])
            used = {(p, sk) for items in self.stories.values() for p, sk, _ in items}
            n = 0
            for sk, s in gs.unmapped_stories(self.ctx.repo, self.ref, ph, used):
                num, title = self._title(ph, sk)
                if not num or "retrospective" in sk:
                    continue
                area = (mvp.get("story_areas") or {}).get(num) or (mvp.get("epic_areas") or {}).get(int(num.split(".")[0]))
                res = gs.stages_from_stories([(ph, sk, s)], self.app)
                if not area or not res or not res["stages"]:
                    continue
                bkey = self.baseline_by_story.get(sk)
                rows.setdefault(area, []).append({
                    "id": gs.fid_of(bkey) if bkey else "mvp-" + sk,
                    "label": (self.specs[bkey].get("title") or title) if bkey else title, "stage": res["stage"], "doneDate": res.get("doneDate"),
                    "since": res["stages"][0]["from"], "desc": "", "clar": None, "clarLabel": None, "guess": False,
                    "origin": "old-work", "basis": "tracker", "originNote": "Built in the MVP, before the BA specs.",
                    "stages": res["stages"], "work": self.work_of([(ph, sk, s)]), "tags": [ph], "who": []})
                n += 1
            print("MVP stories as rows: %d" % n)
        return rows

    def add_requests(self, rows_by_id):
        n_chg = n_bug = 0
        doc_subject = self.ghc.get("doc_subject")
        for fid, c in (self.ghc.get("changes") or {}).items():
            f, parent = rows_by_id.get(fid), rows_by_id.get(c.get("parent"))
            if f and not c.get("parent"):
                # no parent (big features, 10 Nov 2026): the change is a row of its own, shown once, marked a change
                src = c.get("source") or {}
                if src.get("date"):
                    kind = src.get("kind") or "email"
                    subject = src["what"].split(" — ")[0] if kind == "email" and src.get("what") else None
                    if kind == "doc" and doc_subject:
                        subject = "%s — rows added %s" % (doc_subject, dt.date.fromisoformat(iso(src["date"])).strftime("%#d %b" if sys.platform == "win32" else "%-d %b"))
                    f["askedIn"] = f.get("askedIn") or self.ctx.add_pin(iso(src["date"]), kind, src.get("who"), subject)
                f["askedBy"] = f.get("askedBy") or src.get("who")
                if src.get("what"):
                    f["asked"] = src["what"]
                f["kind"] = "change"
                n_chg += 1
                continue
            if not f or not parent or not f.get("stages"):
                print("Change %s: no row for it or its parent %s" % (fid, c.get("parent"))); continue
            src, pin = c.get("source") or {}, None
            if src.get("date"):
                day, kind = iso(src["date"]), src.get("kind") or "email"
                subject = None
                if kind == "email" and src.get("what"):
                    subject = src["what"].split(" — ")[0]
                if kind == "doc" and doc_subject:
                    subject = "%s — rows added %s" % (doc_subject, dt.date.fromisoformat(day).strftime("%#d %b" if sys.platform == "win32" else "%-d %b"))
                pin = self.ctx.add_pin(day, kind, src.get("who"), subject)
            parent.setdefault("requests", []).append({
                "id": "chg-" + fid, "kind": "change", "title": f["label"], "askedIn": pin,
                "askedBy": src.get("who") or (f.get("who") or [None])[0], "asked": src.get("what"),
                "stages": f["stages"], "work": [], "merged": None, "splitOff": None,
                "self": fid, "guess": bool(c.get("guess")), "about": f.get("about") or None,
                **({"tags": f["tags"]} if f.get("tags") and f["tags"] != parent.get("tags") else {})})
            f["changes"] = c["parent"]
            n_chg += 1
        bpath = self.ctx.here / "bug-parents.yaml"
        parents = (yaml.safe_load(bpath.read_text(encoding="utf-8")) or {}) if bpath.exists() else {}
        # `github.qa_bugs: false` leaves our own QA test-run bugs off the page: the client sees only the bugs it
        # reported itself (Vadim, 11 Nov 2026)
        show_qa = self.ghc.get("qa_bugs", True) is not False and self.ctx.tl.get("items") != "specs"
        bugs = gs.qa_bugs(self.ctx.repo, self.ref, self.app) if self.app and show_qa else {}
        for bid, b in bugs.items():
            m = parents.get(bid) or {}
            parent = rows_by_id.get(m.get("parent"))
            if m.get("skip") or not parent:
                continue
            parent.setdefault("requests", []).append({
                "id": bid.lower(), "kind": "bug", "title": m.get("title") or b["title"], "askedIn": None, "askedBy": None,
                "stages": b["stages"], "work": [], "merged": None, "splitOff": None, "guess": not m.get("sure", True),
                "note": "QA bug %s · %s · found %s%s" % (bid, b["severity"], b["found"],
                        " · fixed in app commit %s" % b["fixSha"][:8] if b.get("fixSha") else
                        (" · no fix recorded yet" if b["stage"] == "ready" else ""))})
            n_bug += 1
        print("Changes under their features: %d · QA bugs: %d of %d" % (n_chg, n_bug, len(bugs)))

    def releases(self, default):
        if default or not self.app:
            return default
        # no releases on the dashboard: the app's release branches (release/2026-08-31 …) are the production releases
        names = gs._git(self.app_repo, "branch", "-r", "--list", "origin/release/*", "--format=%(refname:short)").stdout.split()
        return sorted([{"name": "Release " + n.split("/")[-1], "date": n.split("/")[-1]} for n in names
                       if re.fullmatch(r"\d{4}-\d\d-\d\d", n.split("/")[-1])], key=lambda r: r["date"])

    def footer(self):
        mvp = (self.ghc.get("mvp") or {}).get("phase")
        return ("the BA dashboard, the BA specs, the BMAD stories (docs repo, %s) and the app's dev and main branches. "
                "Spec and Ready come from each spec's status; In dev starts with the first story; In QA = every story done "
                "and its code on dev; Done = on main (production). Rows that are not on the dashboard are BA specs%s; "
                "switch off \"Hide done\" to see the finished ones. * = placed here by guess."
                % (self.ref.split("/")[-1], ", or MVP stories (phase %s, built before the BA specs)" % mvp if mvp else ""))
