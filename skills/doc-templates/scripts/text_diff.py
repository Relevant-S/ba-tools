"""Diff the paragraph text of two .docx files (body + footers).
Usage: python -I text_diff.py A.docx B.docx"""
import sys
import zipfile
import difflib
import re
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def paras(path):
    z = zipfile.ZipFile(path)
    out = []
    names = ['word/document.xml'] + sorted(n for n in z.namelist() if re.match(r'word/(footer|header)\d*\.xml', n))
    for n in names:
        root = ET.fromstring(z.read(n))
        for p in root.iter(W + 'p'):
            t = ''.join((x.text or '') for x in p.iter() if x.tag == W + 't')
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                out.append(n.split('/')[1][:7] + ': ' + t)
    return out


a, b = paras(sys.argv[1]), paras(sys.argv[2])
for line in difflib.unified_diff(a, b, 'A', 'B', n=0, lineterm=''):
    print(line[:220])
