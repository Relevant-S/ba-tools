"""Tracker plug-in: Jira. Moved here from Acme Lending's docs/BA/timeline/build.py on 6 Nov 2026.

Stage dates come from the status history of each feature's Jira tickets (the dashboard links the tickets):
the first day any ticket reached each stage; Done only when every ticket is done. Stories created before the
timeline start (`earlier_work:` in the data file) are rows of their own, placed by component, then by epic
(`earlier_work.epic_areas`), else in `earlier_work.fallback_area` as a guess. Tags are the tickets' releases.

Read only. Uses JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN when set; otherwise, and when Jira cannot be
reached, the caches next to the data file (jira-history.json, jira-earlier-stories.json).

The data file: `product.work_link` (default https://example.atlassian.net/browse/), `jira_project` (default
ACME), `jira: false` to skip the earlier stories, `earlier_work: {epic_areas, fallback_area, issue_types, until}`.
`issue_types` (default [Story]) and `until` (default the start date; `all` = every one) widen the rows for a
project whose work lives mostly in Jira tasks (the Bond Portal).
"""
import base64, datetime as dt, json, os, re, urllib.request

from . import Base


def jira_status_stage(name):
    n = (name or "").lower()
    if any(w in n for w in ("done", "closed", "resolved", "released")):
        return "done"
    if "test" in n or "qa" in n:
        return "qa"
    if any(w in n for w in ("progress", "develop", "review", "coding")):
        return "dev"
    return "ready"


def short_tag(name):
    """'6.4. - Compliance one-screen review, ...' -> '6.4'; 'Release 5.1.1. - ...' -> '5.1.1'; others as they are."""
    m = re.match(r"\s*(?:Release\s+)?(\d+(?:\.\d+)*)", name or "")
    return m.group(1) if m else (name or "").strip()


def stages_from_jira(keys, hist, since=None):
    """First day the feature's tickets reached each stage, in stage order. Done only when every ticket is done."""
    rows = [hist[k] for k in keys if k in hist]
    if not rows:
        return []
    order = ["ready", "dev", "qa", "done"]
    first = {"ready": min(r["created"] for r in rows)}
    for r in rows:
        for day, stg in r["moves"]:
            if stg in order[1:] and (stg not in first or day < first[stg]):
                first[stg] = day
    last_stage = [max(([order.index(s) for _, s in r["moves"]] or [0])) for r in rows]
    if min(last_stage) < 3:
        first.pop("done", None)                       # some ticket is not done yet
    else:
        first["done"] = max(max(d for d, s in r["moves"] if s == "done") for r in rows)
    out, prev = [], ""
    if since and since < first["ready"]:
        out.append({"stage": "concept", "from": since})
        prev = since
    for s in order:
        if s in first and first[s] >= prev:
            out.append({"stage": s, "from": first[s]})
            prev = first[s]
    return out


class Tracker(Base):
    name = "jira"
    title = "Jira"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.work_link = ctx.product.get("work_link") or "https://example.atlassian.net/browse/"
        self.hist_cache = ctx.here / "jira-history.json"
        self.earlier_cache = ctx.here / "jira-earlier-stories.json"
        self.login = [os.environ.get(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")]
        self.hist, self.earlier, self.summary, self.until = {}, [], {}, ctx.start

    # ---------- Jira, read only
    def _post(self, body):
        base, email, token = self.login
        auth = "Basic " + base64.b64encode(("%s:%s" % (email, token)).encode()).decode()
        req = urllib.request.Request(base.rstrip("/") + "/rest/api/3/search/jql", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))

    def _history(self, keys):
        """{key: {"created", "moves": [[date, stage], …], "versions"}} for the given tickets."""
        cache = json.loads(self.hist_cache.read_text(encoding="utf-8")) if self.hist_cache.exists() else {}
        if not all(self.login):
            print("No Jira login in this shell: using the cached ticket history (%d tickets)" % len(cache))
            return cache
        keys = sorted(set(keys))
        for i in range(0, len(keys), 50):
            try:
                res = self._post({"jql": "key in (%s)" % ",".join(keys[i:i + 50]), "fields": ["created", "status", "fixVersions"],
                                  "expand": "changelog", "maxResults": 100})
            except Exception as e:  # keep the cache when Jira cannot be reached
                print("Jira could not be read (%s): using the cached ticket history" % e)
                return cache
            for issue in res.get("issues", []):
                moves = [[h["created"][:10], jira_status_stage(it.get("toString"))]
                         for h in (issue.get("changelog") or {}).get("histories", []) for it in h.get("items", []) if it.get("field") == "status"]
                cache[issue["key"]] = {"created": issue["fields"]["created"][:10], "moves": sorted(moves),
                                       "versions": [v.get("name", "") for v in issue["fields"].get("fixVersions") or []]}
        self.hist_cache.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
        print("Read the history of %d Jira tickets" % len(keys))
        return cache

    def _earlier_stories(self, project, before, types=("Story",)):
        """The Jira stories (or other types) created before a day, or all with before=None (cached in jira-earlier-stories.json)."""
        cache = json.loads(self.earlier_cache.read_text(encoding="utf-8")) if self.earlier_cache.exists() else []
        if not all(self.login):
            print("No Jira login in this shell: earlier stories from the cache only (%d stories)" % len(cache))
            return cache
        out, page = [], None
        while True:
            jql = "project = %s AND issuetype in (%s)%s ORDER BY created" % (
                project, ", ".join('"%s"' % t for t in types), " AND created < %s" % before if before else "")
            body = {"jql": jql,
                    "fields": ["summary", "created", "status", "components", "parent", "resolutiondate"], "maxResults": 100}
            if page:
                body["nextPageToken"] = page
            try:
                res = self._post(body)
            except Exception as e:
                print("Jira could not be read (%s): earlier stories from the cache" % e)
                return cache
            for i in res.get("issues", []):
                f, parent = i["fields"], i["fields"].get("parent") or {}
                out.append({"key": i["key"], "summary": f.get("summary", "").strip(), "created": f["created"][:10],
                            "status": f["status"]["name"], "done": f["status"]["statusCategory"]["key"] == "done",
                            "resolved": (f.get("resolutiondate") or "")[:10] or None,
                            "components": [c["name"] for c in f.get("components") or []],
                            "epic": parent.get("key"), "epicName": (parent.get("fields") or {}).get("summary")})
            page = res.get("nextPageToken")
            if not page or res.get("isLast"):
                break
        self.earlier_cache.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print("Read %d Jira %s%s" % (len(out), "/".join(types), " created before %s" % before if before else ""))
        return out

    def _done_day(self, key):
        days = [d for d, s in (self.hist.get(key) or {}).get("moves", []) if s == "done"]
        return days[-1] if days else None

    # ---------- hooks
    def prepare(self, dashboard_features):
        tl = self.ctx.tl
        keys = [t["key"] for f in dashboard_features for t in (f.get("tickets") or [])]
        for f in dashboard_features:
            for t in f.get("tickets") or []:
                self.summary[t["key"]] = (t.get("summary", ""), t.get("status", ""))
        if tl.get("earlier_work") and tl.get("jira", True) is not False:
            # every ticket the dashboard knows, not only this timeline's: a story linked anywhere is not "earlier"
            on_dashboard = {t["key"] for e in self.ctx.data["epics"] for f in e.get("features", []) for t in (f.get("tickets") or [])}
            ew = tl["earlier_work"]
            until = ew.get("until", self.ctx.start)
            until = None if str(until) == "all" else str(until)
            self.until = until
            self.earlier = [s for s in self._earlier_stories(tl.get("jira_project", "ACME"), until, tuple(ew.get("issue_types") or ["Story"]))
                            if s["key"] not in on_dashboard]
        all_keys = [t["key"] for e in self.ctx.data["epics"] for f in e.get("features", []) for t in (f.get("tickets") or [])]
        self.hist = self._history(all_keys + [s["key"] for s in self.earlier])

    def work_items(self, ids):
        return [{"id": k, "title": self.summary.get(k, ("", ""))[0], "status": self.summary.get(k, ("", ""))[1],
                 "done": self._done_day(k)} for k in ids or []]

    def tags_of_work(self, work):
        out = []
        for w in work:
            for v in (self.hist.get(w["id"]) or {}).get("versions") or []:
                t = short_tag(v)
                if t and t not in out:
                    out.append(t)
        return out

    def feature_work(self, f):
        return [{"id": t["key"], "title": t.get("summary", ""), "status": t.get("status", ""), "done": self._done_day(t["key"])}
                for t in f.get("tickets") or []]

    def feature(self, f, out, first):
        out["work"] = self.feature_work(f)
        js = stages_from_jira([w["id"] for w in out["work"]], self.hist, since=first)
        if not js:
            return
        out["stages"], out["basis"] = js, "tracker"     # the dot and label keep the dashboard's current stage
        note = "From the Jira history of its tickets" + ("; Concept starts when the dashboard first lists it" if js[0]["stage"] == "concept" else "")
        rank = {"concept": 0, "spec": 1, "design": 1, "ready": 2, "dev": 3, "qa": 4, "done": 5, "live": 5}
        if rank.get(out["stage"], 0) < rank[js[-1]["stage"]]:
            # new work on a feature whose earlier tickets are further on (e.g. all done): show the stage it is in now
            out["stages"].append({"stage": out["stage"], "from": js[-1]["from"]})
            note += ". Its earlier tickets are further on; it is back in this stage for new work"
        out["basisNote"] = note + "."

    def extra_rows(self, on_dashboard):
        ew = self.ctx.tl.get("earlier_work") or {}
        known = {a["name"] if isinstance(a, dict) else a for g in self.ctx.tl["groups"] for a in g["areas"]}
        rows = {}
        for s in self.earlier:
            area = next((c for c in s["components"] if c in known), None) or (ew.get("epic_areas") or {}).get(s.get("epicName"))
            guess = not area
            area = area or ew.get("fallback_area")
            stages = stages_from_jira([s["key"]], self.hist)
            if s["done"] and (not stages or stages[-1]["stage"] != "done"):
                # done in Jira without a recorded move to done (e.g. a bulk edit): use the resolution date
                day = s.get("resolved") or (stages[-1]["from"] if stages else s["created"])
                stages = [x for x in stages if x["from"] <= day] + [{"stage": "done", "from": day}]
            if not stages:
                stages = [{"stage": "ready", "from": s["created"]}]
            last = stages[-1]
            done = last["from"] if last["stage"] == "done" else None
            rows.setdefault(area, []).append({
                "id": s["key"], "label": s["summary"], "stage": last["stage"], "doneDate": done,
                "since": s["created"], "desc": "", "clar": None, "clarLabel": None, "guess": guess,
                "origin": "old-work", "basis": "tracker",
                "originNote": ("A Jira story from before %s" % self._day(self.ctx.start) if s["created"] < self.ctx.start
                               else "A Jira ticket that is not on the dashboard") + (", in the epic “%s”." % s["epicName"] if s.get("epicName") else "."),
                "work": [{"id": s["key"], "title": s["summary"], "status": s["status"], "done": done}],
                "stages": stages, "tags": self.tags_of_work([{"id": s["key"]}]), "who": []})
        return rows

    def area_link(self, area):
        for e in self.ctx.data["epics"]:
            if e["label"] == area and e.get("prod") == self.ctx.product["dashboard"]:
                url = (e.get("jira") or {}).get("search")
                return {"url": url, "label": "See all in Jira"} if url else None
        return None

    @staticmethod
    def _day(iso_day):
        d = dt.date.fromisoformat(iso_day)
        return "%d %s %d" % (d.day, d.strftime("%b"), d.year)

    def footer(self):
        rec = [f.get("title") or f["id"] for f in self.ctx.tl.get("features") or []]
        names = ", ".join(rec[:-1]) + " and " + rec[-1] if len(rec) > 1 else "".join(rec)
        return ("the BA dashboard, the timeline data file, Jira and the intake files. %sFaded bars have no stage history "
                "yet. %s, with stage dates from their Jira history; switch off \"Hide "
                "done\" to see the finished ones. * = placed here by guess." % (
                    "Bars of %s show recorded stage dates. " % names if rec else "",
                    "Rows from before %s are Jira stories" % self._day(self.ctx.start) if self.until == self.ctx.start
                    else "Rows not on the dashboard are Jira tickets"))
