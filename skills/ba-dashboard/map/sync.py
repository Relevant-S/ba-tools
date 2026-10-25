"""Write the mind map's saved notes and "Resolved" ticks into docs/BA/dashboard.yaml.

    uv run --with pyyaml python <skill>/map/sync.py resolutions.json        (run from the project root)

`resolutions.json` is the mind map's `resolutions` collection, read with ArtifactData `list` (the
page's link, collection "resolutions") and saved as JSON: a list of documents, each either the
document body itself or {"id": ..., "data": {...}}. For every document whose item is still in the
dashboard:
  - each note goes to the front of the item's "where it stands" text (`s`) as "UPDATE <date> — <note>.",
    the last one as "CLOSED <date> — <note>." when the item is resolved;
  - a resolved item gets `done: true`, so the dashboard shows it struck through.
It saves with the ba-dashboard skill's own writer, so the file keeps its usual format, and prints
which keys were applied: delete exactly those documents from the page's store afterwards. A key it
cannot match (the item's title changed, or it is gone) is reported and left in the store.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("dashboard", Path(__file__).resolve().parent.parent / "scripts/dashboard.py")
argv, sys.argv = sys.argv, [sys.argv[0]]  # dashboard.py reads --root from argv when imported
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)
sys.argv = argv

LIST_OF = {"waiting": "awaiting", "todo": "todos", "agenda": "agenda"}


def item_key(kind, title):  # the same key as build.py's item_key
    return hashlib.sha1(f"{kind}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


def day(iso):
    d = dt.date.fromisoformat(str(iso)[:10])
    return f"{d.day} {d.strftime('%b').upper()}"


docs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
docs = [x.get("data", x) if isinstance(x, dict) else x for x in (docs.get("documents", docs) if isinstance(docs, dict) else docs)]
d = dashboard.load()
index = {}
for kind, name in LIST_OF.items():
    for it in d[name]:
        index[item_key(kind, it["t"])] = it

applied, missing = [], []
for doc in docs:
    it = index.get(doc.get("key"))
    if it is None:
        missing.append({"key": doc.get("key"), "title": doc.get("title")})
        continue
    notes = doc.get("notes") or []
    lines = []
    for i, n in enumerate(notes):
        last = i == len(notes) - 1
        word = "CLOSED" if doc.get("resolved") and last else "UPDATE"
        lines.append(f"{word} {day(n['at'])} — {n['text'].rstrip('.')}.")
    if doc.get("resolved") and not notes:
        lines.append(f"CLOSED {day(doc.get('updatedAt') or dt.date.today())}.")
    if lines:
        it["s"] = " ".join(reversed(lines)) + (" " + it["s"] if it.get("s") else "")
    if doc.get("resolved"):
        it["done"] = True
    applied.append({"key": doc["key"], "title": it["t"], "resolved": bool(doc.get("resolved")), "notes": len(notes)})

if applied:
    dashboard.save(d)
print(json.dumps({"ok": True, "applied": applied, "not_found": missing}, ensure_ascii=False, indent=1))
