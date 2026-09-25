"""Turn the slide files into one printable HTML page (one 1920x1080 page per slide), then print it to PDF."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
order = json.load(open(os.path.join(ROOT, "project", "deck.json"), encoding="utf-8"))["order"]


def style_of(tag):
    m = re.search(r'style="([^"]*)"', tag)
    return m.group(1) if m else ""


def prop(style, name, default=""):
    m = re.search(rf'(?:^|;)\s*{name}\s*:\s*([^;]+)', style)
    return m.group(1).strip() if m else default


def arrow(m):
    s = style_of(m.group(0))
    w, h, c = prop(s, "width", "60px"), prop(s, "height", "24px"), prop(s, "background", "#999")
    return (f'<svg style="{s}; background:none; flex:none" viewBox="0 0 100 40" preserveAspectRatio="none">'
            f'<path d="M0 13 H60 V0 L100 20 L60 40 V27 H0 Z" fill="{c}"/></svg>')


def icon(m):
    s = style_of(m.group(0))
    c = prop(s, "color", "#0F9D76")
    return (f'<svg style="{s}; flex:none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="{c}"/>'
            f'<path d="M6.5 12.5l3.5 3.5 7.5-8" stroke="#fff" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>')


pages = []
for sid in order:
    html = open(os.path.join(ROOT, "project", "slides", f"{sid}.html"), encoding="utf-8").read()
    html = re.sub(r"<aside>.*?</aside>", "", html, flags=re.S)
    html = re.sub(r'<x-shape kind="arrow-right"[^>]*></x-shape>', arrow, html)
    html = re.sub(r'<x-icon[^>]*></x-icon>', icon, html)
    pages.append(html)

doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Our BA approach — a guide for BAs</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
  @page {{ size: 1920px 1080px; margin: 0 }}
  * {{ margin: 0; padding: 0; box-sizing: border-box }}
  html, body {{ background: #F6F4EF; -webkit-print-color-adjust: exact; print-color-adjust: exact }}
  section {{ width: 1920px; height: 1080px; position: relative; overflow: hidden; break-after: page }}
  section:last-child {{ break-after: auto }}
  p {{ line-height: 1.4 }} h1 {{ line-height: 1.1 }} h2 {{ line-height: 1.15 }}
</style></head><body>
{''.join(pages)}
</body></html>"""
out_html = os.path.join(ROOT, "our-ba-approach.html")
open(out_html, "w", encoding="utf-8", newline="\n").write(doc)

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
out_pdf = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "our-ba-approach.pdf")
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                f"--print-to-pdf={out_pdf}", "file:///" + out_html.replace("\\", "/")], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(out_pdf, os.path.getsize(out_pdf), "bytes")
