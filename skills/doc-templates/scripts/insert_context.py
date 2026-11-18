"""Show 2 paragraphs before and 1 after each inserted paragraph, the numbering
of inserted paragraphs, and count of {{ }} tags in the file.
Usage: python -I insert_context.py FILE.docx"""
import sys
import zipfile
import re
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
z = zipfile.ZipFile(sys.argv[1])
xml = z.read('word/document.xml').decode('utf8')
root = ET.fromstring(xml)
paras = list(root.iter(W + 'p'))


def text(p):
    return ''.join((t.text or '') for t in p.iter() if t.tag in (W + 't',))


def numinfo(p):
    n = p.find(W + 'pPr/' + W + 'numPr')
    if n is None:
        return ''
    il = n.find(W + 'ilvl')
    ni = n.find(W + 'numId')
    return f"[num {ni.get(W + 'val') if ni is not None else '?'} lvl {il.get(W + 'val') if il is not None else '?'}]"


ins_idx = [i for i, p in enumerate(paras) if p.find('.//' + W + 'ins') is not None and text(p).strip()]
shown = set()
for i in ins_idx:
    for j in range(max(0, i - 2), min(len(paras), i + 2)):
        if j in shown:
            continue
        shown.add(j)
        mark = 'INS' if j in ins_idx else '   '
        print(mark, numinfo(paras[j]), text(paras[j])[:110])
    print('...')
tags = re.findall(r'\{\{[^}]*\}\}', re.sub(r'<[^>]+>', '', xml))
print('TEMPLATE TAGS:', len(tags), tags[:8])
