#!/usr/bin/env python3
"""Build a client clarification page from a YAML input file.

    python _generate.py scorecard-decisions.yaml

Writes <slug>.html beside the input. Publish that file as an artifact with the SAME
path each round, so the URL — and therefore the dashboard link — never changes.

Why a YAML input rather than reading the spec's Open section: the internal question
("Which record levels actually ship?") is not the client question ("Should notes be on
customers only, or also on applications and loans?"), and every option has to carry its
consequence. That rewrite is judgement, not transformation. Each question keeps a
`spec_ref` so answers can be routed back to the spec later.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import mimetypes
import pathlib
import re
import sys

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("error: pyyaml is required — `uv run --with pyyaml _generate.py <input.yaml>`")

HERE = pathlib.Path(__file__).parent
TEMPLATE = HERE / "_template.html"

# ── helpers ──────────────────────────────────────────────────────────────────

def esc(s: object) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def esc_ascii(s: object) -> str:
    """Escape, then push anything non-ASCII out as a numeric character reference.

    Figma frame names carry characters like the middot in `v14 · Release from probate`.
    Written raw they depend on a charset declaration, and these pages do not carry one —
    the artifact wrapper supplies it, so the file renders correctly when published and as
    mojibake when served any other way. Encoding them makes the output charset-proof, and
    matches the template, which is entities throughout.
    """
    return esc(s).encode("ascii", "xmlcharrefreplace").decode("ascii")


SCREEN_WIDTH = 1200   # plenty for a 1440 staff frame read on a laptop
SCREEN_QUALITY = 80


def data_uri(path: pathlib.Path) -> str:
    """Embed an image so the page is one self-contained file.

    The artifact sandbox blocks external image hosts, so a data URI (or the artifact's
    own asset store) is the only way to get a picture onto one of these pages. That makes
    page weight a real constraint: a raw 1440px PNG export is ~135 KB, which is ~180 KB
    once base64'd, against a 32 KB page. So downscale to SCREEN_WIDTH and re-encode as
    WebP first — the same three probate frames go from 281 KB of PNG to 84 KB of WebP.
    Keep the full-resolution PNG in screens/ as the source; only the page gets the small one.
    """
    if not path.is_file():
        sys.exit(f"error: screen image not found: {path}")
    try:
        from PIL import Image
    except ModuleNotFoundError:
        # Without Pillow the page still builds, just heavy. Say so rather than failing.
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        kb = path.stat().st_size * 4 / 3 / 1024
        print(f"  warning: Pillow not installed, embedding {path.name} at full size "
              f"(~{kb:.0f} KB of base64). `uv run --with pyyaml --with pillow` to shrink it.")
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    import io
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w > SCREEN_WIDTH:
        im = im.resize((SCREEN_WIDTH, round(h * SCREEN_WIDTH / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=SCREEN_QUALITY, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def figma_url(file_key: str, node: str) -> str:
    """A node id in a Figma URL uses a hyphen, not the colon the API reports."""
    return (f"https://www.figma.com/design/{file_key}/"
            f"?node-id={str(node).replace(':', '-')}")


ENTITY = re.compile(r"&(?:[a-zA-Z]+|#\d+);")


def plain(value: str, field: str, where: str) -> str:
    """These fields are escaped by the page's JS, so an HTML entity in one renders
    literally as `&mdash;`. Catch it here rather than in a screenshot."""
    if isinstance(value, str) and ENTITY.search(value):
        sys.exit(f"error: {where} field '{field}' contains an HTML entity "
                 f"({ENTITY.search(value).group(0)}). This field is rendered as text — "
                 f"use the character itself.")
    return value


def require(d: dict, key: str, where: str):
    if key not in d or d[key] in (None, ""):
        sys.exit(f"error: {where} is missing required field '{key}'")
    return d[key]


# ── rendering ────────────────────────────────────────────────────────────────

STAGES = {"concept": "Concept", "spec": "Spec & design", "ready": "Ready for dev",
          "dev": "In dev", "qa": "In QA", "done": "Done"}
SUMMARY_CAP = 700
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                       "august", "september", "october", "november", "december"], 1)}
FIGMA_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6 M20 4l-9 9 '
              'M18 14v5a1 1 0 0 1 -1 1h-12a1 1 0 0 1 -1 -1v-12a1 1 0 0 1 1 -1h5"/></svg>')


def figma_button(href: str) -> str:
    return (f'<a class="btn ghost small" href="{href}" target="_blank" rel="noopener">'
            f'{FIGMA_ICON}Open in Figma</a>')


def render_design(design: dict, base: pathlib.Path) -> str:
    """What the feature is, and what it looks like.

    The summary and ONE screen stay visible: a paragraph and a picture orient a reader who has
    never seen the feature. The rest of the gallery and the longer detail sit behind a
    disclosure. Every screen with a Figma node gets an "Open in Figma" button to that frame.
    This is a SURFACE, not the record, so the summary is capped.
    """
    if not design:
        return ""
    summary = require(design, "summary", "the design block")
    if len(summary) > SUMMARY_CAP:
        print(f"  warning: design.summary is {len(summary)} characters (soft cap {SUMMARY_CAP}).")

    file_key = design.get("figma_file")
    screens, hero, captured = [], None, []
    for i, s in enumerate(design.get("screens") or [], 1):
        where = f"design screen {i}"
        src_path = base / require(s, "src", where)
        stamp = _dt.date.fromtimestamp(src_path.stat().st_mtime).isoformat()
        captured.append({"file": src_path.name, "date": stamp,
                         "node": str(s.get("node") or "(no node id)"), "frame": str(s.get("frame") or "")})
        item = {"src": data_uri(src_path),
                "cap": esc_ascii(plain(s.get("cap", ""), "cap", where)),
                "frame": esc_ascii(plain(s.get("frame", ""), "frame", where))}
        if s.get("node") and file_key:
            item["href"] = figma_url(file_key, s["node"])
        if s.get("hero") and hero is None:
            hero = item
        else:
            screens.append(item)
    if hero is None and screens:
        hero = screens.pop(0)

    def figure(it: dict) -> str:
        link = figma_button(it["href"]) if it.get("href") else ""
        return (f'<figure><img src="{it["src"]}" alt="{it["cap"]}" loading="lazy">'
                f'<figcaption><span>{it["cap"]}</span>{link}</figcaption></figure>')

    label = design.get("label", "What it looks like")
    out = ['    <section class="card design">', f'      <h2>{esc_ascii(label)}</h2>',
           f'      <div class="design-sum">{summary}</div>']
    if hero:
        out.append("      " + figure(hero))
    panel = []
    if design.get("detail"):
        panel.append(f'<div class="design-detail">{design["detail"]}</div>')
    if design.get("figma_page") and file_key:
        panel.append('<p class="design-where">Every frame below lives on the Figma page '
                     f'<b>{esc_ascii(design["figma_page"])}</b>.</p>')
    panel += [figure(s) for s in screens]
    if panel:
        more = design.get("more_label", "More screens and detail")
        out += [f'      <button class="disc" id="dmore" type="button" aria-expanded="false" aria-controls="dpanel">'
                f'{esc_ascii(more)}<svg width="10" height="7" viewBox="0 0 10 7" fill="none" aria-hidden="true">'
                '<path d="M1 1.5 5 5.5 9 1.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
                'stroke-linejoin="round"/></svg></button>',
                '      <div class="dpanel" id="dpanel" hidden>', "\n".join("        " + p for p in panel), "      </div>"]
    out.append("    </section>")
    # Record where every image came from, inside the page itself, so it can be republished
    # without reading the old one back.
    if captured:
        rows = [f"     node {c['node']:<14} {c['frame'].replace('--', '-'):<44} {c['file']} (captured {c['date']})"
                for c in captured]
        out.insert(0, "\n".join(["<!-- DESIGN SCREENS - the Figma source of every image on this page.",
                                 f"     Figma file: {file_key or '(none)'}"] + rows +
                                ["     To refresh: re-pull each node through the Figma MCP into",
                                 "     screens/<file>, then re-run _generate.py.", "-->"]))
        print("  design screens: " + ", ".join(f"{c['file']} ({c['date']})" for c in captured))
    return "\n".join(out)


def render_problem_solution(cfg: dict) -> str:
    cards = [f'      <section class="card"><h2><span class="tag">{t}</span></h2><p>{cfg[k]}</p></section>'
             for k, t in (("problem", "Problem"), ("solution", "Solution")) if cfg.get(k)]
    return '    <div class="ps">\n' + "\n".join(cards) + "\n    </div>" if cards else ""


def guess_date(text: str, year: int):
    """Old `settled` entries carry their date in prose, e.g. "(13 October)"."""
    m = re.search(r"\b(\d{1,2})(?:\s+and\s+\d{1,2})?\s+(" + "|".join(MONTHS) + r")\b", text, re.I)
    return f"{year:04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}" if m else None


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in (("&mdash;", "—"), ("&ndash;", "–"), ("&middot;", "·"), ("&rarr;", "→"),
                 ("&amp;", "&"), ("&nbsp;", " "), ("&ldquo;", "“"), ("&rdquo;", "”"), ("&rsquo;", "’")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def build_decisions(cfg: dict) -> list:
    """`decisions:` is the new shape: id, date, who, how, title, detail. A page not yet converted
    still has the old `settled:` list of HTML lines; turn each into a decision without a person."""
    if cfg.get("decisions"):
        out = []
        for i, dc in enumerate(cfg["decisions"], 1):
            where = f"decision {i}"
            out.append({"id": require(dc, "id", where), "date": str(dc.get("date") or "") or None,
                        "who": plain(dc.get("who", ""), "who", where), "how": plain(dc.get("how", ""), "how", where),
                        "title": plain(require(dc, "title", where), "title", where),
                        "detail": plain(dc.get("detail", ""), "detail", where)})
        return out
    settled = cfg.get("settled") or []
    if isinstance(settled, str):
        settled = [settled]
    year = _dt.date.today().year
    out = []
    for i, line in enumerate(settled, 1):
        m = re.match(r"\s*<strong>(.*?)</strong>(.*)", line, re.S)
        title, detail = (strip_tags(m.group(1)), strip_tags(m.group(2))) if m else (strip_tags(line), "")
        if title.lower().startswith("already decided"):
            continue
        detail = detail.lstrip(".,;:— ").strip()
        out.append({"id": f"s{i}", "date": guess_date(line, year), "who": "", "how": "",
                    "title": title.rstrip("."), "detail": detail})
    return out


def load_stage(cfg: dict, base: pathlib.Path):
    """The feature's stage, from the same data as the mind map (docs/BA/mind-map/stages.json,
    keyed by the page's published URL), so the two always agree. `stage:` in the YAML wins."""
    if cfg.get("stage"):
        return cfg["stage"], None
    f = base.parent / "mind-map" / "stages.json"
    if cfg.get("url") and f.is_file():
        hit = json.loads(f.read_text(encoding="utf-8")).get(cfg["url"])
        if hit:
            return hit["stage"], hit
    return None, None


BACK_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6l6 6"/></svg>'


def render_back(cfg: dict, base: pathlib.Path) -> str:
    """A Back button to the mind map, opened on this page's feature (`<map link>#<feature id>`) — or, when
    the profile's tools.dashboard.timelines makes the Timelines the dashboard, to the product's Timeline.
    The map link and the feature id come from docs/BA/mind-map/stages.json. A page whose feature is
    not on the dashboard goes back to the map itself; with no map at all, there is no button."""
    f = base.parent / "mind-map" / "stages.json"
    if not f.is_file():
        return ""
    data = json.loads(f.read_text(encoding="utf-8"))
    url = data.get("_mapUrl")
    if not url:
        return ""
    hit = data.get(cfg.get("url")) or {}
    if data.get("_backLabel"):  # the Timelines are the dashboard: back to this page's product Timeline
        href, label = hit.get("back") or url, data["_backLabel"]
    else:
        feature = hit.get("feature")
        href, label = url + ("#" + feature if feature else ""), "Back to the mind map"
    return (f'<a class="btn ghost back" href="{esc(href)}" target="_blank" rel="noopener">'
            f'{BACK_ICON}{esc(label)}</a>')


def build_questions(questions: list, base: pathlib.Path) -> list:
    """Normalise YAML questions into the shape the page's JS expects."""
    out = []
    for i, q in enumerate(questions, 1):
        where = f"question {i}"
        item = {
            "id": require(q, "id", where),
            "title": plain(require(q, "title", where), "title", where),
            "meta": plain(q.get("meta", ""), "meta", where),
            "body": require(q, "body", where),
            "note": plain(q.get("note", "Anything else we should know?"), "note", where),
            "notePlaceholder": plain(q.get("note_placeholder", "Optional — a sentence is plenty"),
                                     "note_placeholder", where),
            "options": [],
            "screens": [],
        }
        for key in ("section", "body2", "snag", "spec_ref"):
            if q.get(key):
                item[key] = plain(q[key], key, where) if key == "section" else q[key]
        if q.get("quote"):
            qt = q["quote"]
            item["quote"] = {"text": require(qt, "text", f"{where} quote"),
                             "cite": qt.get("cite", "")}
        for o in require(q, "options", where):
            opt = {"v": require(o, "v", f"{where} option"),
                   "t": plain(require(o, "t", f"{where} option"), "t", f"{where} option"),
                   "d": plain(o.get("d", ""), "d", f"{where} option")}
            if o.get("rec"):
                opt["rec"] = True
            item["options"].append(opt)
        for s in q.get("screens") or []:
            scr = {"src": data_uri(base / require(s, "src", f"{where} screen")),
                   "cap": plain(s.get("cap", ""), "cap", f"{where} screen")}
            if s.get("figma"):
                scr["figma"] = s["figma"]
            item["screens"].append(scr)
        out.append(item)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        return int(bool(sys.exit(__doc__)))
    inp = pathlib.Path(sys.argv[1]).resolve()
    if not inp.is_file():
        sys.exit(f"error: no such input file: {inp}")
    cfg = yaml.safe_load(inp.read_text(encoding="utf-8")) or {}
    base = inp.parent

    slug = require(cfg, "slug", "the input file")
    questions = build_questions(cfg.get("questions") or [], base)
    decisions = build_decisions(cfg)
    stage, stage_src = load_stage(cfg, base)

    events = []
    for i, ev in enumerate(cfg.get("events") or [], 1):
        where = f"event {i}"
        e = {"date": str(require(ev, "date", where)), "kind": ev.get("kind", "note"),
             "who": plain(ev.get("who", ""), "who", where), "title": plain(require(ev, "title", where), "title", where)}
        if e["kind"] == "stage":
            e["stage"] = require(ev, "stage", where)
        events.append(e)
    # The current stage from the mind map, if no event records it yet.
    last_stage = max((e for e in events if e["kind"] == "stage"), key=lambda e: e["date"], default=None)
    if not stage and last_stage:  # a page with no dashboard feature: its own latest stage event
        stage = last_stage["stage"]
    if stage and (not last_stage or last_stage["stage"] != stage):
        when = (stage_src or {}).get("since") or (stage_src or {}).get("asOf") or _dt.date.today().isoformat()
        events.append({"date": when, "kind": "stage", "stage": stage, "who": "",
                       "title": f"Now {STAGES.get(stage, stage)}" + (" (from Jira)" if stage_src and stage_src.get("fromJira") else "")})

    # Send writes into the artifact's own store; the BA's Claude session reads it back (`read_db`,
    # collection `answers`, doc `latest`). It only appears where the store is reachable. Copy is the
    # fallback. A page with nothing to answer and nothing to change keeps neither.
    actions = ['<button class="btn" id="send" type="button" hidden>Send answers</button>',
               '<button class="btn ghost" id="copy" type="button">Copy all answers</button>']
    if not questions and not decisions:
        actions = []

    name = cfg.get("name") or cfg.get("title") or slug
    pill = (f'<span class="pill s-{esc(stage)}"><span class="dot"></span>{esc_ascii(STAGES.get(stage, stage))}</span>'
            if stage else "")
    data = {"questions": questions, "decisions": decisions, "events": events, "stages": STAGES}

    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "{{DOC_TITLE}}":        esc(cfg.get("doc_title") or name),
        "{{CRUMB}}":            esc_ascii(name),
        "{{BACK}}":             render_back(cfg, base),
        "{{H1}}":               esc_ascii(name) if cfg.get("name") else require(cfg, "title", "the input file"),
        "{{DESCRIPTION}}":      cfg.get("description") or cfg.get("standfirst", ""),
        "{{STAGE_PILL}}":       pill,
        "{{ROUND}}":            esc_ascii(cfg["round"]) if cfg.get("round") else cfg.get("eyebrow", ""),
        "{{PROBLEM_SOLUTION}}": render_problem_solution(cfg),
        "{{DESIGN}}":           render_design(cfg.get("design") or {}, base),
        "{{ACTIONS}}":          "\n      ".join(actions),
        "{{DATA_JSON}}":        json.dumps(data, ensure_ascii=True).replace("</", "<\\/"),
        "{{STORE_KEY}}":        json.dumps(cfg.get("store_key") or f"{slug}-v1"),
        "{{DB_DOC}}":           json.dumps(slug),
        "{{COPY_HEADER}}":      json.dumps(cfg.get("copy_header") or name),
    }.items():
        html = html.replace(token, value)

    if re.search(r"\{\{[A-Z_]+\}\}", html):
        sys.exit("error: template still has unreplaced placeholders")

    out = base / f"{slug}.html"
    out.write_text(html, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"{out.name}  -  {len(questions)} questions, {len(decisions)} decisions, {len(events)} events, "
          f"stage {stage or '(none)'}, {kb:.0f} KB")
    if kb > 600:
        print(f"  warning: {kb:.0f} KB is heavy for a page the client opens on a phone.")
    print("publish to the same URL each round so the link does not change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
