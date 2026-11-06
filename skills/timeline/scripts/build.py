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
                                       recorded features, pins, tags, plus whatever the tracker needs
  mind-map/mind-map.html               the dashboard's built data (areas, features, stage, tickets, releases)
  dashboard.yaml                       client text, clarification links, to-dos
  clarifications/*-decisions.yaml      the Clarification pages tab and "Decided" on pins
  intake/ and intake/.processed/       one pin per call, email, comment batch, document, page answers
  <data folder>/descriptions.yaml      optional: 2–3 plain bullets per row without client text
Writes:
  <data folder>/<out>.html             the page to publish (default: <data file name>.html)

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
    for f in list((ba / "intake").glob("*.md")) + list((ba / "intake" / ".processed").glob("*.md")):
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
    missing = []
    for f in rows_by_id.values():
        if about.get(f["id"]):
            f["about"] = [str(x) for x in about[f["id"]]]
        elif not f.get("desc"):
            missing.append(f["id"])
    if missing and dpath.exists():
        print("No description yet (add to descriptions.yaml): %d — %s" % (len(missing), ", ".join(missing[:12])))
    tracker.add_requests(rows_by_id)
    for f in rows_by_id.values():
        if f.get("requests"):
            f["requests"].sort(key=lambda q: q["stages"][0]["from"] if q.get("stages") else "")
    pins.sort(key=lambda m: (m["date"], m["kind"]))

    releases = tracker.releases(sorted(
        [{"name": r["name"], "date": r["date"]} for r in data["board"]["releases"].get(PROD, []) if r.get("released") and r.get("date")],
        key=lambda r: r["date"]))

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
    tpl = (SKILL / "template.html").read_text(encoding="utf-8")
    page = tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False)).replace("__PRODUCT__", product["name"])
    out = Path(args.out).resolve() if args.out else data_file.with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    print("Built %s: %d areas, %d rows (%d not on the dashboard), %d pins, %d releases, %d clarification pages · tracker: %s" % (
        out.name, sum(len(g["areas"]) for g in groups), len(rows_by_id),
        sum(1 for f in rows_by_id.values() if f["origin"] != "dashboard"), len(pins), len(releases), len(pages), tracker.name))


if __name__ == "__main__":
    main()
