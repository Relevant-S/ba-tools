"""Build the BA dashboard page (Map + Board tabs) from docs/BA/dashboard.yaml, the clarification pages and Jira.

    uv run --with pyyaml python <skill>/map/build.py [--refresh] [--root <project>]

Run from the project root (or pass --root). Reads:
  - docs/BA/dashboard.yaml                       features, topics, and the awaiting / todos / agenda items
  - docs/BA/specs/.ba-profile.yml                products (Jira project -> product name), tools.dashboard
  - docs/BA/clarifications/*-decisions.yaml      answered-question counts and the spec path, matched by `url`
  - docs/BA/mind-map/{tickets,areas,releases}.json   the Jira files; --refresh rewrites them first
Writes docs/BA/mind-map/mind-map.html (the page to publish) and docs/BA/mind-map/stages.json (each
clarification page reads its stage and the map link from it).

--refresh needs node and the Jira variables JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN. The Jira scripts only read.

How the map is grouped (all from dashboard.yaml, nothing hand-made in here):
  - a feature row is a bubble; `id` names it (a slug of its title when missing);
  - a topic (`topics:` list: id, title, prod, jira_area) is a bubble for work with no feature row yet;
  - an awaiting / todo / agenda item sits under the feature or topic named by its `feature:` field,
    otherwise in "Not linked yet";
  - a bubble's area is the Jira component its tickets carry most; with no tickets, its `jira_area`;
    with neither, "No area". Its tickets are its `tickets:` list, else the keys written in its text.
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


root = Path(arg("--root", ".")).resolve()
ba = root / "docs/BA"
mm = ba / "mind-map"
mm.mkdir(parents=True, exist_ok=True)
d = yaml.safe_load(open(ba / "dashboard.yaml", encoding="utf-8"))
prof = yaml.safe_load(open(ba / "specs/.ba-profile.yml", encoding="utf-8"))
dash = (prof.get("tools") or {}).get("dashboard") or {}
mcfg = dash.get("map") or {}
today = date.fromisoformat(str(d["updated"]))

# Jira project -> product name as the dashboard writes it (`prod:`). tools.dashboard.map.products wins
# over the profile's product names, for when the dashboard spells a product differently.
PROJ = mcfg.get("products") or {p["jira_project"]: p["name"] for p in prof.get("products", []) if p.get("jira_project")}
if not PROJ:
    sys.exit("No Jira projects: set products[].jira_project (or tools.dashboard.map.products) in .ba-profile.yml")
MAP_URL = dash.get("url", "")
KEY_RE = re.compile(r"\b(?:%s)-\d+\b" % "|".join(map(re.escape, PROJ)))
SECTIONS = {"W": ("awaiting", "waiting"), "T": ("todos", "todo"), "A": ("agenda", "agenda")}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


# ---------- Jira files ----------
def refs():
    """Every Jira key the open dashboard entries mention, and which entries mention it."""
    keys = {}
    for sec, c in (("features", "F"), ("topics", "P"), ("awaiting", "W"), ("todos", "T"), ("agenda", "A")):
        for i, x in enumerate(d.get(sec) or []):
            if x.get("done"):
                continue
            for k in sorted(set(KEY_RE.findall(" ".join(str(v) for v in x.values())))):
                keys.setdefault(k, []).append(f"{c}{i}")
    return keys


if "--refresh" in sys.argv:
    (mm / "refs.json").write_text(json.dumps(refs(), indent=1), encoding="utf-8")
    projects = ",".join(PROJ)
    for cmd in (["node", str(HERE / "jira-tickets.mjs"), str(mm / "refs.json"), str(mm / "tickets.json")],
                ["node", str(HERE / "jira-areas.mjs"), str(mm / "areas.json"), projects],
                ["node", str(HERE / "jira-releases.mjs"), str(mm / "releases.json"), projects]):
        subprocess.run(cmd, check=True)


def load_json(name, empty):
    f = mm / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else empty


parents = load_json("tickets.json", {})
jira_areas = load_json("areas.json", [])
rel = load_json("releases.json", {"releases": [], "tickets": {}})

# ---------- Bubbles: features and topics ----------
clar_by_url = {}
for f in sorted((ba / "clarifications").glob("*-decisions.yaml")):
    c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if c.get("url"):
        clar_by_url[c["url"]] = c


def days(since):
    try:
        return (today - date.fromisoformat(str(since))).days
    except ValueError:
        return None


def item_key(kind, title):
    """A stable key for an item: the page saves notes under it, and sync.py finds the item by it.
    Built from the kind and title, not the list position, which shifts as items are added."""
    return hashlib.sha1(f"{kind}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


def item(code):
    sec, kind = SECTIONS[code[0]]
    x = d[sec][int(code[1:])]
    age = days(x.get("since"))
    status = "hot" if x.get("hot") else ("old" if age is not None and age > 30 else "open")
    return {"id": code, "key": item_key(kind, x["t"]), "kind": kind, "title": x["t"], "who": x.get("who", ""),
            "since": str(x.get("since", "")), "age": age, "status": status,
            "prod": x.get("prod", ""), "s": x.get("s", ""), "l": x.get("l", ""), "done": bool(x.get("done"))}


areas, by_id = [], {}
for fi, f in enumerate(d.get("features") or []):
    aid = f.get("id") or slug(f["area"])
    a = {"id": aid, "label": f.get("short") or f["area"], "children": [], "entry": f, "codes": [f"F{fi}"],
         "jira_area": f.get("jira_area")}
    open_qs = f.get("open") or []
    clar_url = (f.get("clar") or {}).get("url")
    c = clar_by_url.get(clar_url) or {}
    settled = None
    if isinstance(c.get("settled"), list):
        settled = len(c["settled"])
    elif isinstance(c.get("decisions"), list):
        settled = len(c["decisions"])
    a["spec_path"] = c.get("spec")
    a.update(stage=f["stage"], prod=f["prod"], hot=bool(f.get("hot")))
    a["feature"] = {"id": f"F{fi}", "kind": "feature", "title": f["area"], "who": f.get("who", ""),
                    "since": str(f.get("since", "")), "status": f["stage"], "prod": f["prod"],
                    "s": f.get("client_s") or f.get("s", ""), "open": open_qs, "settled": settled,
                    "clar": clar_url, "clarLabel": (f.get("clar") or {}).get("label")}
    areas.append(a)
    by_id[aid] = a
for pi, t in enumerate(d.get("topics") or []):
    a = {"id": t["id"], "label": t["title"], "children": [], "entry": t, "codes": [f"P{pi}"],
         "jira_area": t.get("jira_area"), "stage": None, "prod": t.get("prod")}
    areas.append(a)
    by_id[t["id"]] = a

rest = {"id": "unlinked", "label": "Loose items", "stage": None, "prod": "Both", "children": [], "entry": {}, "codes": []}
for c, (sec, _) in SECTIONS.items():
    for i, x in enumerate(d.get(sec) or []):
        a = by_id.get(x.get("feature"))
        if a is not None:
            a["children"].append(item(f"{c}{i}"))
        elif not x.get("done"):
            rest["children"].append(item(f"{c}{i}"))
areas.append(rest)  # gets its tickets and stage like any bubble, but no area and no board card
for a in areas:
    if not a.get("prod"):
        prods = {c["prod"] for c in a["children"]}
        a["prod"] = prods.pop() if len(prods) == 1 else "Both"

# ---------- Stages: the same six on every project ----------
# Concept (grey) -> Spec & design (purple) -> Ready for dev (blue) -> In dev (magenta) -> In QA (amber) -> Done (green).
# Jira status -> stage comes from tools.dashboard.map.stage_of_status. Statuses not listed fall back to
# Jira's own three status groups (To Do -> Ready for dev, In Progress -> In dev, Done -> Done).
STAGE_OF_STATUS = mcfg.get("stage_of_status") or {}
GROUP_STAGE = {"new": "ready", "indeterminate": "dev", "done": "done"}
FLOW = ["concept", "spec", "ready", "dev", "qa", "done"]
SPEC_READY = {"filed", "resolved"}


def spec_status(path):
    if not path or path.endswith("/") or not (root / path).is_file():
        return None
    m = re.search(r"^status:\s*'?([\w-]+)", (root / path).read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def ticket_stage(t):
    return STAGE_OF_STATUS.get(t["status"], GROUP_STAGE[t["category"]])


for a in areas:
    codes = set(a["codes"]) | {c["id"] for c in a["children"]}
    # A `tickets:` list wins over ticket keys picked up from the text. An empty list means "no tickets yet".
    entry = a["entry"]
    listed = set(entry["tickets"] or []) if "tickets" in entry else None
    a["tickets"] = sorted(({"key": k, "stage": None, **{f: v[f] for f in ("summary", "status", "category", "resolved", "parent", "components")}}
                           for k, v in parents.items() if (k in listed if listed is not None else codes & set(v["by"]))), key=lambda t: t["key"])
    for t in a["tickets"]:
        t["stage"] = ticket_stage(t)
    f, tk = a.get("feature"), a["tickets"]
    open_t = [t for t in tk if t["stage"] != "done"]
    a["specStatus"] = spec_status(a.get("spec_path"))
    answered = None
    if f and f["settled"] is not None and f["settled"] + len(f["open"]):
        answered = f["settled"] / (f["settled"] + len(f["open"]))
    a["answered"] = answered
    if open_t:
        # Not further than its slowest open ticket.
        a["stageKey"] = min((t["stage"] for t in open_t), key=FLOW.index)
    elif tk and not (f and f["status"] in ("spec", "design")):
        a["stageKey"] = "done"
    elif f and f["status"] == "dev":
        a["stageKey"] = "dev"
    elif f and f["status"] == "spec":
        a["stageKey"] = "ready" if a["specStatus"] in SPEC_READY else "spec"
    else:
        a["stageKey"] = "concept"
    # Tickets waiting at To Do do not make a feature Ready for dev while its spec is still being written:
    # Ready for dev means approved.
    if a["stageKey"] == "ready" and a["specStatus"] and a["specStatus"] not in SPEC_READY:
        a["stageKey"] = "spec"

# ---------- Areas: Jira components (they never close, unlike epics) ----------
PROD_KEY = {v: k for k, v in PROJ.items()}
FIRST = next(iter(PROJ))
recent_cut = str(date.fromordinal(today.toordinal() - 30))
placed = {}
for a in areas:
    if a is rest:
        continue
    prod_key = PROD_KEY.get(a["prod"], FIRST)
    own = [t for t in a["tickets"] if t["key"].startswith(prod_key + "-")] or a["tickets"]
    comps = Counter(c for t in own for c in t["components"])
    if comps:
        placed[a["id"]] = (own[0]["key"].split("-")[0], comps.most_common(1)[0][0], "from its tickets")
    elif a.get("jira_area"):
        placed[a["id"]] = (prod_key, a["jira_area"], "set on the dashboard")
    else:
        placed[a["id"]] = None
    a["areaHow"] = placed[a["id"]][2] if placed[a["id"]] else "no tickets and no area set"
    a["doneDate"] = max((t["resolved"] or "" for t in a["tickets"]), default="") or None if a["stageKey"] == "done" else None
epics = []
for j in jira_areas:
    feats = [a for a in areas if placed.get(a["id"]) and placed[a["id"]][:2] == (j["project"], j["name"])]
    stages = [ticket_stage(o) for o in j["open"]]
    in_flight = any(o["category"] == "indeterminate" for o in j["open"])
    own = (min(stages, key=FLOW.index) if stages else "done" if j["done"] else "concept")
    active = bool(feats) or in_flight or (j["lastDone"] or "") >= recent_cut
    epics.append({"id": f'{j["project"]}:{j["name"]}', "prod": PROJ.get(j["project"], j["project"]), "label": j["name"], "jira": j,
                  "features": feats, "active": active, "stage": own})
# A jira_area that Jira does not have (renamed, or the Jira files are missing) still shows, as its own area.
known = {(j["project"], j["name"]) for j in jira_areas}
for key in sorted({placed[a["id"]][:2] for a in areas if placed.get(a["id"])} - known):
    epics.append({"id": f"{key[0]}:{key[1]}", "prod": PROJ.get(key[0], key[0]), "label": key[1], "jira": None, "active": True,
                  "features": [a for a in areas if placed.get(a["id"]) and placed[a["id"]][:2] == key], "stage": "concept"})
epics.append({"id": "noarea", "prod": "Both", "label": "No area", "jira": None, "noarea": True, "active": True,
              "features": [a for a in areas if a is not rest and placed.get(a["id"]) is None], "stage": "concept"})
epics.append({"id": "unlinked", "prod": "Both", "label": "Not linked yet", "jira": None, "active": True, "loose": True,
              "features": [rest], "stage": "concept"})

# ---------- Board: rows are Jira releases, columns are areas, one card per feature ----------
# A card is a dashboard feature where the ticket belongs to one; otherwise the ticket's Jira epic;
# otherwise "Other tickets" in its area. A feature with tickets in two releases has a card in each.
# Tickets with no release, or in the release named "Backlog", go to the "Not planned yet" row, with
# the dashboard features that have no tickets yet.
NONE = "none"


def vnum(name):
    return [int(n) for n in re.findall(r"\d+", name.split(" - ")[0])] or [0]


releases = {}
for p, pname in PROJ.items():
    rs = [r for r in rel["releases"] if r["project"] == p and r["name"].lower() != "backlog"]
    upcoming = sorted((r for r in rs if not r["released"]), key=lambda r: vnum(r["name"]))
    shipped = sorted((r for r in rs if r["released"]), key=lambda r: (r["date"] or "", vnum(r["name"])), reverse=True)
    releases[pname] = [{"name": r["name"], "date": r["date"], "released": r["released"],
                        "overdue": bool(not r["released"] and r["date"] and r["date"] < str(today))} for r in upcoming + shipped]
feat_of = {t["key"]: a for a in areas if a is not rest for t in a["tickets"]}


def slim(k, t):
    return {"key": k, "summary": t["summary"], "status": t["status"], "stage": ticket_stage(t), "who": t.get("assignee")}


groups = {}


def put(row, gkey, base, tk):
    g = groups.setdefault((row, gkey), {**base, "row": row, "tickets": []})
    g["tickets"].append(tk)


for k, t in rel["tickets"].items():
    rows = [r for r in t["releases"] if r.lower() != "backlog"] or [NONE]
    a = feat_of.get(k)
    proj = PROJ.get(k.split("-")[0], k.split("-")[0])
    for row in rows:
        if a:
            put(row, ("F", a["id"]), {"kind": "feature", "fid": a["id"], "title": a["label"], "prod": a["prod"]}, slim(k, t))
        elif t["parent"]:
            put(row, ("E", t["parent"]), {"kind": "epic", "epic": t["parent"], "title": t["parentName"] or t["parent"],
                                          "prod": proj}, {**slim(k, t), "comps": t["components"]})
        else:
            comp = (t["components"] or ["No area"])[0]
            put(row, ("O", k.split("-")[0], comp), {"kind": "other", "title": "Other tickets", "area": comp, "prod": proj}, slim(k, t))
# Dashboard features: tickets Jira's release list did not return (done, no release), and features with no tickets.
for a in areas:
    if a is rest:
        continue
    seen = {x["key"] for (row, gk), g in groups.items() if gk == ("F", a["id"]) for x in g["tickets"]}
    base = {"kind": "feature", "fid": a["id"], "title": a["label"], "prod": a["prod"]}
    for t in a["tickets"]:
        if t["key"] not in seen and t["key"] not in rel["tickets"]:
            put(NONE, ("F", a["id"]), base, {"key": t["key"], "summary": t["summary"], "status": t["status"], "stage": t["stage"], "who": None})
    if not a["tickets"]:
        groups[(NONE, ("F", a["id"]))] = {**base, "row": NONE, "tickets": [], "stage": a["stageKey"]}
cards = []
for (row, gk), g in groups.items():
    tk = g["tickets"]
    a = by_id.get(g.get("fid"))
    if a:
        g["area"] = placed[a["id"]][1] if placed.get(a["id"]) else "No area"
    elif g["kind"] == "epic":
        comps = Counter(c for x in tk for c in x.pop("comps"))
        g["area"] = comps.most_common(1)[0][0] if comps else "No area"
    if "stage" not in g:
        open_t = [x["stage"] for x in tk if x["stage"] != "done"]
        g["stage"] = min(open_t, key=FLOW.index) if open_t else "done"
        if a and g["stage"] == "ready" and a["specStatus"] and a["specStatus"] not in SPEC_READY:
            g["stage"] = "spec"
    g["blocked"] = any(x["status"].lower() == "blocked" for x in tk)
    g["doneDate"] = max((parents.get(x["key"], {}).get("resolved") or rel["tickets"].get(x["key"], {}).get("resolved") or "" for x in tk), default="") or None
    g["id"] = "c" + hashlib.sha1(repr((row, gk)).encode()).hexdigest()[:10]
    tk.sort(key=lambda x: (FLOW.index(x["stage"]), x["key"]))
    cards.append(g)
board = {"releases": releases, "cards": cards,
         "areas": {PROJ[p]: [j["name"] for j in jira_areas if j["project"] == p] for p in PROJ}}

for a in areas:
    for k in ("spec_path", "codes", "entry", "jira_area"):
        a.pop(k, None)

# The clarification pages take their stage from here, keyed by the page's published link, so a page
# and the map always show the same stage.
stages_out = {}
for a in areas:
    f = a.get("feature")
    if f and f.get("clar"):
        stages_out[f["clar"]] = {"stage": a["stageKey"], "fromJira": bool(a["tickets"]),
                                 "since": a.get("doneDate"), "asOf": str(today), "feature": a["id"]}
# Where the clarification pages' Back button goes: the map, opened on the feature (#<feature id>).
stages_out["_mapUrl"] = MAP_URL
(mm / "stages.json").write_text(json.dumps(stages_out, indent=1), encoding="utf-8")

data = {"updated": str(today), "title": d.get("title", "BA Dashboard"), "products": list(PROJ.values()),
        "mapUrl": MAP_URL, "epics": epics, "board": board}
tpl = (HERE / "template.html").read_text(encoding="utf-8")
html = tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
(mm / "mind-map.html").write_text(html, encoding="utf-8")
print(json.dumps({"ok": True, "page": str(mm / "mind-map.html"), "areas": len(epics),
                  "active": sum(e["active"] for e in epics), "bubbles": len(areas) - 1,
                  "items": sum(len(a["children"]) for a in areas), "not_linked": len(rest["children"]),
                  "jira_files": bool(parents or jira_areas)}))
