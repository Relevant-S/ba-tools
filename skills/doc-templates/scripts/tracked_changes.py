"""List tracked changes per paragraph in a .docx: print the paragraph with
[-deleted-] and {+inserted+} marks. Also flags {{ }} template tags.
Usage: python -I tracked_changes.py FILE.docx"""
import sys
import zipfile
import re
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
z = zipfile.ZipFile(sys.argv[1])
root = ET.fromstring(z.read('word/document.xml'))


def walk(el, mode, out):
    tag = el.tag
    if tag == W + 'ins':
        mode = 'ins'
    elif tag == W + 'del':
        mode = 'del'
    if tag == W + 't' or tag == W + 'delText':
        t = el.text or ''
        if mode == 'ins':
            out.append('{+' + t + '+}')
        elif mode == 'del':
            out.append('[-' + t + '-]')
        else:
            out.append(t)
    elif tag == W + 'tab':
        out.append(' ')
    for c in el:
        walk(c, mode, out)


n = 0
for p in root.iter(W + 'p'):
    has = p.find('.//' + W + 'ins') is not None or p.find('.//' + W + 'del') is not None
    ppr_change = p.find('.//' + W + 'rPr/' + W + 'ins') is not None
    if not has:
        continue
    out = []
    walk(p, None, out)
    s = ''.join(out)
    s = s.replace('+}{+', '').replace('-][-', '')
    if not re.search(r'\{\+.+?\+\}|\[-.+?-\]', s):
        continue
    n += 1
    print(f'--- change {n}')
    print(s)
print('TOTAL', n)
