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

def render_stages(stages: list, label: str) -> str:
    if not stages:
        return ""
    out = ['<section class="lifecycle">',
           f'  <p class="section-label">{esc_ascii(label)}</p>',
           '  <div class="stages">']
    for i, st in enumerate(stages, 1):
        hold = " hold" if st.get("hold") else ""
        out.append(f'    <div class="stage{hold}">')
        out.append(f'      <div class="stage-n">{i:02d}</div>')
        out.append(f'      <div class="stage-t">{esc_ascii(require(st, "title", "a stage"))}</div>')
        if st.get("detail"):
            out.append(f'      <p class="stage-d">{esc_ascii(st["detail"])}</p>')
        out.append("    </div>")
    out += ["  </div>", "</section>"]
    return "\n".join(out)


SUMMARY_CAP = 700


def render_design(design: dict, stages_html: str, base: pathlib.Path) -> str:
    """The opener: what the feature is, and what it looks like.

    Shape is deliberate. The summary and ONE screen stay visible, because a paragraph and
    a picture are what orient a reader who has never seen the feature, and hiding them
    behind a click defeats that. Everything that grows — the rest of the gallery, the
    longer detail, and the lifecycle strip — goes behind the disclosure.

    This is a SURFACE, not the record. The summary is capped so it cannot quietly become a
    second copy of the spec.
    """
    if not design:
        return ""

    summary = require(design, "summary", "the design block")
    if len(summary) > SUMMARY_CAP:
        print(f"  warning: design.summary is {len(summary)} characters (soft cap "
              f"{SUMMARY_CAP}). This block is an orientation, not a spec — the detail "
              f"belongs in the spec, and a long one here will rot against it.")

    file_key = design.get("figma_file")
    screens, hero, captured = [], None, []
    for i, s in enumerate(design.get("screens") or [], 1):
        where = f"design screen {i}"
        src_path = base / require(s, "src", where)
        # Report each screen's date rather than guessing at staleness. Comparing against
        # the YAML's own mtime looks clever and fires on every legitimate edit to the
        # prose, which trains you to ignore it.
        stamp = _dt.date.fromtimestamp(src_path.stat().st_mtime).isoformat()
        captured.append({
            "file": src_path.name,
            "date": stamp,
            "node": str(s.get("node") or "(no node id)"),
            "frame": str(s.get("frame") or ""),
        })
        item = {
            "src": data_uri(src_path),
            "cap": esc_ascii(plain(s.get("cap", ""), "cap", where)),
            "frame": esc_ascii(plain(s.get("frame", ""), "frame", where)),
        }
        if s.get("node") and file_key:
            item["href"] = figma_url(file_key, s["node"])
        if s.get("hero") and hero is None:
            hero = item
        else:
            screens.append(item)
    if hero is None and screens:
        hero = screens.pop(0)

    def figure(it: dict, cls: str = "") -> str:
        link = ""
        if it.get("href"):
            label = f'Open {it["frame"]} in Figma' if it["frame"] else "Open this frame in Figma"
            link = ('<span class="screen-link"><a href="' + it["href"] + '" target="_blank" '
                    'rel="noopener">' + label + ' &rarr;</a></span>')
        return (f'<figure class="{cls}"><div class="screen">'
                f'<img src="{it["src"]}" alt="{it["cap"]}" loading="lazy"></div>'
                f'<figcaption>{it["cap"]}{link}</figcaption></figure>')

    label = design.get("label", "What this feature is")
    out = ['<section class="design">',
           f'  <p class="section-label">{esc_ascii(label)}</p>',
           f'  <div class="design-sum">{summary}</div>']
    if hero:
        out.append("  " + figure(hero, "hero"))

    panel = []
    if design.get("detail"):
        panel.append(f'<div class="design-detail">{design["detail"]}</div>')
    if design.get("figma_page") and file_key:
        panel.append('<p class="design-where">Every frame below lives on the Figma page '
                     f'<b>{esc_ascii(design["figma_page"])}</b>.</p>')
    panel += [figure(s) for s in screens]
    if stages_html:
        panel.append(stages_html)

    if panel:
        more = design.get("more_label", "The rest of the design")
        out += [
            f'  <button class="disc" id="dmore" type="button" aria-expanded="false" '
            f'aria-controls="dpanel">{esc_ascii(more)}'
            '<svg class="caret" width="10" height="7" viewBox="0 0 10 7" fill="none" '
            'aria-hidden="true"><path d="M1 1.5 5 5.5 9 1.5" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>',
            '  <div class="dpanel" id="dpanel" hidden>',
            "\n".join("    " + p for p in panel),
            "  </div>",
        ]
    out.append("</section>")
    # Record where every image came from, inside the page itself. The published page is
    # then self-describing: the Figma file, the node, the frame name and the capture date
    # are recoverable from the artifact without opening this repo. That is what lets the
    # page be republished without reading the old one back first.
    if captured:
        rows = []
        for c in captured:
            # A double hyphen inside a comment would close it early, and a frame name is
            # free text, so strip any out of the parts that came from the YAML.
            frame = c["frame"].replace("--", "-")
            rows.append(f"     node {c['node']:<14} {frame:<44} {c['file']} "
                        f"(captured {c['date']})")
        note = ["<!-- DESIGN SCREENS - the Figma source of every image on this page.",
                f"     Figma file: {file_key or '(none)'}"] + rows + [
                "     To refresh: re-pull each node through the Figma MCP into",
                "     screens/<file>, then re-run _generate.py.",
                "-->"]
        out.insert(0, "\n".join(note))
        print("  design screens: " + ", ".join(
            f"{c['file']} ({c['date']})" for c in captured))
    return "\n".join(out)


def render_offline(settled) -> str:
    """`settled` is normally a prose block of author HTML. A list is also accepted."""
    if not settled:
        return ""
    inner = settled if isinstance(settled, str) else "<ul>" + "".join(
        f"<li>{s}</li>" for s in settled) + "</ul>"
    return f'<div class="offline on">{inner}</div>' 


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
    questions = build_questions(require(cfg, "questions", "the input file"), base)

    # The lifecycle strip is itself a high-level description. Where a `design:` block
    # exists it moves inside that block's disclosure, so the reader meets one context
    # section before the first question rather than three stacked ones.
    stages_html = render_stages(cfg.get("stages") or [],
                                cfg.get("stages_label", "Where this has got to"))
    design_html = render_design(cfg.get("design") or {}, stages_html, base)
    if design_html:
        stages_html = ""

    # No email action. Confirmed on the live pages 2026-09-10: these are published as
    # artifacts, and the artifact sandbox blocks the page from navigating the top-level
    # window — for a scripted `window.location.href = "mailto:..."` and for a plain anchor
    # alike. Both were tried and both were refused as a blocked connection. The answers go
    # back by clipboard: into Slack, which is already wired to /fetch-slack, or into an email
    # the reader composes themselves.
    # `Send to Claude` writes the answer set into the artifact's own store, which the BA's
    # Claude session then reads straight back (`read_db` on this artifact, collection
    # `answers`, doc `latest`). That is the whole point: on a client call the answers are
    # typed once and nothing is copied by hand afterwards. The button only appears where
    # the store is reachable — a local file has no `window.claude`, so it stays hidden and
    # the clipboard remains the route. Clipboard stays as the fallback either way.
    actions = ['<button class="btn btn-primary" id="send" type="button" hidden>Send answers to Claude</button>',
               '<button class="btn" id="copy" type="button">Copy all answers</button>',
               '<span class="toast" id="toast">Copied to clipboard</span>']

    # A page whose questions have all been answered and written into the spec keeps its
    # value as the record of what was decided. What it must not keep is the machinery for
    # answering: "0 of 0 answered" above two dead buttons reads as a broken page, not a
    # finished one.
    if not questions:
        actions = []

    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "{{DOC_TITLE}}":     esc(cfg.get("doc_title") or cfg.get("title") or slug),
        "{{EYEBROW}}":       cfg.get("eyebrow", ""),
        "{{H1}}":            require(cfg, "title", "the input file"),
        "{{STANDFIRST}}":    cfg.get("standfirst", ""),
        "{{DESIGN}}":        design_html,
        "{{STAGES}}":        stages_html,
        "{{COUNT_INIT}}":    (f"0 of {len(questions)} answered" if questions
                              else "Every question answered and recorded in the spec"),
        "{{CLOSE_H2}}":      cfg.get("close_title", "That is all of them"),
        "{{CLOSE_BODY}}":    cfg.get("close_body", ""),
        "{{OFFLINE}}":       render_offline(cfg.get("settled") or []),
        "{{ACTIONS}}":       "\n      ".join(actions),
        "{{QUESTIONS_JSON}}": json.dumps(questions, indent=2, ensure_ascii=True),
        # ensure_ascii keeps the page independent of a charset declaration. These
        # pages do not carry one - the artifact wrapper supplies it - so a raw em-dash
        # renders as mojibake anywhere else. — in a JS string literal does not.
        "{{STORE_KEY}}":     json.dumps(cfg.get("store_key") or f"{slug}-v1"),
        "{{DB_DOC}}":        json.dumps(slug),
        "{{COPY_HEADER}}":   json.dumps(cfg.get("copy_header") or cfg.get("title") or slug),
        "{{COPY_NOUN}}":     json.dumps(cfg.get("copy_noun", "questions")),
    }.items():
        html = html.replace(token, value)

    left = [t for t in ("{{", "}}") if t in html]
    if left:
        sys.exit("error: template still has unreplaced placeholders")

    out = base / f"{slug}.html"
    out.write_text(html, encoding="utf-8")
    kb = out.stat().st_size / 1024
    screens = sum(len(q["screens"]) for q in questions)
    design_screens = len((cfg.get("design") or {}).get("screens") or [])
    where = f"{screens} question screens, {design_screens} design screens"
    print(f"{out.name}  —  {len(questions)} questions, {where}, {kb:.0f} KB")
    if kb > 600:
        print(f"  warning: {kb:.0f} KB is heavy for a page the client opens on a phone. "
              f"Drop a screen, or lower SCREEN_WIDTH / SCREEN_QUALITY.")
    print(f"publish to the same path each round so the URL does not change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
