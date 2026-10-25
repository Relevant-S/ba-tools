#!/usr/bin/env python3
"""One-off: move a clarification page's YAML to the new layout's fields, keeping its formatting.

    python _convert_v2.py merchants-decisions.yaml merchants-v2-fields.yaml

The second file holds the new top-level fields (name, description, round, url, problem, solution,
decisions, events). They are inserted after `title:`. The fields the new layout no longer reads
(`stages_label`, `stages`, `close_title`, `close_body`, `settled`) are removed. Top-level blocks are
cut as text, so comments and the existing questions keep their formatting.
"""
import re
import sys
from pathlib import Path

import yaml

DROP = {"stages_label", "stages", "close_title", "close_body", "settled"}

target, fields = Path(sys.argv[1]), Path(sys.argv[2])
new = fields.read_text(encoding="utf-8").rstrip() + "\n"
yaml.safe_load(new)  # fail early on a broken snippet
lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
top = [(i, m.group(1)) for i, l in enumerate(lines) if (m := re.match(r"([a-z_]+):", l))]
bounds = {k: (i, top[n + 1][0] if n + 1 < len(top) else len(lines)) for n, (i, k) in enumerate(top)}
added = {k for k in yaml.safe_load(new)}
drop = (DROP | added) & set(bounds)
out = []
for n, (i, k) in enumerate(top):
    if n == 0:
        out += lines[:i]
    a, b = bounds[k]
    if k not in drop:
        out += lines[a:b]
    if k == "title":
        out.append(new)
target.write_text("".join(out), encoding="utf-8")
yaml.safe_load(target.read_text(encoding="utf-8"))
print(f"{target.name}: added {sorted(added)}, removed {sorted(drop - added)}")
