"""Add "Page X of Y" to the footers of a generated-document template (.docx).

Result in each footer line:
    <Company> | Page 2 of 4 | <address> | <phone> | <web>
(e.g. "Acme Ltd. | Page 2 of 4 | 1 Example Street - Springfield | ...")

Why this exists: Google Docs saves page fields EMPTY, and LibreOffice on the
documents server then prints the numbers in a black serif font. This script
writes each field in Word's full form (begin / instrText / separate / a "1"
placeholder / end) and gives every run the footer's own font and colour, so
LibreOffice keeps the footer style.

NEVER open the result in Google Docs: that re-saves the file and strips the fix.
Put it onto Drive with Manage versions -> Upload new version.

Usage:
    python -I add_page_numbers.py IN.docx OUT.docx --company "Acme Ltd."

--company is the footer text before the first "|" (the profile's
tools.doc_templates.company). Running it twice changes nothing.

What it does, per footer the document uses (default and first page):
- skips footers with no text (e.g. the unused "even pages" footer),
- skips footers that already have a PAGE field,
- finds the company name (stored as one run or split) and the
  first run after it that starts with "|" (the address part),
- inserts " | Page {PAGE} of {NUMPAGES}" between them, in the style of the
  address part (regular, not bold),
- stops with an error if a footer does not have that shape, so nothing is
  guessed.
"""
import re
import sys
import zipfile

RUN_RE = re.compile(r'<w:r\b[^>]*>(?:(?!</w:r>).)*?</w:r>', re.S)


def run_text(run: str) -> str:
    return ''.join(re.findall(r'<w:t\b[^>]*>([^<]*)</w:t>', run))


def run_rpr(run: str) -> str:
    m = re.search(r'<w:rPr>(.*?)</w:rPr>', run, re.S)
    inner = m.group(1) if m else ''
    inner = re.sub(r'<w:b(Cs)?\b[^>]*/>', '', inner)   # never bold
    inner = re.sub(r'<w:rtl\b[^>]*/>', '', inner)
    return '<w:rPr>' + inner + '</w:rPr>'


def counter_runs(rpr: str, lead: str = ' ', tail: str = '') -> str:
    def text(t):
        return f'<w:r>{rpr}<w:t xml:space="preserve">{t}</w:t></w:r>'

    def field(code):
        return (
            f'<w:r>{rpr}<w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r>{rpr}<w:instrText xml:space="preserve"> {code} \\* MERGEFORMAT </w:instrText></w:r>'
            f'<w:r>{rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r>{rpr}<w:t>1</w:t></w:r>'
            f'<w:r>{rpr}<w:fldChar w:fldCharType="end"/></w:r>'
        )

    return (text(lead + '| Page ') + field('PAGE') + text(' of ') + field('NUMPAGES')
            + (text(tail) if tail else ''))


def full_field(rpr: str, code: str) -> str:
    return (
        f'<w:r>{rpr}<w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r>{rpr}<w:instrText xml:space="preserve"> {code} \\* MERGEFORMAT </w:instrText></w:r>'
        f'<w:r>{rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r>{rpr}<w:t>1</w:t></w:r>'
        f'<w:r>{rpr}<w:fldChar w:fldCharType="end"/></w:r>'
    )


# A page field as Google Docs saves it: ONE run holding begin / instrText /
# separate / end and no digit. LibreOffice then prints the digit in its own
# default font (black serif or LiberationSans). Rewrite it in the full form,
# keeping that run's own style.
DOCS_FIELD_RE = re.compile(
    r'<w:r\b[^>]*>(?P<rpr><w:rPr>(?:(?!</w:rPr>).)*</w:rPr>)?'
    r'<w:fldChar w:fldCharType="begin"\s*/>'
    r'<w:instrText[^>]*>\s*(?P<code>PAGE|NUMPAGES)\b[^<]*</w:instrText>'
    r'<w:fldChar w:fldCharType="separate"\s*/>'
    r'<w:fldChar w:fldCharType="end"\s*/></w:r>', re.S)


def repair_docs_fields(xml: str):
    count = 0

    def fix(m):
        nonlocal count
        count += 1
        rpr = m.group('rpr') or ''
        rpr = re.sub(r'<w:rtl\b[^>]*/>', '', rpr)
        return full_field(rpr, m.group('code'))

    return DOCS_FIELD_RE.sub(fix, xml), count


COMPANY = 'Acme Ltd.'   # replaced by --company


def add_counter(xml: str, name: str) -> str:
    """Insert the counter just before the first run that starts with "|"
    (the address part). Everything before it must read exactly COMPANY, which
    may be stored as one run or split (e.g. "Acme" + " Ltd.")."""
    text_runs = [m for m in RUN_RE.finditer(xml) if run_text(m.group(0)).strip()]
    addr_i = next((i for i, m in enumerate(text_runs)
                   if run_text(m.group(0)).lstrip().startswith('|')), None)
    if addr_i is None or addr_i == 0:
        raise SystemExit(f'{name}: no "<company> | <address>" shape found')
    before = ''.join(run_text(m.group(0)) for m in text_runs[:addr_i])
    if before.strip() != COMPANY:
        raise SystemExit(f'{name}: text before the first "|" is {before!r}, expected {COMPANY!r}')
    addr = text_runs[addr_i]
    addr_text = run_text(addr.group(0))
    # keep exactly one space on each side of every "|":
    # "Acme Ltd." + " | University..."  -> add " | Page X of Y"
    # "Acme Ltd. " + "| University..."  -> add "| Page X of Y "
    lead = '' if before.endswith(' ') else ' '
    tail = '' if addr_text.startswith(' ') else ' '
    rpr = run_rpr(addr.group(0))
    pos = addr.start()
    return xml[:pos] + counter_runs(rpr, lead, tail) + xml[pos:]


def continue_numbering(doc: str):
    """Google Docs writes "restart page numbers at 1" on every section.
    When a later section starts on a new page (e.g. the Agent Agreement's
    Appendix), the counter jumps back to "Page 1", and LibreOffice adds an
    invisible blank page to keep odd/even order, so the total is one too high
    ("Page 1 of 5" on a 4-page PDF). Keep the restart only on the first
    section, so numbering runs on through the whole document."""
    count = 0
    first = True

    def fix(m):
        nonlocal count, first
        s = m.group(0)
        if first:
            first = False
            return s
        new = re.sub(r'(<w:pgNumType\b[^>]*?)\s+w:start="\d+"', r'\1', s)
        if new != s:
            count += 1
        return new

    return re.sub(r'<w:sectPr\b.*?</w:sectPr>', fix, doc, flags=re.S), count


def fix_list_markers(numbering: str, doc: str):
    """Google Docs drops the style of some list markers ("a.", "i.") when it
    saves. LibreOffice then draws them in its default 11 pt font, much bigger
    than the text. For every list level that is actually used and has no
    font or size of its own, give the marker the font, size and colour of the
    first text run of the items that use it (never bold or italic).
    Levels that already have a font and size are left alone."""
    num_to_abs = dict(re.findall(
        r'<w:num\b[^>]*w:numId="(\d+)"[^>]*>.*?<w:abstractNumId w:val="(\d+)"', numbering, re.S))
    # (abstractNumId, ilvl) -> rPr of the first text run of the first item using it
    first_item = {}
    for p in re.finditer(r'<w:p\b.*?</w:p>', doc, re.S):
        para = p.group(0)
        np_ = re.search(r'<w:numPr>.*?</w:numPr>', para, re.S)
        if not np_:
            continue
        ilvl = re.search(r'<w:ilvl w:val="(\d+)"', np_.group(0))
        num = re.search(r'<w:numId w:val="(\d+)"', np_.group(0))
        if not num or num.group(1) not in num_to_abs:
            continue
        key = (num_to_abs[num.group(1)], ilvl.group(1) if ilvl else '0')
        if key in first_item:
            continue
        for r in RUN_RE.finditer(para):
            if run_text(r.group(0)).strip():
                m = re.search(r'<w:rPr>(.*?)</w:rPr>', r.group(0), re.S)
                first_item[key] = m.group(1) if m else ''
                break

    count = 0

    def style_from(rpr: str) -> str:
        # element order follows the Word schema: rFonts, b, bCs, i, iCs, color, sz, szCs
        fonts = ''.join(re.findall(r'<w:rFonts\b[^>]*/>', rpr)[:1])
        rest = ''.join(re.findall(r'<w:color\b[^>]*/>', rpr)[:1]
                       + re.findall(r'<w:sz\b[^>]*/>', rpr)[:1]
                       + re.findall(r'<w:szCs\b[^>]*/>', rpr)[:1])
        if not (fonts or rest):
            return ''
        return fonts + '<w:b w:val="0"/><w:bCs w:val="0"/><w:i w:val="0"/><w:iCs w:val="0"/>' + rest

    def fix_abs(a):
        nonlocal count
        abs_id = a.group(1)

        def fix_lvl(lv):
            nonlocal count
            body = lv.group(0)
            ilvl = lv.group(1)
            key = (abs_id, ilvl)
            if key not in first_item:
                return body
            rpr = re.search(r'<w:rPr>(.*?)</w:rPr>', body, re.S)
            inner = rpr.group(1) if rpr else ''
            if '<w:rFonts' in inner and '<w:sz ' in inner:
                return body
            new = style_from(first_item[key])
            if not new:
                return body
            # keep anything already there that we don't set (e.g. underline)
            extra = re.sub(r'<w:(rFonts|color|sz|szCs|b|bCs|i|iCs)\b[^>]*/>', '', inner)
            count += 1
            new_rpr = '<w:rPr>' + new + extra + '</w:rPr>'
            if rpr:
                return body[:rpr.start()] + new_rpr + body[rpr.end():]
            return body.replace('</w:lvl>', new_rpr + '</w:lvl>')

        return re.sub(r'<w:lvl\b[^>]*w:ilvl="(\d+)"[^>]*>.*?</w:lvl>', fix_lvl, a.group(0), flags=re.S)

    out = re.sub(r'<w:abstractNum\b[^>]*w:abstractNumId="(\d+)"[^>]*>.*?</w:abstractNum>',
                 fix_abs, numbering, flags=re.S)
    return out, count


def used_footers(z: zipfile.ZipFile) -> list:
    doc = z.read('word/document.xml').decode('utf8')
    rels = z.read('word/_rels/document.xml.rels').decode('utf8')
    ids = set(re.findall(r'<w:footerReference\b[^>]*r:id="([^"]+)"', doc))
    out = []
    for rid in ids:
        m = re.search(r'<Relationship\b[^>]*Id="' + re.escape(rid) + r'"[^>]*Target="([^"]+)"', rels)
        if not m:
            m = re.search(r'<Relationship\b[^>]*Target="([^"]+)"[^>]*Id="' + re.escape(rid) + r'"', rels)
        if m:
            out.append('word/' + m.group(1).lstrip('/').replace('word/', ''))
    return sorted(set(out))


def main(src: str, dst: str) -> None:
    with zipfile.ZipFile(src) as z:
        changed = {}
        for name in used_footers(z):
            xml = z.read(name).decode('utf8')
            if not re.search(r'<w:t\b[^>]*>[^<]*\S', xml):
                print(f'skip {name}: no text')
                continue
            if 'PAGE' in ''.join(re.findall(r'<w:instrText[^>]*>([^<]*)<', xml)) \
                    or re.search(r'<w:fldSimple\b[^>]*PAGE', xml):
                fixed, n = repair_docs_fields(xml)
                if n:
                    changed[name] = fixed
                    print(f'repaired {n} page field(s) emptied by Google Docs in {name}')
                else:
                    print(f'skip {name}: already has a working page field')
                continue
            changed[name] = add_counter(xml, name)
            print(f'added page counter to {name}')
        doc = z.read('word/document.xml').decode('utf8')
        fixed, n = continue_numbering(doc)
        if n:
            changed['word/document.xml'] = fixed
            print(f'page numbering now continues through {n} later section(s)')
        if 'word/numbering.xml' in z.namelist():
            numbering = z.read('word/numbering.xml').decode('utf8')
            fixed, n = fix_list_markers(numbering, doc)
            if n:
                changed['word/numbering.xml'] = fixed
                print(f'list markers: gave {n} unstyled list level(s) the style of their item text')
        # rewrite the zip with the changed parts, same order, same compression
        with zipfile.ZipFile(dst, 'w') as out:
            for info in z.infolist():
                data = changed[info.filename].encode('utf8') if info.filename in changed \
                    else z.read(info.filename)
                out.writestr(info, data, compress_type=info.compress_type)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Add "Page X of Y" to a .docx template footer.')
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--company', required=True, help='footer text before the first "|"')
    a = ap.parse_args()
    COMPANY = a.company
    main(a.src, a.dst)
