"""ba-dashboard helper — the dashboard's data lives in docs/BA/dashboard.yaml; this builds the page from it
and makes the small, safe edits other skills need. Every command prints one JSON line.

    uv run --with pyyaml python <skill>/scripts/dashboard.py <command> [options]

Commands (run from the project root, or pass --root):
  build                                   docs/BA/dashboard.yaml  →  docs/BA/dashboard.html
  init --title "<name>" --products "A,B"  start an empty dashboard.yaml (refuses if one exists)
  add <awaiting|todos|agenda> --item <file.yaml>
                                          append one item (an awaiting item gets the next § number)
  close <awaiting|todos|agenda> --n <N> | --title "<exact title>"
                                          mark an item answered (it stays, struck through)
  set-clar --feature "<area>" --url <link> --label "<label>" [--open <file.yaml>] [--new <file.yaml>]
                                          point a feature row at its clarification page, and optionally
                                          replace its open-question list; --new creates the row if missing
  list                                    counts, and every feature with its clarification link
  slack-plan                              the client copy in Slack: which List rows to create, change or
                                          close, compared with docs/BA/dashboard-slack.yaml
  slack-ack --file <results.json>         record the Slack list ids / row ids after the rows were written
"""
import datetime as dt
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL / "assets/template.html"
LISTS = ("awaiting", "todos", "agenda")
ITEM_KEYS = {"prod", "who", "since", "t"}          # required on every awaiting / todo / agenda item
FEATURE_KEYS = {"area", "prod", "stage", "who", "since", "s"}
STAGES = {"design", "spec", "dev"}


def out(obj):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))


def fail(msg):
    out({"ok": False, "error": msg})
    sys.exit(1)


def args_after(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


ROOT = Path(args_after("--root", ".")).resolve()
YML = ROOT / "docs/BA/dashboard.yaml"
HTML = ROOT / "docs/BA/dashboard.html"
SLACK = ROOT / "docs/BA/dashboard-slack.yaml"


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
HEAD = ("# BA dashboard data — the only place to edit the dashboard. The ba-dashboard skill builds\n"
        "# docs/BA/dashboard.html from it and publishes it to the link in the project profile\n"
        "# (tools.dashboard.url). Lists: features (one row per feature, with its clarification page),\n"
        "# topics (work with no feature row yet), awaiting (parked on someone else), todos (on the BA),\n"
        "# agenda (for the next client call). An item's `feature:` names the feature or topic it sits under on the map.\n\n")


def load():
    if not YML.exists():
        fail(f"{YML} not found — run `init` first")
    d = yaml.safe_load(YML.read_text(encoding="utf-8")) or {}
    for k in ("features",) + LISTS:
        d.setdefault(k, [])
    return d


def save(d):
    d["updated"] = dt.date.today().isoformat()
    with open(YML, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEAD + yaml.dump(d, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=110))


def check(d):
    problems = []
    for name in LISTS:
        for i, it in enumerate(d[name]):
            miss = ITEM_KEYS - set(it)
            if miss:
                problems.append(f"{name}[{i}] '{it.get('t', '?')}' is missing {sorted(miss)}")
    # The map groups by id: a feature's `id` (else a slug of its title), a topic's `id`, an item's `feature`.
    ids = [f.get("id") or re.sub(r"[^a-z0-9]+", "-", str(f.get("area", "")).lower()).strip("-")[:40] for f in d["features"]]
    for i, t in enumerate(d.get("topics") or []):
        if not t.get("id") or not t.get("title"):
            problems.append(f"topics[{i}] needs an id and a title")
        ids.append(t.get("id"))
    for x in sorted({x for x in ids if ids.count(x) > 1}):
        problems.append(f"the id '{x}' is used twice (features / topics)")
    for name in LISTS:
        for i, it in enumerate(d[name]):
            if it.get("feature") and it["feature"] not in ids:
                problems.append(f"{name}[{i}] '{it.get('t', '?')}' names feature '{it['feature']}', which no feature or topic has")
    for i, f in enumerate(d["features"]):
        miss = FEATURE_KEYS - set(f)
        if miss:
            problems.append(f"features[{i}] '{f.get('area', '?')}' is missing {sorted(miss)}")
        if f.get("stage") not in STAGES:
            problems.append(f"features[{i}] '{f.get('area', '?')}' stage must be one of {sorted(STAGES)}")
        f.setdefault("open", [])
        f.setdefault("clar", None)
        f.setdefault("refs", "")
    for name in LISTS + ("features",):
        for it in d[name]:
            it["since"] = str(it.get("since", ""))
    return problems


def cmd_build():
    d = load()
    problems = check(d)
    if problems:
        fail("; ".join(problems))
    data = {k: d[k] for k in ("features",) + LISTS}
    data["products"] = d.get("products") or sorted({i.get("prod") for k in data for i in data[k] if i.get("prod") not in (None, "Both")})
    # </script> inside the data would end the script block early
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("{{TITLE}}", html.escape(d.get("title", "BA Dashboard")))
            .replace("{{UPDATED}}", html.escape(str(d.get("updated", dt.date.today().isoformat()))))
            .replace("{{LEDE}}", d.get("lede", ""))
            .replace("{{AGENDA_NOTE}}", f'<div class="note">{d["agenda_note"]}</div>' if d.get("agenda_note") else "")
            .replace("{{FOOTER}}", d.get("footer") or "<p>Built from <code>docs/BA/dashboard.yaml</code> by the ba-dashboard skill.</p>")
            .replace("{{DATA}}", blob))
    with open(HTML, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    out({"ok": True, "built": str(HTML), "bytes": len(page.encode()),
         "counts": {k: len(d[k]) for k in ("features",) + LISTS}})


def cmd_init():
    if YML.exists():
        fail(f"{YML} already exists")
    title = args_after("--title", "BA Dashboard")
    prods = [p.strip() for p in (args_after("--products", "") or "").split(",") if p.strip()]
    YML.parent.mkdir(parents=True, exist_ok=True)
    save({"title": title, "updated": "", "products": prods,
          "lede": "Everything open on the BA side. Parked items are indexed by the person who owes the answer.",
          "agenda_note": "", "footer": "", "features": [], "topics": [], "awaiting": [], "todos": [], "agenda": []})
    out({"ok": True, "created": str(YML)})


def read_item(path):
    p = Path(path)
    if not p.exists():
        fail(f"{p} not found")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def cmd_add(name):
    if name not in LISTS:
        fail(f"list must be one of {LISTS}")
    d = load()
    it = read_item(args_after("--item") or fail("--item <file.yaml> is required"))
    miss = ITEM_KEYS - set(it)
    if miss:
        fail(f"item is missing {sorted(miss)}")
    first_line = it["t"].strip().lower()
    if any(x.get("t", "").strip().lower() == first_line for x in d[name]):
        out({"ok": True, "skipped": "an item with this title is already there", "title": it["t"]}); return
    if name == "awaiting" and "n" not in it:
        it["n"] = max([x.get("n", 0) for x in d["awaiting"]] or [0]) + 1
    d[name].append(it)
    save(d)
    out({"ok": True, "added": name, "title": it["t"], "n": it.get("n")})


def cmd_close(name):
    d = load()
    n, title = args_after("--n"), args_after("--title")
    hits = [x for x in d.get(name, []) if (n and str(x.get("n")) == n) or (title and x.get("t") == title)]
    if len(hits) != 1:
        fail(f"found {len(hits)} matching items in {name} — give an exact --n or --title")
    hits[0]["done"] = True
    save(d)
    out({"ok": True, "closed": hits[0]["t"]})


def cmd_set_clar():
    d = load()
    area, url, label = args_after("--feature"), args_after("--url"), args_after("--label")
    if not (area and url and label):
        fail("--feature, --url and --label are required")
    rows = [f for f in d["features"] if f.get("area", "").strip().lower() == area.strip().lower()]
    if not rows:
        new = args_after("--new")
        if not new:
            fail(f"no feature row called '{area}' — pass --new <file.yaml> with area, prod, stage, who, since, s")
        f = read_item(new)
        miss = FEATURE_KEYS - set(f)
        if miss:
            fail(f"new feature is missing {sorted(miss)}")
        d["features"].append(f)
        rows = [f]
    f = rows[0]
    f["clar"] = {"url": url, "label": label}
    if args_after("--open"):
        f["open"] = read_item(args_after("--open"))
    save(d)
    out({"ok": True, "feature": f["area"], "clar": f["clar"], "open_questions": len(f.get("open", []))})


def cmd_list():
    d = load()
    out({"ok": True, "counts": {k: len(d[k]) for k in ("features",) + LISTS},
         "features": [{"area": f.get("area"), "stage": f.get("stage"), "open": len(f.get("open", [])),
                       "clarification_page": (f.get("clar") or {}).get("url")} for f in d["features"]]})


# --- the client copy in Slack -------------------------------------------------------------------------
# Two Slack Lists, written through the Slack connector: features in flight, and items waiting on the
# client. The script only decides what to write; the agent writes it and hands the row ids back (slack-ack).
STAGE_LABEL = {"design": "Design", "spec": "Spec", "dev": "In development"}
SLACK_HEAD = ("# The client copy of the BA dashboard, in Slack — two Slack Lists built from docs/BA/dashboard.yaml by\n"
              "# `dashboard.py slack-plan`. The BA's own page stays the full view; these lists show the client only the\n"
              "# features in flight and the items waiting on the client's side. Row ids below are written by slack-ack.\n"
              "# client_owners: an awaiting item goes to Slack when the FIRST person named in its `who` matches one.\n\n")


def plain(s):
    # Line breaks stay, so bullet lists in the dashboard text reach Slack as lists.
    text = re.sub(r"<[^>]+>", "", html.unescape(s or ""))
    return "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.strip().splitlines())


def slack_state():
    if not SLACK.exists():
        fail(f"{SLACK} not found — it holds the Slack lists and the client-owner names")
    st = yaml.safe_load(SLACK.read_text(encoding="utf-8")) or {}
    st.setdefault("lists", {}).setdefault("features", {}).setdefault("rows", {})
    st["lists"].setdefault("waiting", {}).setdefault("rows", {})
    return st


def is_client_owner(who, owners):
    first = re.split(r",| then | via |\+", who or "")[0].strip().lower()
    return any(o.lower() in first for o in owners)


def slack_rows(d, st):
    feats = {}
    for f in d["features"]:
        if f.get("client") is False:
            continue
        feats[f["area"]] = {"Feature": plain(f["area"]), "Product": f["prod"], "Stage": STAGE_LABEL[f["stage"]],
                            "With": plain(f["who"]), "Since": str(f["since"]),
                            "Where it stands": plain(f.get("client_s") or f["s"]),
                            "Open questions": "\n".join(f"• {plain(o)}" for o in f.get("open") or []) or "None"}
    wait = {}
    for a in d["awaiting"]:
        if a.get("client") is False or not is_client_owner(a["who"], st.get("client_owners", [])):
            continue
        if a.get("done") and str(a["n"]) not in st["lists"]["waiting"]["rows"]:
            continue                                  # answered before it ever reached Slack

        wait[str(a["n"])] = {"Question": plain(a["t"]), "Product": a["prod"], "Owner": plain(a["who"]),
                             "Waiting since": str(a["since"]),
                             "Where it stands": plain(a.get("client_s") or a.get("s")),
                             "Status": "Answered" if a.get("done") else "Partly answered" if a.get("part") else "Open"}
    return {"features": feats, "waiting": wait}


def digest(cols):
    return hashlib.sha1(json.dumps(cols, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def cmd_slack_plan():
    d, st = load(), slack_state()
    check(d)
    plan = {"ok": True, "lists": {}, "create": [], "update": [], "close": []}
    gone = {"features": {"Stage": "Done"}, "waiting": {"Status": "Closed"}}
    for name, rows in slack_rows(d, st).items():
        lst = st["lists"][name]
        plan["lists"][name] = {"id": lst.get("id"), "url": lst.get("url")}
        for key, cols in rows.items():
            have = lst["rows"].get(key)
            if not have:
                plan["create"].append({"list": name, "key": key, "columns": cols, "hash": digest(cols)})
            elif have.get("hash") != digest(cols):
                plan["update"].append({"list": name, "key": key, "record_id": have["record_id"],
                                       "columns": cols, "hash": digest(cols)})
        for key, have in lst["rows"].items():
            if key not in rows and not have.get("closed"):
                plan["close"].append({"list": name, "key": key, "record_id": have["record_id"], "columns": gone[name]})
    plan["counts"] = {k: len(plan[k]) for k in ("create", "update", "close")}
    out(plan)


def cmd_slack_ack():
    st = slack_state()
    res = json.loads(Path(args_after("--file") or fail("--file <results.json> is required")).read_text(encoding="utf-8"))
    for name, meta in (res.get("lists") or {}).items():
        st["lists"][name].update({k: v for k, v in meta.items() if v})
    for r in res.get("rows", []):
        row = st["lists"][r["list"]]["rows"].setdefault(r["key"], {})
        row["record_id"] = r["record_id"]
        if r.get("closed"):
            row["closed"] = True
        else:
            row["hash"] = r["hash"]
            row.pop("closed", None)
    st["synced"] = dt.date.today().isoformat()
    with open(SLACK, "w", encoding="utf-8", newline="\n") as f:
        f.write(SLACK_HEAD + yaml.dump(st, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=110))
    out({"ok": True, "rows": {k: len(v["rows"]) for k, v in st["lists"].items()}})


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    if c == "build": cmd_build()
    elif c == "init": cmd_init()
    elif c == "add": cmd_add(sys.argv[2] if len(sys.argv) > 2 else "")
    elif c == "close": cmd_close(sys.argv[2] if len(sys.argv) > 2 else "")
    elif c == "set-clar": cmd_set_clar()
    elif c == "list": cmd_list()
    elif c == "slack-plan": cmd_slack_plan()
    elif c == "slack-ack": cmd_slack_ack()
    else: print(__doc__)
