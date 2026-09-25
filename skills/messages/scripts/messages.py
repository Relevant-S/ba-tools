"""messages helper — the project's catalogue of every message the system sends by itself (email, in-app,
push, SMS). Data: docs/BA/messages.yaml. Page: docs/BA/messages.html. Every command prints one JSON line.

    uv run --with pyyaml python <skill>/scripts/messages.py <command> [--root <project>]

Commands:
  init --title "<name>" --products "A,B"   start an empty catalogue (refuses if one exists)
  next-id                                   the next free message id (M-001, M-002, …)
  add --item <file.yaml>                    add one message (gets the next id when it has none)
  set <id> --item <file.yaml>               replace fields of one message (only the fields in the file)
  build                                     messages.yaml → messages.html
  list                                      counts by channel, product and status
"""
import datetime as dt
import html
import json
import sys
from pathlib import Path

import yaml

CHANNELS = ("email", "in-app", "push", "sms")
STATUSES = ("live", "planned", "retired")
REQUIRED = {"name", "channel", "trigger", "recipients", "status"}


def out(obj):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))


def fail(msg):
    out({"ok": False, "error": msg})
    sys.exit(1)


def opt(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


ROOT = Path(opt("--root", ".")).resolve()
YML, HTML = ROOT / "docs/BA/messages.yaml", ROOT / "docs/BA/messages.html"


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))
HEAD = ("# Messages catalogue — every message the system sends by itself. The ba-tools `messages` skill builds\n"
        "# docs/BA/messages.html from it. One entry per message; a spec names a message by its id ([msg: M-012]).\n\n")


def load():
    if not YML.exists():
        fail(f"{YML} not found — run `init` first")
    d = yaml.safe_load(YML.read_text(encoding="utf-8")) or {}
    d.setdefault("messages", [])
    return d


def save(d):
    d["updated"] = dt.date.today().isoformat()
    with open(YML, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEAD + yaml.dump(d, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=110))


def next_id(d):
    nums = [int(m["id"].split("-")[1]) for m in d["messages"] if str(m.get("id", "")).startswith("M-")]
    return f"M-{(max(nums) if nums else 0) + 1:03d}"


def validate(m):
    miss = REQUIRED - set(m)
    if miss:
        return f"{m.get('id', '?')} is missing {sorted(miss)}"
    if m["channel"] not in CHANNELS:
        return f"{m.get('id')} channel must be one of {CHANNELS}"
    if m["status"] not in STATUSES:
        return f"{m.get('id')} status must be one of {STATUSES}"
    return ""


def read_item(p):
    p = Path(p or fail("--item <file.yaml> is required"))
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else fail(f"{p} not found")


def cmd_init():
    if YML.exists():
        fail(f"{YML} already exists")
    YML.parent.mkdir(parents=True, exist_ok=True)
    save({"title": opt("--title", "Messages catalogue"), "updated": "",
          "products": [p.strip() for p in (opt("--products", "") or "").split(",") if p.strip()], "messages": []})
    out({"ok": True, "created": str(YML)})


def cmd_add():
    d, m = load(), read_item(opt("--item"))
    m.setdefault("id", next_id(d))
    if any(x["id"] == m["id"] for x in d["messages"]):
        fail(f"{m['id']} already exists — use `set`")
    err = validate(m)
    if err:
        fail(err)
    d["messages"].append(m)
    save(d)
    out({"ok": True, "added": m["id"], "name": m["name"]})


def cmd_set(mid):
    d, patch = load(), read_item(opt("--item"))
    hit = [m for m in d["messages"] if m["id"] == mid]
    if not hit:
        fail(f"no message {mid}")
    hit[0].update(patch)
    err = validate(hit[0])
    if err:
        fail(err)
    save(d)
    out({"ok": True, "updated": mid})


def cmd_build():
    d = load()
    errs = [e for e in (validate(m) for m in d["messages"]) if e]
    if errs:
        fail("; ".join(errs))
    e = lambda v: html.escape(str(v or ""))
    rows = []
    for m in sorted(d["messages"], key=lambda m: m["id"]):
        body = e(m.get("content", "")).replace("\n", "<br>")
        rows.append(
            f'<article class="msg" data-channel="{e(m["channel"])}" data-product="{e(m.get("product", ""))}" data-status="{e(m["status"])}">'
            f'<div class="top"><span class="id">{e(m["id"])}</span><span class="pill ch-{e(m["channel"])}">{e(m["channel"])}</span>'
            f'<span class="pill st-{e(m["status"])}">{e(m["status"])}</span><span class="prod">{e(m.get("product", ""))}</span></div>'
            f'<h3>{e(m["name"])}</h3>'
            + (f'<p class="subj"><b>Subject</b> {e(m["subject"])}</p>' if m.get("subject") else "")
            + f'<dl><dt>Sent when</dt><dd>{e(m["trigger"])}</dd><dt>To</dt><dd>{e(m["recipients"])}</dd>'
            + (f'<dt>Only if</dt><dd>{e(m["conditions"])}</dd>' if m.get("conditions") else "")
            + (f'<dt>Spec</dt><dd>{e(m["spec"])}</dd>' if m.get("spec") else "")
            + (f'<dt>In the code</dt><dd class="mono">{e(m["source"])}</dd>' if m.get("source") else "")
            + "</dl>"
            + (f'<details><summary>What it says</summary><p class="body">{body}</p></details>' if body else "")
            + "</article>")
    counts = {c: sum(1 for m in d["messages"] if m["channel"] == c) for c in CHANNELS}
    prods = sorted({m.get("product", "") for m in d["messages"] if m.get("product")})
    chips = lambda group, vals: "".join(f'<button class="chip" data-{group}="{e(v)}" aria-pressed="false">{e(v)}</button>' for v in vals)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(d.get("title", "Messages catalogue"))}</title>
<style>
:root{{--bg:#f4f5f2;--card:#fff;--ink:#16211f;--ink2:#46524f;--ink3:#6b7775;--rule:#dde2df;--acc:#0d5b60;--acc-bg:#e3eeee;--warn:#8a5a06;--warn-bg:#f7ecd8;--off:#8b4545;--off-bg:#f5e4e4}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0e1413;--card:#161f1e;--ink:#e7eeec;--ink2:#b0bcba;--ink3:#80908d;--rule:#2a3634;--acc:#62c3c4;--acc-bg:#15302f;--warn:#e0a44e;--warn-bg:#33260f;--off:#ee9a9a;--off-bg:#361c1c}}}}
:root[data-theme=dark]{{--bg:#0e1413;--card:#161f1e;--ink:#e7eeec;--ink2:#b0bcba;--ink3:#80908d;--rule:#2a3634;--acc:#62c3c4;--acc-bg:#15302f;--warn:#e0a44e;--warn-bg:#33260f;--off:#ee9a9a;--off-bg:#361c1c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif}}
.wrap{{max-width:1040px;margin:0 auto;padding:32px 16px 64px}}h1{{margin:0;font-size:26px}}.lede{{color:var(--ink2);max-width:70ch}}
.counts{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}}.count{{background:var(--card);border:1px solid var(--rule);padding:10px 14px}}.count b{{display:block;font-size:22px}}
.bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}}.bar span{{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink3);min-width:70px}}
.chip{{background:var(--card);color:var(--ink2);border:1px solid var(--rule);padding:5px 11px;font:inherit;font-size:13px;cursor:pointer}}.chip[aria-pressed=true]{{background:var(--acc);border-color:var(--acc);color:var(--card)}}
input[type=search]{{width:100%;max-width:420px;padding:8px 10px;border:1px solid var(--rule);background:var(--card);color:var(--ink);font:inherit}}
.msg{{background:var(--card);border:1px solid var(--rule);padding:16px 18px;margin-top:10px}}.top{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:13px}}
.id{{font-family:ui-monospace,Menlo,monospace;font-weight:600}}.pill{{padding:1px 8px;background:var(--acc-bg);color:var(--acc)}}.st-planned{{background:var(--warn-bg);color:var(--warn)}}.st-retired{{background:var(--off-bg);color:var(--off)}}.prod{{color:var(--ink3)}}
h3{{margin:8px 0 4px;font-size:17px}}.subj{{margin:0 0 6px}}dl{{display:grid;grid-template-columns:110px 1fr;gap:2px 12px;margin:6px 0}}dt{{color:var(--ink3)}}dd{{margin:0}}.mono{{font-family:ui-monospace,Menlo,monospace;font-size:13px;overflow-wrap:anywhere}}
details summary{{cursor:pointer;color:var(--acc)}}.body{{color:var(--ink2);border-left:3px solid var(--rule);padding-left:12px}}.empty{{color:var(--ink3);padding:20px 0}}
@media (max-width:560px){{dl{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>{e(d.get("title", "Messages catalogue"))}</h1>
<p class="lede">Every message the system sends by itself — what fires it, who gets it, and what it says. Updated {e(d.get("updated", ""))}. Built from <code>docs/BA/messages.yaml</code>; a spec names a message by its id.</p>
<div class="counts">{"".join(f'<div class="count"><b>{n}</b>{c}</div>' for c, n in counts.items())}<div class="count"><b>{len(d["messages"])}</b>in total</div></div>
<div class="bar"><span>Channel</span>{chips("channel", CHANNELS)}</div>
<div class="bar"><span>Product</span>{chips("product", prods)}</div>
<div class="bar"><span>Status</span>{chips("status", STATUSES)}</div>
<div class="bar"><input type="search" id="q" placeholder="Search names, triggers, subjects…" aria-label="Search messages"></div>
<div id="list">{"".join(rows) or '<p class="empty">No messages yet.</p>'}</div>
</div>
<script>
const on={{channel:null,product:null,status:null}};
function paint(){{const q=document.getElementById('q').value.toLowerCase();
 document.querySelectorAll('.msg').forEach(m=>{{const ok=Object.entries(on).every(([k,v])=>!v||m.dataset[k]===v)&&(!q||m.textContent.toLowerCase().includes(q));m.hidden=!ok;}});}}
document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{{const [k]=Object.keys(b.dataset);const v=b.dataset[k];
 on[k]=on[k]===v?null:v;document.querySelectorAll(`.chip[data-${{k}}]`).forEach(c=>c.setAttribute('aria-pressed',String(on[k]===c.dataset[k])));paint();}}));
document.getElementById('q').addEventListener('input',paint);
</script></body></html>"""
    with open(HTML, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    out({"ok": True, "built": str(HTML), "messages": len(d["messages"]), "by_channel": counts})


def cmd_list():
    d = load()
    by = lambda k: {v: sum(1 for m in d["messages"] if m.get(k) == v) for v in sorted({m.get(k) for m in d["messages"]})}
    out({"ok": True, "total": len(d["messages"]), "channel": by("channel"), "product": by("product"), "status": by("status")})


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    if c == "init": cmd_init()
    elif c == "next-id": out({"ok": True, "next": next_id(load())})
    elif c == "add": cmd_add()
    elif c == "set": cmd_set(sys.argv[2] if len(sys.argv) > 2 else "")
    elif c == "build": cmd_build()
    elif c == "list": cmd_list()
    else: print(__doc__)
