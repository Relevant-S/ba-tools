"""Build a project's timeline page — the shared part, the same in every project.

The page is the BA dashboard's features over time: areas → features → changes and bugs, with the calls,
emails, comments and documents behind them, plus three list tabs (Clarification pages, To-dos, Next meeting
agenda). It never writes to the dashboard.

Shared here (every project):  the dashboard's features, to-dos and agenda; pins from the intake files and the
data file; decisions from the clarification pages; recorded features (stage dates written by hand); the plain
descriptions file; the Clarification pages tab.
From the tracker plug-in (scripts/trackers/<tracker>.py):  stage dates and work items of each feature, old work
not on the dashboard, changes and bugs, releases, the area link. See trackers/__init__.py for the hooks.

Reads, read only (paths from the project's docs/BA folder):
  <data file>                          the timeline data file: product settings, area groups, placements,
                                       recorded features, pins, tags, `upcoming` (planned deadlines,
                                       releases and steps; checked here), plus whatever the tracker needs
  mind-map/mind-map.html               the dashboard's built data (areas, features, stage, tickets, releases)
  dashboard.yaml                       client text, clarification links, to-dos
  clarifications/*-decisions.yaml      the Clarification pages tab and "Decided" on pins
  intake/ and intake/.processed/       one pin per call, email, comment batch, document, page answers
  <data folder>/descriptions.yaml      optional: 2–3 plain bullets per row without client text
Writes:
  <data folder>/<out>.html             the page to publish (default: <data file name>.html)
  --json PATH                          instead of the page: only the page's data (`payload`) as JSON, at PATH.
                                       portal-publish's `timeline plan` reads it and makes the timeline/1 send.

Run from the project's repo root:
  python <ba-tools>/skills/timeline/scripts/build.py docs/BA/timeline/<project>-timeline.yaml
"""
import argparse, datetime as dt, importlib, json, re, sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
TODAY = dt.date.today()
PIN_TITLE = {"call": "Client call", "email": "Email", "comments": "Comments", "doc": "Document", "page": "Clarification-page answers"}


def iso(d):
    return d if isinstance(d, str) else d.isoformat()


def front(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    try:
        return yaml.safe_load(m.group(1)) if m else {}
    except yaml.YAMLError:
        return {}


def person(who):
    """'sam@acme.example' -> 'Sam'; 'Pat Lee (U0000000001)' (Slack) -> 'Pat'."""
    local = who.split("@")[0].split(".")[0] if "@" in who else who.split("(")[0].strip().split(" ")[0]
    return local[:1].upper() + local[1:]


def cp_url(d):
    """The feature's clarification page — only a claude.ai artifact link counts (Vadim, 5 Nov: the client spec
    docs in Google Docs were a wrong turn)."""
    u = (d.get("clar") or {}).get("url") or ""
    return u if re.match(r"https://claude\.ai/(?:code/)?artifact/", u) else None


def settings(tl):
    """The product settings: the data file's `product:` block, with fallbacks from the older keys."""
    p = dict(tl.get("product") or {})
    proj = tl.get("project") or p.get("name") or "Product"
    p.setdefault("name", proj)
    p.setdefault("dashboard", proj)                       # the dashboard's product name ("AcmeLending", "NWE")
    p.setdefault("clarifications", str(p["dashboard"]).lower())   # `product:` in the clarification files
    p.setdefault("tag_word", tl.get("tag_label") or "Phase")
    p.setdefault("tracker", "none")
    p.setdefault("ba", "the BA")
    p.setdefault("staff_domain", "relevant.software")
    return p


# ---------- pins from the intake files
INTAKE_KIND = {"fireflies": "call", "plaud": "call", "manual": "call", "gmail": "email", "slack": "comments",
               "confluence": "comments", "document": "doc", "portal": "page"}


def pins_from_intake(ba, start, product):
    """One pin per day and kind. A call recorded in parts counts once."""
    kinds = {}
    skip = re.compile(product["intake_skip"], re.I) if product.get("intake_skip") else None
    pages = {}                                             # clarification page slug -> its product
    for c in (ba / "clarifications").glob("*-decisions.yaml"):
        m = re.search(r"^product:\s*(\S+)", c.read_text(encoding="utf-8", errors="replace"), re.M)
        pages[c.name[:-len("-decisions.yaml")]] = m.group(1) if m else None
    for f in list((ba / "intake").glob("*.md")) + list((ba / "intake" / ".processed").glob("*.md")):
        if skip and skip.search(f.name):
            continue                                       # another product's file (product.intake_skip)
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(?:\d{4}-)?([a-z]+)-(.*)\.md$", f.name)
        if not m:
            continue
        day, src, rest = m.groups()
        if day < start:
            continue
        if src == "client":                                # client-call-… / client-message-…
            src = "fireflies" if rest.startswith("call") else "gmail"
        kind = INTAKE_KIND.get(src)
        if not kind:
            continue
        if src == "slack" and product.get("slack_prefix") and not rest.startswith(product["slack_prefix"]):
            continue                                       # another product's channel
        if src == "portal" and pages.get(re.sub(r"-decisions$", "", rest)) not in (None, product.get("clarifications")):
            continue                                       # answers on another product's clarification page
        e = kinds.setdefault((day, kind), {"n": 0, "slugs": [], "files": [], "srcs": set()})
        e["n"] += 1
        e["slugs"].append(rest)
        e["files"].append(f)
        e["srcs"].add(src)
    out = []
    for (day, kind), e in sorted(kinds.items()):
        words = re.sub(r"-[0-9a-f]{6,}$", "", e["slugs"][0]).replace("-", " ")
        words = words[:1].upper() + words[1:]
        if kind == "call":
            title = "Client call"
        elif kind in ("email", "doc"):
            title = PIN_TITLE[kind] + (" · " + words if words else "")
        elif kind == "comments":
            title = ("Slack · %d message%s" if e["srcs"] == {"slack"} else "Comments · %d batch%s") % (
                e["n"], "" if e["n"] == 1 else ("s" if e["srcs"] == {"slack"} else "es"))
        else:
            title = "Answers on %d clarification page%s" % (e["n"], "" if e["n"] == 1 else "s")
        out.append({"id": "%s-%s" % (day, kind), "date": day, "kind": kind, "title": title, "files": e["files"]})
    return out


def pin_details(m, product):
    """People, minutes, subject and the summary bullets of a pin's intake files."""
    out = {"people": [], "staff": 0, "minutes": 0, "summary": [], "subject": None}
    drop = re.compile(product["summary_drop"], re.I) if product.get("summary_drop") else None
    seen = set()
    for f in m.get("files", []):
        text = Path(f).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        fm = front(text) or {}
        for e in fm.get("participants") or []:
            e = str(e).strip()
            if product["staff_domain"] in e.lower():
                if e.lower() not in seen:
                    out["staff"] += 1
            elif person(e) not in out["people"]:
                out["people"].append(person(e))
            seen.add(e.lower())
        if fm.get("subject") and not out["subject"]:
            out["subject"] = str(fm["subject"])
        d = re.search(r"\*\*Duration:\*\*\s*(\d+)", text)
        if d:
            out["minutes"] += int(d.group(1))
        sm = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        for line in (sm.group(1).splitlines() if sm else []):
            line = line.strip()
            if not line.startswith("- "):
                continue
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line[2:]).strip().replace("�", "'")
            if line and not (drop and drop.search(line)) and line not in out["summary"]:
                out["summary"].append(line)
    out["summary"] = out["summary"][:6]
    return out


# ---------- upcoming: planned events after today (deadlines, releases, planned steps)
UPCOMING_KINDS = ("deadline", "release", "planned")


class DataError(Exception):
    """A plain one-line problem in the data file. The build stops with it."""


def check_upcoming(items, feature_ids):
    """The data file's `upcoming:` list, checked and tidied for the page.

    Each item: id (unique), title (up to 300), kind (deadline · release · planned); then `date`, or `after`
    (a feature id), or neither ("no date yet"); optional `what` (up to 20 lines), `needs` (feature ids),
    `who` (up to 200). Raises DataError with one plain line naming the item."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise DataError("upcoming: must be a list of items (each starts with \"- id: …\").")
    out, seen = [], set()
    for n, u in enumerate(items, 1):
        if not isinstance(u, dict):
            raise DataError("upcoming item %d: must be a block with id, title and kind." % n)
        uid = str(u.get("id") or "").strip()
        name = "upcoming item \"%s\"" % uid if uid else "upcoming item %d" % n
        if not uid:
            raise DataError("%s: has no id." % name)
        if uid in seen:
            raise DataError("%s: the id is used twice — give each item its own id." % name)
        seen.add(uid)
        extra = sorted(set(u) - {"id", "title", "kind", "date", "after", "what", "needs", "who"})
        if extra:
            raise DataError("%s: unknown field %s (use id, title, kind, date, after, what, needs, who)." % (name, ", ".join(extra)))
        title = str(u.get("title") or "").strip()
        if not title:
            raise DataError("%s: has no title." % name)
        if len(title) > 300:
            raise DataError("%s: the title is longer than 300 characters." % name)
        kind = str(u.get("kind") or "").strip()
        if kind not in UPCOMING_KINDS:
            raise DataError("%s: kind must be deadline, release or planned (it is \"%s\")." % (name, kind))
        item = {"id": uid, "title": title, "kind": kind}
        if u.get("date") is not None and u.get("after") is not None:
            raise DataError("%s: has both a date and \"after\" — keep one." % name)
        if u.get("date") is not None:
            day = u["date"]
            if isinstance(day, dt.datetime):
                day = day.date()
            if not isinstance(day, dt.date):
                try:
                    day = dt.date.fromisoformat(str(day).strip())
                except ValueError:
                    raise DataError("%s: the date \"%s\" is not a date like 2026-12-17." % (name, u["date"]))
            item["date"] = day.isoformat()
        if u.get("after") is not None:
            after = str(u["after"]).strip()
            if after not in feature_ids:
                raise DataError("%s: \"after: %s\" is not a feature on this timeline." % (name, after))
            item["after"] = after
        what = u.get("what")
        if what is not None:
            lines = [str(x).strip() for x in what] if isinstance(what, list) else str(what).splitlines()
            lines = [x[2:].strip() if x.startswith("- ") else x for x in (y.strip() for y in lines)]
            lines = [x for x in lines if x]
            if len(lines) > 20:
                raise DataError("%s: \"what\" has more than 20 lines." % name)
            if lines:
                item["what"] = lines
        needs = u.get("needs")
        if needs is not None:
            needs = needs if isinstance(needs, list) else [needs]
            needs = [str(x).strip() for x in needs if str(x).strip()]
            bad = [x for x in needs if x not in feature_ids]
            if bad:
                raise DataError("%s: \"needs\" names %s, not a feature on this timeline." % (name, ", ".join(bad)))
            if needs:
                item["needs"] = list(dict.fromkeys(needs))
        who = u.get("who")
        if who is not None:
            who = ", ".join(str(x).strip() for x in who) if isinstance(who, list) else str(who).strip()
            if len(who) > 200:
                raise DataError("%s: \"who\" is longer than 200 characters." % name)
            if who:
                item["who"] = who
        out.append(item)
    return out


def release_lines(releases, today):
    """The release lines: every released release with a date, and the unreleased ones dated today or later
    (future releases show after today; one whose date has passed without a release is left out)."""
    keep = [{"name": r["name"], "date": iso(r["date"])} for r in releases
            if r.get("date") and (r.get("released") or iso(r["date"]) >= today.isoformat())]
    return sorted(keep, key=lambda r: r["date"])


def load_dashboard_data(ba):
    html = (ba / "mind-map" / "mind-map.html").read_text(encoding="utf-8")
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    if not m:
        sys.exit("Could not find the dashboard data in mind-map.html")
    return json.loads(m.group(1))


def main():
    ap = argparse.ArgumentParser(description="Build the timeline page")
    ap.add_argument("data_file", help="the project's timeline data file, e.g. docs/BA/timeline/epd-timeline.yaml")
    ap.add_argument("--ba", default="docs/BA", help="the project's BA folder (default docs/BA)")
    ap.add_argument("--out", help="the page to write (default: next to the data file, .html)")
    ap.add_argument("--json", metavar="PATH", help="write only the page's data, as JSON, to PATH (no page)")
    args = ap.parse_args()

    data_file = Path(args.data_file).resolve()
    here, ba = data_file.parent, Path(args.ba).resolve()
    tl = yaml.safe_load(data_file.read_text(encoding="utf-8"))
    product = settings(tl)
    dash = yaml.safe_load((ba / "dashboard.yaml").read_text(encoding="utf-8"))
    data = load_dashboard_data(ba)
    start = iso(tl["start"])
    PROD = product["dashboard"]

    # ---- pins: the intake files, then the data file's own (`pins:`, older files `milestones:`)
    pins = {m["id"]: m for m in pins_from_intake(ba, start, product)}
    for m in tl.get("pins") or tl.get("milestones") or []:
        if m["kind"] in ("release", "ba"):
            continue
        day = iso(m["date"])
        key = "%s-%s" % (day, m["kind"])
        if key in pins and m["kind"] != "call":
            key = "%s-%s-%s" % (day, m["kind"], m["id"])      # a second item of the same kind on the same day
        pins.setdefault(key, {"id": key, "date": day, "kind": m["kind"], "title": m["title"] if m["kind"] != "call" else "Client call"})
        pins[key]["ref"] = m["id"]
        if m["kind"] == "call" and "(" in m["title"]:
            pins[key]["title"] = "Client call " + m["title"][m["title"].index("("):]
    pins = sorted(pins.values(), key=lambda m: (m["date"], m["kind"]))

    decided = {}
    for f in sorted((ba / "clarifications").glob("*-decisions.yaml")):
        cd = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if cd.get("product") != product["clarifications"]:
            continue
        for x in cd.get("decisions") or []:
            if x.get("date"):
                decided.setdefault(iso(x["date"]), []).append({"title": x.get("title", ""), "page": cd.get("name") or cd.get("slug", ""), "how": x.get("how") or "", "url": cd.get("url")})
    owes = {}
    for a in (dash.get("awaiting") or []) + (dash.get("todos") or []):
        if a.get("done") or a.get("prod") not in (PROD, "Both") or not a.get("since"):
            continue
        owes.setdefault(iso(a["since"]), []).append({"who": a.get("who", ""), "text": a.get("client_s") or a.get("t", "")})
    kind_words = {"call": ("on the client call", "relayed from", "answered for"), "page": ("page", "portal", "send button"), "email": ("email",)}
    for m in pins:
        m.update({k: v for k, v in pin_details(m, product).items() if v})
        m.pop("files", None)
        ds = [x for x in decided.get(m["date"], []) if any(w in x["how"].lower() for w in kind_words.get(m["kind"], ()))]
        if ds:
            m["decided"] = ds
        if m["kind"] == "call" and owes.get(m["date"]):
            m["owes"] = owes[m["date"]]
    ref_to_pin = {m.get("ref"): m["id"] for m in pins if m.get("ref")}

    def add_pin(day, kind, who=None, subject=None):
        """A pin for a source the tracker names (a change's email or document): the one on that day and channel,
        else a new one. Returns its id."""
        pid = "%s-%s" % (day, kind)
        m = next((x for x in pins if x["id"] == pid), None)
        if not m:
            m = {"id": pid, "date": day, "kind": kind, "title": PIN_TITLE.get(kind, "Source"), "people": []}
            if subject:
                m["subject"] = subject
            pins.append(m)
        if who and who not in (m.get("people") or []):
            m.setdefault("people", []).append(who)
        return pid

    # ---- the tracker plug-in
    ctx = argparse.Namespace(ba=ba, repo=ba.parents[1], here=here, tl=tl, dash=dash, data=data, start=start,
                             today=TODAY, product=product, add_pin=add_pin)
    mod = importlib.import_module("trackers." + product["tracker"].replace("-", "_")) if product["tracker"] != "none" else importlib.import_module("trackers")
    tracker = getattr(mod, "Tracker", None) or mod.Base
    tracker = tracker(ctx)

    # ---- the dashboard's features by area (placements put area-less ones somewhere, marked as a guess)
    placements = tl.get("placements") or {}
    by_area = {}
    for epic in data["epics"]:
        for f in epic.get("features", []):
            if f.get("prod") not in (PROD, "Both") or f["id"] == "unlinked":
                continue
            area, guess = epic["label"], False
            if area in ("No area", "Not linked yet"):
                if f["id"] not in placements:
                    continue
                area, guess = placements[f["id"]], True
            by_area.setdefault(area, []).append((f, guess))
    tracker.prepare([f for fs in by_area.values() for f, _ in fs])

    client_text = {f["id"]: f for f in dash.get("features", [])}
    recorded = {f["id"]: f for f in tl.get("features") or []}
    hand_tags = tl.get("tags") or tl.get("phases") or {}
    extra_tags = tl.get("extra_tags") or {}

    def extra_tags_of(key):
        v = extra_tags.get(key)
        return [str(t).strip() for t in (v if isinstance(v, list) else [v]) if str(t or "").strip()]
    item_first = {}
    for lst in ("awaiting", "todos", "agenda"):
        for a in dash.get(lst) or []:
            if a.get("feature") and a.get("since"):
                day = iso(a["since"])
                if a["feature"] not in item_first or day < item_first[a["feature"]]:
                    item_first[a["feature"]] = day

    def feature_out(f, guess):
        fid = f["id"]
        d, r = client_text.get(fid, {}), recorded.get(fid)
        out = {
            "id": fid, "label": re.sub(r"\s*\(shipped [^)]*\)$", "", f["label"]),
            "stage": f.get("stageKey") or f.get("stage") or "concept", "doneDate": f.get("doneDate"),
            "since": iso(d["since"]) if d.get("since") else None, "desc": d.get("client_s") or "",
            "clar": cp_url(d), "clarLabel": (d.get("clar") or {}).get("label") if cp_url(d) else None,
            "guess": guess, "origin": "dashboard", "basis": "none", "work": [],
        }
        if r:
            # stage dates written by hand in the data file win over the tracker
            out["stages"] = [{"stage": s["stage"], "from": iso(s["from"])} for s in r["stages"]]
            out["basis"], out["work"] = "recorded", tracker.feature_work(f)
            out["startedBefore"] = iso(r["started_before_start"]) if r.get("started_before_start") else None
            out["askedIn"], out["askedBy"] = ref_to_pin.get(r.get("asked_in")), r.get("asked_by")
            out["requests"] = [{
                "id": q["id"], "kind": q["kind"], "title": q["title"],
                "askedIn": ref_to_pin.get(q["asked_in"]), "askedBy": q.get("asked_by"),
                "stages": [{"stage": s["stage"], "from": iso(s["from"])} for s in q["stages"]],
                "work": tracker.work_items(q.get("jira") or q.get("work") or []),
                "merged": iso(q["merged"]) if q.get("merged") else None, "splitOff": q.get("split_off"),
            } for q in r.get("requests", [])]
            if r["stages"]:
                out["stage"] = r["stages"][-1]["stage"]
        else:
            starts = [x for x in (out["since"], item_first.get(fid)) if x]
            if starts and not out["since"]:
                out["since"] = min(starts)
            tracker.feature(f, out, min(starts) if starts else None)
        if not out["since"] and out.get("stages"):
            out["since"] = out["stages"][0]["from"]
        # the dashboard's own items (waiting, to-do, next-call agenda), with the dashboard's keys, so a note
        # saved on the page syncs into dashboard.yaml exactly like one saved on the dashboard
        items = [{k: c.get(k) for k in ("key", "id", "kind", "title", "who", "since", "age", "status", "prod", "s", "l")}
                 for c in f.get("children") or [] if not c.get("done") and c.get("kind") in ("waiting", "todo", "agenda")]
        if items:
            out["todos"] = sorted(items, key=lambda x: str(x["since"] or ""))
        if d.get("open"):
            out["openQ"] = [str(q) for q in d["open"]]
        # tags: recorded `phase:` > the data file's `tags:` > the tracker's
        if r and r.get("phase"):
            out["tags"] = [str(r["phase"])]
        elif str(hand_tags.get(fid) or "").strip():
            out["tags"] = [str(hand_tags[fid]).strip()]
        else:
            out.setdefault("tags", tracker.tags_of_work(out["work"]))
        for q, src in zip(out.get("requests") or [], (r or {}).get("requests") or []):
            qt = [str(src["phase"])] if src.get("phase") else tracker.tags_of_work(q["work"])
            if qt and qt != out["tags"]:
                q["tags"] = qt
        who = [w.strip().split(" ")[0] for w in str(d.get("who") or "").replace("&", "+").split("+") if w.strip()]
        if r and r.get("asked_by"):
            who.append(str(r["asked_by"]).split(" ")[0])
        out["who"] = sorted(set(w for w in who if w and w != "Easy"))
        return out

    # ---- areas: the dashboard's features, then the tracker's rows that are not on the dashboard
    extra = tracker.extra_rows({f["id"] for fs in by_area.values() for f, _ in fs})
    # rows written by hand in the data file (`hand_rows:`), for items with no dashboard feature, spec or story —
    # e.g. client feedback rows fixed straight in the code (Vadim, 11 Nov 2026)
    for h in tl.get("hand_rows") or []:
        stages = [{"stage": s["stage"], "from": iso(s["from"])} for s in h.get("stages") or []]
        row = {"id": str(h["id"]), "label": str(h["label"]), "stage": stages[-1]["stage"] if stages else h["stage"],
               "doneDate": iso(h["done"]) if h.get("done") else None, "since": iso(h["since"]) if h.get("since") else
               (stages[0]["from"] if stages else None), "desc": "", "clar": None, "clarLabel": None, "guess": False,
               "origin": "dashboard", "basis": "code" if stages else "none", "work": [], "tags": [], "who": [],
               "originNote": str(h.get("note") or "From the client feedback sheet.")}
        if stages:
            row["stages"] = stages
        elif row["since"]:
            # no recorded stage dates: one stage from the day it was asked, so it can still sit under a parent
            row["stages"] = [{"stage": row["stage"], "from": row["since"]}]
        if h.get("basis_note"):
            row["basisNote"] = str(h["basis_note"])
        if h.get("kind"):
            row["kind"] = str(h["kind"])
        extra.setdefault(str(h["area"]), []).append(row)
    # Big features (Vadim, 10 Nov 2026): an area may list its `rows:` — the ids of every row under it, in the
    # order shown. A listed row moves there from wherever the dashboard or the tracker put it, and is no guess.
    place, order = {}, {}
    for g in tl["groups"]:
        for a in g["areas"]:
            for i, rid in enumerate((a.get("rows") or []) if isinstance(a, dict) else []):
                if str(rid) in place:
                    raise DataError("Row %s is listed under both %s and %s." % (rid, place[str(rid)], a["name"]))
                place[str(rid)], order[str(rid)] = a["name"], i
    if place:
        moved = {}
        for area, fs in by_area.items():
            for f, guess in fs:
                moved.setdefault(place.get(f["id"], area), []).append((f, guess and f["id"] not in place))
        by_area, moved = moved, {}
        for area, rows in extra.items():
            for f in rows:
                if f["id"] in place:
                    f["guess"] = False
                moved.setdefault(place.get(f["id"], area), []).append(f)
        extra = moved
    known = set()
    groups = []
    for g in tl["groups"]:
        areas = []
        for a in g["areas"]:
            name = a["name"] if isinstance(a, dict) else a
            known.add(name)
            row = {"name": name,
                   "features": [feature_out(f, guess) for f, guess in by_area.get(name, [])]
                               + sorted(extra.pop(name, []), key=lambda f: f.get("since") or "")}
            if place:
                row["features"].sort(key=lambda f: order.get(f["id"], 10 ** 6))
            link = tracker.area_link(name)
            if link:
                row["link"] = link
            areas.append(row)
        groups.append({"name": g["name"], "areas": areas})
    left_out = sorted(a for a in by_area if a not in known)
    if left_out:
        print("Not on the timeline (no such area in the data file): " + ", ".join("%s (%d)" % (a, len(by_area[a])) for a in left_out))
    for a, rows in extra.items():
        print("No such area in the data file: %s (%d rows from %s left out)" % (a, len(rows), tracker.title))

    rows_by_id = {f["id"]: f for g in groups for a in g["areas"] for f in a["features"]}
    # plain descriptions for rows without the dashboard's client text (Vadim, 5 Nov)
    dpath = here / "descriptions.yaml"
    about = (yaml.safe_load(dpath.read_text(encoding="utf-8")) or {}) if dpath.exists() else {}
    # an entry is a list of bullets, or {about: [...], figma: <link>, figma_where: "<page> → <frame>"};
    # a QA bug or change under a row is described by its own id the same way
    def describe(target, entry):
        if isinstance(entry, dict):
            if entry.get("about"):
                target["about"] = [str(x) for x in entry["about"]][:20]
            if str(entry.get("figma") or "").startswith("https://www.figma.com/"):
                target["figma"] = str(entry["figma"])
                if entry.get("figma_where"):
                    target["figmaWhere"] = str(entry["figma_where"])
        elif entry:
            target["about"] = [str(x) for x in entry][:20]
    missing = []
    for f in rows_by_id.values():
        if about.get(f["id"]):
            describe(f, about[f["id"]])
        if not f.get("about") and not f.get("desc"):
            missing.append(f["id"])
    if missing and dpath.exists():
        print("No description yet (add to descriptions.yaml): %d — %s" % (len(missing), ", ".join(missing[:12])))
    # stage dates written by hand win over the tracker for every row, not only the dashboard's (Vadim, 11 Nov 2026)
    for fid, r in recorded.items():
        f = rows_by_id.get(fid)
        if f and r.get("stages") and f.get("basis") != "recorded":
            f["stages"] = [{"stage": s["stage"], "from": iso(s["from"])} for s in r["stages"]]
            f["stage"], f["basis"] = f["stages"][-1]["stage"], "recorded"
            if f["stage"] in ("done", "live"):
                f["doneDate"] = f["stages"][-1]["from"]
    tracker.add_requests(rows_by_id)
    for f in rows_by_id.values():
        for q in f.get("requests") or []:
            if about.get(q["id"]):
                describe(q, about[q["id"]])
    # what each row is inside its big feature: the first build, something new, or a change (the tracker marks those)
    # `row_kinds:` in the data file overrides it per row, e.g. a client-reported bug shown as "bug" (Vadim, 11 Nov 2026)
    row_kinds = tl.get("row_kinds") or {}
    for f in rows_by_id.values():
        f.setdefault("kind", "build" if f.get("origin") == "old-work" else "new")
        if row_kinds.get(f["id"]):
            f["kind"] = str(row_kinds[f["id"]])
    for k in sorted(set(row_kinds) - set(rows_by_id)):
        print("row_kinds: no such row: %s" % k)
    # extra tags (e.g. "Before Global"), from the data file's `extra_tags:`, added after the phase or release —
    # on every row, whether it came from the dashboard, a spec or the tracker
    for f in rows_by_id.values():
        f["tags"] = list(f.get("tags") or [])
        f["tags"] += [t for t in extra_tags_of(f["id"]) if t not in f["tags"]]
        for q in f.get("requests") or []:
            more = extra_tags_of(q["id"])
            if more:
                base = q.get("tags") or f["tags"]
                q["tags"] = list(base) + [t for t in more if t not in base]
    unknown = sorted(k for k in extra_tags if k not in rows_by_id
                     and not any(q["id"] == k for f in rows_by_id.values() for q in f.get("requests") or []))
    if unknown:
        print("extra_tags: no such row or change: " + ", ".join(map(str, unknown)))
    # ---- the one item model (`items: specs`, Vadim 11 Nov 2026): every row is a spec item. Its type, tags, summary,
    # Figma link and outside references come from the spec; an item with a `parent` shows once, under the item at
    # the top of its parent chain, all on one level, and takes that top item's area.
    if tl.get("items") == "specs" and hasattr(tracker, "item_of"):
        for r in getattr(tracker, "child_rows", []):
            r.setdefault("tags", [])
            rows_by_id.setdefault(r["id"], r)
        item_of = tracker.item_of

        def kind_of(it):
            t = (it or {}).get("type")
            if t == "feature" or not t:
                return "build" if (it or {}).get("baseline") else None
            return str(t)

        def fill(target, it):
            for t in it.get("tags") or []:
                if str(t) not in target.setdefault("tags", []):
                    target["tags"].append(str(t))
            if it.get("summary"):
                target["about"] = list(it["summary"])
            if str(it.get("figma") or "").startswith("https://www.figma.com/"):
                target["figma"] = str(it["figma"])
                if it.get("figma_where"):
                    target["figmaWhere"] = str(it["figma_where"])
            ref = next((r for r in it.get("refs") or [] if isinstance(r, dict)), None)
            if ref:
                pin = tracker.pin_for_ref(ref)
                if pin and not target.get("askedIn"):
                    target["askedIn"] = pin
                target["askedBy"] = target.get("askedBy") or ref.get("who")
                if ref.get("asked"):
                    target["asked"] = str(ref["asked"])

        by_key = {}
        for fid, f in rows_by_id.items():
            it = item_of(fid)
            if it:
                by_key[it["key"]] = fid
                fill(f, it)
                k = kind_of(it)
                if k:
                    f["kind"] = k
                elif f.get("kind") == "change":
                    f["kind"] = "new"

        def top_of(fid):
            seen, cur = set(), fid
            while True:
                it = item_of(cur)
                par = (it or {}).get("parent")
                if not par or par not in by_key or by_key[par] in seen:
                    return cur
                seen.add(cur)
                cur = by_key[par]

        gone = set()
        for fid in list(rows_by_id):
            it = item_of(fid)
            if not it or not it.get("parent"):
                continue
            top = top_of(fid)
            if top == fid or top not in rows_by_id:
                print("Item %s: parent %s is not on the timeline" % (it["key"], it["parent"]))
                continue
            s, p = rows_by_id[fid], rows_by_id[top]
            k = kind_of(it) or "sub-feature"
            q = {"id": fid, "kind": k if k in ("bug", "change", "improvement", "sub-feature") else "sub-feature",
                 "title": s["label"], "stages": s.get("stages") or [{"stage": s.get("stage") or "spec", "from": s.get("since") or TODAY.isoformat()}],
                 "work": s.get("work") or [], "merged": None, "splitOff": None, "guess": False,
                 "tags": list(s.get("tags") or [])}
            for k_ in ("about", "figma", "figmaWhere", "askedIn", "askedBy", "asked"):
                if s.get(k_):
                    q[k_] = s[k_]
            p.setdefault("requests", []).append(q)
            gone.add(fid)
        for g in groups:
            for a in g["areas"]:
                a["features"] = [f for f in a["features"] if f["id"] not in gone]
        for fid in gone:
            rows_by_id.pop(fid, None)
        print("Items under their top parent: %d" % len(gone))
    # `nest_changes: true` (Vadim, 11 Nov 2026): a change or bug with a `parent` shows ONCE, under its parent row,
    # on the same level as the others — its own row is removed, and what the row carried moves onto the item
    if tl.get("nest_changes"):
        gone = set()
        for f in list(rows_by_id.values()):
            for q in f.get("requests") or []:
                s = rows_by_id.get(q.get("self"))
                if not s or s is f:
                    continue
                q["kind"] = s.get("kind") if s.get("kind") in ("bug", "change", "improvement", "sub-feature") else q["kind"]
                q["tags"] = list(s.get("tags") or [])
                for k_ in ("about", "figma", "figmaWhere"):
                    if s.get(k_):
                        q[k_] = s[k_]
                q.pop("self", None)
                gone.add(s["id"])
        for g in groups:
            for a in g["areas"]:
                a["features"] = [f for f in a["features"] if f["id"] not in gone]
        for fid in gone:
            rows_by_id.pop(fid, None)
        print("Nested under their parent rows: %d" % len(gone))
    for f in rows_by_id.values():
        if f.get("requests"):
            f["requests"].sort(key=lambda q: q["stages"][0]["from"] if q.get("stages") else "")
    # `id_in_label: [TKT]` (Vadim, 12 Nov 2026): rows and items with these ids show the id before their name,
    # "TKT-64 - Agenda sessions …", so the client finds its own ticket numbers on the page
    id_pre = [str(x).upper() for x in tl.get("id_in_label") or []]
    if id_pre:
        def _named(it, key):
            m = re.fullmatch(r"(?:chg-)?([a-z]+)(\d+)", str(it.get("id") or ""))
            if m and m.group(1).upper() in id_pre and it.get(key):
                code = "%s-%02d" % (m.group(1).upper(), int(m.group(2)))
                if not it[key].startswith(code):
                    it[key] = "%s - %s" % (code, it[key])
        for f in rows_by_id.values():
            _named(f, "label")
            for q in f.get("requests") or []:
                _named(q, "title")
    pins.sort(key=lambda m: (m["date"], m["kind"]))

    # released releases, and the dated ones still to come (they draw after today)
    releases = tracker.releases(release_lines(data["board"]["releases"].get(PROD, []), TODAY))
    # ---- upcoming: deadlines, releases and planned steps from the data file
    try:
        upcoming = check_upcoming(tl.get("upcoming"), set(rows_by_id))
    except DataError as e:
        sys.exit("Stopped: " + str(e))

    # ---- the Clarification pages tab
    by_clar = {f["clar"]: f["id"] for f in rows_by_id.values() if f.get("clar")}
    pages = []
    for p in sorted((ba / "clarifications").glob("*-decisions.yaml")):
        c = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if c.get("product") != product["clarifications"] or not c.get("url"):
            continue
        pages.append({
            "slug": c.get("slug") or p.stem, "name": c.get("name") or c.get("doc_title") or p.stem,
            "title": re.sub(r"<[^>]+>", "", str(c.get("title") or "")), "url": c["url"],
            "round": re.sub(r"<[^>]+>|&middot;", lambda m: "·" if m.group(0) == "&middot;" else "", str(c.get("round") or "")).strip(),
            "open": len(c.get("questions") or []), "decided": len(c.get("decisions") or []),
            "feature": by_clar.get(c["url"]),
            "updated": max((iso(e["date"]) for e in (c.get("events") or []) if e.get("date")), default=None),
        })

    first = min((f["since"] for f in rows_by_id.values() if f.get("since")), default=None)
    payload = {
        "product": {"name": product["name"], "tagWord": product["tag_word"], "tracker": tracker.name,
                    "workLink": tracker.work_link, "ba": product["ba"], "footer": tracker.footer()},
        "today": TODAY.isoformat(), "start": start, "from": first if first and first < start else None,
        "built": dt.datetime.now().strftime("%d %b %Y, %H:%M"),
        "groups": groups, "pins": pins, "releases": releases, "pages": pages,
        "dashboardUrl": data.get("mapUrl"),
    }
    if upcoming:
        payload["upcoming"] = upcoming
    if args.json:
        out = Path(args.json).resolve()
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    else:
        tpl = (SKILL / "template.html").read_text(encoding="utf-8")
        page = tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False)).replace("__PRODUCT__", product["name"])
        out = Path(args.out).resolve() if args.out else data_file.with_suffix(".html")
        out.write_text(page, encoding="utf-8")
    print("Built %s: %d areas, %d rows (%d not on the dashboard), %d pins, %d releases, %d coming up, %d clarification pages · tracker: %s" % (
        out.name, sum(len(g["areas"]) for g in groups), len(rows_by_id),
        sum(1 for f in rows_by_id.values() if f["origin"] != "dashboard"), len(pins), len(releases), len(upcoming), len(pages), tracker.name))


if __name__ == "__main__":
    main()
