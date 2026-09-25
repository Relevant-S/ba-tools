#!/usr/bin/env python3
"""
Generate a project's data dictionary (ba-tools `data-dictionary` skill).

Reads the SHIPPED truth out of the code:
  - every Prisma schema listed in the config        entities, fields, types, lengths, enums, /// docs
  - optional shared TypeScript enum folders          the cross-boundary enum contract
  - optional UI copy                                  what each field is CALLED on screen
      i18n:        folders of JSON translation files  (scoped to an entity by `model_namespaces`)
      strings_ts:  constant files like  `export const FIRST_NAME = 'First name'`
                   (matched to a field by name; shown as a *suggested* label)

Reads the AUTHORED layer the code cannot hold:
  - the overlay (markdown)                            meaning, "means NOT", labels, min/max, status

Writes one file (the `out` path in the config). Never hand-edit it: edit the overlay or the code, re-run.

Usage:
    uv run --with pyyaml python generate.py [--config docs/BA/data-dictionary.config.yaml] [--root .] [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from itertools import combinations
from pathlib import Path

import yaml

# --- configuration (filled by load_config) ------------------------------------

ROOT = Path(".").resolve()
CFG: dict = {}
TITLE = "Data Dictionary"
OVERLAY = Path("docs/BA/data-dictionary.overlay.md")
OUTPUT = Path("docs/BA/data-dictionary.md")
I18N_DIRS: dict[str, Path] = {}
MODEL_NAMESPACES: dict[str, list[str]] = {}
LABEL_PARENTS = {"form", "fields", "columns", "filter", "label", "labels"}
BOILERPLATE_FIELDS = {"id", "createdAt", "updatedAt", "deletedAt", "version"}
CONVENTIONAL_DESCRIPTIONS = {
    "id": "Primary key.",
    "createdAt": "Row creation timestamp.",
    "updatedAt": "Row last-changed timestamp.",
    "deletedAt": "Soft-delete timestamp; null means live.",
    "version": "Optimistic-concurrency version — incremented on every write, checked on update.",
}
STRINGS: dict[str, tuple[str, str]] = {}   # normalised field name -> (label, "file:KEY")


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def read_source(entry) -> str:
    """A source is a local path, or {repo, ref, path} read from git (the fresh remote branch)."""
    if isinstance(entry, str):
        p = ROOT / entry
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    repo, ref, path = ROOT / entry["repo"], entry.get("ref", "origin/main"), entry["path"]
    r = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def source_label(entry) -> str:
    return entry if isinstance(entry, str) else f"{entry['repo']} @ {entry.get('ref', 'origin/main')} : {entry['path']}"


def load_config(path: Path) -> None:
    global CFG, TITLE, OVERLAY, OUTPUT, I18N_DIRS, MODEL_NAMESPACES, LABEL_PARENTS
    CFG = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    TITLE = CFG.get("title", TITLE)
    OVERLAY = ROOT / CFG.get("overlay", str(OVERLAY))
    OUTPUT = ROOT / CFG.get("out", str(OUTPUT))
    labels = CFG.get("labels") or {}
    I18N_DIRS = {app: ROOT / d for app, d in (labels.get("i18n") or {}).items()}
    MODEL_NAMESPACES = labels.get("model_namespaces") or {}
    if labels.get("label_parents"):
        LABEL_PARENTS = set(labels["label_parents"])
    BOILERPLATE_FIELDS.update(CFG.get("boilerplate_fields") or [])
    CONVENTIONAL_DESCRIPTIONS.update(CFG.get("conventional_descriptions") or {})
    for entry in labels.get("strings_ts") or []:
        text = read_source(entry)
        for key, val in re.findall(r"export\s+const\s+([A-Z][A-Z0-9_]*)\s*=\s*\n?\s*'([^'\n]{1,60})'", text):
            if "{" in val:
                continue
            STRINGS.setdefault(norm(key), (val, f"{Path(source_label(entry)).name}:{key}"))


def conventional_description(fld: Field, model_names: set[str]) -> str:
    """A description derived from structure, not invented. Empty when nothing is derivable."""
    if fld.name in CONVENTIONAL_DESCRIPTIONS:
        return CONVENTIONAL_DESCRIPTIONS[fld.name]
    if fld.name.endswith("Id"):
        target = fld.name[:-2]
        target = target[0].upper() + target[1:]
        if target in model_names:
            optional = " Optional." if fld.is_optional else ""
            return f"Foreign key -> `{target}`.{optional}"
    return ""


# --- models ------------------------------------------------------------------


@dataclass
class Field:
    name: str
    type: str
    is_list: bool
    is_optional: bool
    attrs: str
    doc: str = ""

    @property
    def rendered_type(self) -> str:
        return f"{self.type}{'[]' if self.is_list else ''}{'?' if self.is_optional else ''}"

    @property
    def db_column(self) -> str:
        m = re.search(r'@map\("([^"]+)"\)', self.attrs)
        return m.group(1) if m else ""

    @property
    def max_length(self) -> str:
        m = re.search(r"@db\.(?:VarChar|Char|NVarChar|NChar)\((\d+)\)", self.attrs)
        return m.group(1) if m else ""

    @property
    def required(self) -> bool:
        return not self.is_optional and not self.is_list and "@default" not in self.attrs and "@updatedAt" not in self.attrs

    @property
    def effective_column(self) -> str:
        """The real snake_case column name. Without an explicit @map, Prisma uses the
        field name verbatim - so a blank here would read as 'no column', which is wrong."""
        return self.db_column or self.name


@dataclass
class Model:
    name: str
    doc: str = ""
    table: str = ""
    fields: list[Field] = dc_field(default_factory=list)


@dataclass
class Enum:
    name: str
    values: list[str] = dc_field(default_factory=list)
    doc: str = ""
    source: str = ""  # "prisma" | "shared" | "both"
    shared_values: list[str] = dc_field(default_factory=list)


# --- parsing: prisma ---------------------------------------------------------


def clean_doc(lines: list[str]) -> str:
    text = " ".join(l.strip() for l in lines).strip()
    return re.sub(r"\s+", " ", text)


def parse_prisma(src: str) -> tuple[dict[str, Model], dict[str, Enum]]:
    models: dict[str, Model] = {}
    enums: dict[str, Enum] = {}

    pending: list[str] = []
    current: Model | Enum | None = None
    kind = ""

    for raw in src.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("///"):
            pending.append(stripped[3:])
            continue

        m = re.match(r"^model\s+(\w+)\s*\{", stripped)
        if m:
            current = Model(name=m.group(1), doc=clean_doc(pending))
            kind = "model"
            pending = []
            continue

        m = re.match(r"^enum\s+(\w+)\s*\{", stripped)
        if m:
            current = Enum(name=m.group(1), doc=clean_doc(pending), source="prisma")
            kind = "enum"
            pending = []
            continue

        if stripped.startswith("}") and current is not None:
            if kind == "model":
                models[current.name] = current
            else:
                enums[current.name] = current
            current, kind, pending = None, "", []
            continue

        if current is None or not stripped or stripped.startswith("//"):
            pending = pending if stripped.startswith("//") else pending
            continue

        if kind == "model":
            if stripped.startswith("@@"):
                mm = re.search(r'@@map\("([^"]+)"\)', stripped)
                if mm:
                    current.table = mm.group(1)
                pending = []
                continue
            fm = re.match(r"^(\w+)\s+(\w+)(\[\])?(\?)?\s*(.*)$", stripped)
            if fm:
                current.fields.append(
                    Field(
                        name=fm.group(1),
                        type=fm.group(2),
                        is_list=bool(fm.group(3)),
                        is_optional=bool(fm.group(4)),
                        attrs=fm.group(5) or "",
                        doc=clean_doc(pending),
                    )
                )
            pending = []
        else:
            vm = re.match(r"^([A-Za-z_]\w*)\s*$", stripped)
            if vm:
                current.values.append(vm.group(1))
            pending = []

    return models, enums


# --- parsing: shared TS enums ------------------------------------------------


def parse_shared_enums(directory: Path) -> dict[str, tuple[list[str], str]]:
    """Return {EnumName: ([wire values], jsdoc)} from one folder of TypeScript enum files."""
    found: dict[str, tuple[list[str], str]] = {}
    if not directory.is_dir():
        return found

    for ts in sorted(directory.glob("*.ts")):
        if ts.name.endswith(".test.ts"):
            continue
        src = ts.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"export enum\s+(\w+)\s*\{(.*?)\}", src, re.S):
            name, body = m.group(1), m.group(2)
            values = [v for _, v in re.findall(r"(\w+)\s*=\s*'([^']+)'", body)]
            doc = ""
            preceding = src[: m.start()]
            dm = list(re.finditer(r"/\*\*(.*?)\*/", preceding, re.S))
            if dm and preceding[dm[-1].end():].strip() == "":
                doc = clean_doc([l.lstrip("* ") for l in dm[-1].group(1).splitlines()])
            found[name] = (values, doc)
    return found


# --- parsing: i18n display copy ----------------------------------------------


def load_i18n() -> list[tuple[str, str, str]]:
    """Flatten every English namespace into (app, dotted.key, text)."""
    rows: list[tuple[str, str, str]] = []
    for app, directory in I18N_DIRS.items():
        if not directory.is_dir():
            continue
        for jf in sorted(directory.glob("*.json")):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            def walk(node, prefix):
                for k, v in node.items():
                    key = f"{prefix}{k}"
                    if isinstance(v, dict):
                        walk(v, key + ".")
                    elif isinstance(v, str):
                        rows.append((app, f"{jf.stem}.{key}", v))

            walk(data, "")
    return rows


def field_labels(i18n, field_name: str, model_name: str) -> list[tuple[str, str, str]]:
    """Display labels for a field, scoped to the namespaces that can speak for its model.
    Only keys that are structurally a field LABEL count - `form.type`, `columns.type`,
    `filter.typeLabel` - never body copy that happens to mention the word."""
    allowed = MODEL_NAMESPACES.get(model_name)
    if not allowed:
        hit = STRINGS.get(norm(field_name))
        return [("strings", hit[1], hit[0])] if hit else []
    hits: list[tuple[str, str, str]] = []
    for app, key, text in i18n:
        parts = key.split(".")
        if parts[0] not in allowed:
            continue
        last = parts[-1]
        parent = parts[-2] if len(parts) >= 2 else ""
        is_label = (last == field_name and parent in LABEL_PARENTS) or (
            last == field_name + "Label" and parent in LABEL_PARENTS
        )
        if is_label and "{{" not in text:
            hits.append((app, key, text))
    return hits


def value_labels(i18n, enum_name: str, values: list[str], usages) -> dict[str, list[str]]:
    """Display labels per enum value.

    Scoped hard, because enum values are ordinary words. `open` as a CommunityKind is not
    the `open` of "Open menu", and `pending` as an approval state is not "Mark as pending".
    A hit must be in a namespace that can speak for a model using this enum, AND sit under a
    parent segment naming the field or the enum - the `status.draft` / `tier.gold` shape.
    """
    wanted = set(values)
    found: dict[str, set[str]] = {v: set() for v in values}

    enum_tokens = {t.lower() for t in re.findall(r"[A-Z][a-z]+", enum_name)}
    allowed_ns: set[str] = set()
    allowed_parents: set[str] = set(enum_tokens)
    for model_name, field_name in usages:
        allowed_ns.update(MODEL_NAMESPACES.get(model_name, []))
        allowed_parents.add(field_name.lower())
    if not allowed_ns:
        return {}

    for _, key, text in i18n:
        parts = key.split(".")
        if parts[0] not in allowed_ns or len(parts) < 2:
            continue
        last, parent = parts[-1], parts[-2]
        if last in wanted and parent.lower() in allowed_parents:
            if "{{" not in text and len(text) < 60:
                found[last].add(text)
    return {k: sorted(v) for k, v in found.items() if v}


# --- parsing: the authored overlay -------------------------------------------


def parse_overlay(path: Path) -> dict[str, dict[str, str]]:
    """
    Overlay format - H3 heading is the key, then `key: value` lines.

        ### enum:PartnerTier
        status: partial
        means-not: not the membership tier
        note: free text
    """
    entries: dict[str, dict[str, str]] = {}
    if not path.is_file():
        return entries

    key = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip()
        hm = re.match(r"^###\s+(.+?)\s*$", line)
        if hm:
            key = hm.group(1).strip()
            entries[key] = {}
            continue
        if key and ":" in line and not line.startswith("#"):
            k, _, v = line.partition(":")
            k = k.strip().lower()
            if re.fullmatch(r"[a-z-]+", k):
                entries[key][k] = v.strip()
    return entries


# --- the checks --------------------------------------------------------------


def collision_report(models, prisma_enums, shared_enums, i18n) -> dict[str, list]:
    out: dict[str, list] = {}

    # C1 - one field name, several declared types.
    by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for model in models.values():
        for f in model.fields:
            if f.name in BOILERPLATE_FIELDS:
                continue
            by_name[f.name].append((model.name, f.rendered_type))

    c1 = []
    for name, uses in sorted(by_name.items()):
        base_types = {t.rstrip("?[]") for _, t in uses}
        if len(uses) >= 2 and len(base_types) >= 2:
            scalars = {"String", "Int", "Boolean", "DateTime", "Json", "Decimal", "Float", "BigInt"}
            typed = base_types - scalars
            severity = "HIGH" if typed and (base_types & scalars) else "MEDIUM"
            c1.append((name, sorted(uses), severity))
    out["one_name_many_types"] = c1

    # C2 - one enum value living in several enums.
    all_enums = {n: e.values for n, e in prisma_enums.items()}
    value_owners: dict[str, list[str]] = defaultdict(list)
    for ename, values in all_enums.items():
        for v in values:
            value_owners[v].append(ename)
    out["value_in_many_enums"] = sorted(
        ((v, sorted(owners)) for v, owners in value_owners.items() if len(owners) >= 3),
        key=lambda x: -len(x[1]),
    )

    # C3 - enums whose value sets look alike (Jaccard >= 0.5).
    lookalikes = []
    for (a, va), (b, vb) in combinations(sorted(all_enums.items()), 2):
        sa, sb = set(va), set(vb)
        if not sa or not sb:
            continue
        j = len(sa & sb) / len(sa | sb)
        if j >= 0.5:
            lookalikes.append((a, b, round(j, 2), sorted(sa & sb), sorted(sa ^ sb)))
    out["lookalike_enums"] = sorted(lookalikes, key=lambda x: -x[2])

    # C4 - Prisma enum vs shared TS enum drift.
    drift = []
    for name, e in sorted(prisma_enums.items()):
        if name in shared_enums:
            sv = shared_enums[name][0]
            if sorted(sv) != sorted(e.values):
                drift.append((name, sorted(e.values), sorted(sv)))
    out["prisma_shared_drift"] = drift

    # C5 - enum defined on only one side of the boundary.
    prisma_only = sorted(set(prisma_enums) - set(shared_enums))
    shared_only = sorted(set(shared_enums) - set(prisma_enums))
    out["prisma_only"] = prisma_only
    out["shared_only"] = shared_only

    # C7 - the UI calls a field one thing, the schema calls something ELSE that name.
    # This is the class the schema alone can never catch: a spec writer reads the screen,
    # a developer reads the model, and they use the same word for different things.
    field_owner: dict[str, list[str]] = defaultdict(list)
    for model in models.values():
        for f in model.fields:
            if f.name not in BOILERPLATE_FIELDS:
                field_owner[f.name.lower()].append(f"{model.name}.{f.name}")

    vocab = []
    for model in models.values():
        for f in model.fields:
            if f.name in BOILERPLATE_FIELDS:
                continue
            for _, key, text in field_labels(i18n, f.name, model.name):
                token = re.sub(r"[^a-z]", "", text.lower())
                if not token or token == f.name.lower():
                    continue
                clashes = [o for o in field_owner.get(token, []) if o != f"{model.name}.{f.name}"]
                if clashes:
                    vocab.append((f"{model.name}.{f.name}", text, key, sorted(set(clashes))))
    # One row per (field, label) pair.
    seen_pairs = set()
    deduped = []
    for row in vocab:
        sig = (row[0], row[1])
        if sig not in seen_pairs:
            seen_pairs.add(sig)
            deduped.append(row)
    out["ui_vs_schema_vocabulary"] = deduped

    # C6 - a raw String column where a typed list for that very concept already exists.
    known = set(prisma_enums) | set(shared_enums)
    untyped = []
    for model in models.values():
        for f in model.fields:
            if f.type != "String" or f.name in BOILERPLATE_FIELDS:
                continue
            pascal = f.name[0].upper() + f.name[1:]
            # Exact hits first: the enum IS the concept, or is the model's own version of it.
            exact = sorted(e for e in known if e in (pascal, model.name + pascal))
            # Fall back to a suffix match, but only when it is unambiguous. A loose `endswith`
            # on a word like "Type" matches nine enums and drowns the real findings.
            fuzzy = sorted(e for e in known if e.endswith(pascal) and e != pascal)
            hits = exact or (fuzzy if len(fuzzy) == 1 else [])
            if hits:
                untyped.append((f"{model.name}.{f.name}", hits))
    out["untyped_but_enumerable"] = untyped

    return out


# --- rendering ---------------------------------------------------------------

def warn() -> str:
    return ("<!-- GENERATED FILE - DO NOT HAND-EDIT.\n"
            "     Rebuild with the ba-tools data-dictionary skill (scripts/generate.py).\n"
            f"     Authored rows live in {OVERLAY.relative_to(ROOT).as_posix()} -->\n")

STATUS_MARK = {
    "shipped": "shipped",
    "planned": "PLANNED - not in the schema",
    "partial": "PARTIAL - schema and plan disagree",
    "retired": "RETIRED - do not use",
}


def esc(text: str) -> str:
    return text.replace("|", "\\|").strip()


def truncate(text: str, limit: int = 260) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "..."


def render(models, prisma_enums, shared_enums, overlay, checks, i18n) -> str:
    L: list[str] = []
    a = L.append

    a(warn())
    a(f"# {TITLE}")
    a("")
    a("One name, one meaning. This file is the place to check a name **before** a spec, a PRD or a")
    a("story invents one.")
    a("")
    open_names = [
        n for n, _, _ in checks["one_name_many_types"]
        if not overlay.get(f"word:{n}", {}).get("accepted")
    ]
    open_untyped = [
        c for c, _ in checks["untyped_but_enumerable"]
        if not overlay.get(f"field:{c}", {}).get("accepted")
    ]
    described = total = 0
    for m in models.values():
        for f in m.fields:
            if f.name in BOILERPLATE_FIELDS:
                continue
            total += 1
            fmeta = overlay.get(f"field:{m.name}.{f.name}", {})
            if f.doc or fmeta.get("description"):
                described += 1
    pct = round(described * 100 / total) if total else 0

    a("| | |")
    a("|---|---|")
    a(f"| Entities | {len(models)} |")
    a(f"| Enums (database) | {len(prisma_enums)} |")
    a(f"| Enums (shared contract) | {len(shared_enums)} |")
    a(f"| Fields with a description | {described} of {total} ({pct}%) |")
    a(f"| Name collisions still open | **{len(open_names)}** of {len(checks['one_name_many_types'])} |")
    a(f"| Untyped columns still open | **{len(open_untyped)}** of {len(checks['untyped_but_enumerable'])} |")
    open_vocab = [
        r for r in checks["ui_vs_schema_vocabulary"]
        if not overlay.get(f"label:{r[0]} = {r[1]}", {}).get("accepted")
    ]
    a(
        f"| Screen-vs-schema word clashes still open | **{len(open_vocab)}** of "
        f"{len(checks['ui_vs_schema_vocabulary'])} |"
    )
    a("")
    a("**How to read it.** Parts 2 to 5 are generated from the shipped code and rebuilt on every")
    a("run, so they cannot go stale. Part 1 and the Status / Means-NOT columns are authored by hand")
    a(f"in `{OVERLAY.relative_to(ROOT).as_posix()}`.")
    a("")
    a("**What each entity-table column means.**")
    a("")
    a("| Column | Where it comes from |")
    a("|---|---|")
    a("| **Type** | the Prisma field type. A typed enum is checked by the database; a `String` is not. |")
    a("| **Required** | `yes` when the database refuses a row without it (not optional, no default). The screen may ask for more; an overlay `required:` says so. |")
    a("| **Min / max** | the longest text the column takes (`@db.VarChar(n)`), plus any `min:` / `max:` written in the overlay. `-` means no limit is recorded. |")
    a("| **Column** | the real snake_case column name — what a migration, a raw ledger query or a database dump shows you. Differs from the field name wherever `@map` is set. |")
    a("| **Values** | the allowed values, for anything backed by a checked list. `-` means free text or a number. |")
    a("| **Display name** | what the UI actually calls it, read from the English i18n files, with the key underneath. A best-effort lookup — a *suggested* label came from a strings file by name, not from the screen that shows it. Override with `display:` in the overlay. `-` means no label was found: the field is never shown, or its copy is hardcoded. |")
    a("| **Description** | what the field IS. The schema's own `///` comment first, then an overlay `description:`, then a conventional meaning for keys, stamps and timestamps. `_undocumented_` means nobody has said. |")
    a("| **Notes** | authored warnings only — what this field must NOT be confused with, and any ruling or status. |")
    a("")
    a("**Sources.** " + "; ".join(f"`{source_label(e)}`" for e in CFG.get("schemas", [])) + ". A term that is in a PRD or a spec but not here is **not built**.")
    a("")
    a("---")
    a("")

    # Part 1 - reserved words
    a("## 1. Reserved words - one word, one job")
    a("")
    # A word entry that carries only an `accepted:` ruling belongs in the collision report,
    # not in the vocabulary table.
    words = {
        k: v for k, v in overlay.items()
        if k.startswith("word:") and (v.get("means") or v.get("means-not"))
    }
    if words:
        a("| Word | Means | Never means | Use instead |")
        a("|---|---|---|---|")
        for key, meta in sorted(words.items()):
            a(
                f"| **{esc(key.split(':', 1)[1])}** | {esc(meta.get('means', '-'))} "
                f"| {esc(meta.get('means-not', '-'))} | {esc(meta.get('use-instead', '-'))} |"
            )
    else:
        a("_No reserved words recorded yet. Add `### word:<term>` entries to the overlay._")
    a("")

    # Part 2 - collisions
    a("---")
    a("")
    a("## 2. Collision report (generated)")
    a("")
    a("Every row is a place where one name is doing more than one job, or one list is being")
    a("mistaken for another. A **HIGH** row means one of the uses is untyped - the dangerous shape.")
    a("")

    c1 = checks["one_name_many_types"]
    a("### 2.1 One field name, several types")
    a("")
    if c1:
        a("| Field | Severity | Used as | Ruling |")
        a("|---|---|---|---|")
        for name, uses, sev in c1:
            rendered = "<br>".join(f"`{m}.{name}` -> `{t}`" for m, t in uses)
            accepted = overlay.get(f"word:{name}", {}).get("accepted", "")
            mark = "ACCEPTED" if accepted else f"**{sev}**"
            a(f"| `{name}` | {mark} | {rendered} | {esc(accepted) or 'open'} |")
    else:
        a("_None._")
    a("")

    a("### 2.2 One enum value, several enums")
    a("")
    v = checks["value_in_many_enums"]
    if v:
        a("| Value | Appears in |")
        a("|---|---|")
        for val, owners in v:
            a(f"| `{val}` | {', '.join(f'`{o}`' for o in owners)} |")
    else:
        a("_None._")
    a("")

    a("### 2.3 Look-alike lists")
    a("")
    a("Two enums that share most of their values. These are the pairs a reader will assume are")
    a("interchangeable. Check the difference column before reusing either.")
    a("")
    lk = checks["lookalike_enums"]
    if lk:
        a("| Enum A | Enum B | Overlap | Shared values | **Differs by** |")
        a("|---|---|---|---|---|")
        for x, y, j, shared, diff in lk:
            a(
                f"| `{x}` | `{y}` | {int(j * 100)}% | {', '.join(f'`{s}`' for s in shared)} "
                f"| {', '.join(f'`{d}`' for d in diff) or '-'} |"
            )
    else:
        a("_None._")
    a("")

    a("### 2.4 Database enum vs shared contract")
    a("")
    a("The database list and the shared contract should carry the same values. Any row here is live drift.")
    a("")
    drift = checks["prisma_shared_drift"]
    if drift:
        a("| Enum | Prisma | shared contract |")
        a("|---|---|---|")
        for name, pv, sv in drift:
            a(f"| `{name}` | {', '.join(f'`{x}`' for x in pv)} | {', '.join(f'`{x}`' for x in sv)} |")
    else:
        a("_No drift. Every enum defined on both sides carries identical values._")
    a("")
    a(f"**Database only** ({len(checks['prisma_only'])}) - no shared contract, so the client cannot")
    a("type against them: " + (", ".join(f"`{x}`" for x in checks["prisma_only"]) or "none") + ".")
    a("")
    a(f"**Shared only** ({len(checks['shared_only'])}) - no database column, so these are wire or")
    a("UI concepts: " + (", ".join(f"`{x}`" for x in checks["shared_only"]) or "none") + ".")
    a("")

    a("### 2.5 Untyped column, typed list available")
    a("")
    a("The column is a plain `String`, but a checked list for that same concept already exists.")
    a("Sometimes that is deliberate - say so in the overlay and it moves to ACCEPTED. Left open, it")
    a("is a column the database will not defend.")
    a("")
    ut = checks["untyped_but_enumerable"]
    if ut:
        a("| Column | Existing list | Ruling |")
        a("|---|---|---|")
        for col, hits in ut:
            accepted = overlay.get(f"field:{col}", {}).get("accepted", "")
            a(
                f"| `{col}` | {', '.join(f'`{h}`' for h in hits)} "
                f"| {'ACCEPTED - ' + esc(accepted) if accepted else '**open**'} |"
            )
    else:
        a("_None._")
    a("")

    a("### 2.6 The screen and the schema use the same word for different things")
    a("")
    a("The UI calls a field one thing; the schema gives that same name to something else. This is")
    a("the collision no schema check can find - a spec writer reads the screen, a developer reads")
    a("the model, and neither can see the other's vocabulary.")
    a("")
    vocab = checks["ui_vs_schema_vocabulary"]
    if vocab:
        a("| Field | The UI calls it | i18n key | But the schema spends that word on | Ruling |")
        a("|---|---|---|---|---|")
        for fld, label, key, clashes in vocab:
            ruling = overlay.get(f"label:{fld} = {label}", {}).get("accepted", "")
            a(
                f"| `{fld}` | **\"{esc(label)}\"** | `{key}` "
                f"| {', '.join(f'`{c}`' for c in clashes)} "
                f"| {'ACCEPTED - ' + esc(ruling) if ruling else '**open**'} |"
            )
    else:
        a("_None._")
    a("")

    # Part 3 - enum registry
    a("---")
    a("")
    a("## 3. Enum registry (generated + authored status)")
    a("")
    a("Each value shows the English label the UI puts on it, where the i18n files carry one.")
    a("A value with no label is either not shown to users or has its copy hardcoded.")
    a("")
    a("| Enum | Values (and how they are displayed) | Count | Status | Never means |")
    a("|---|---|---|---|---|")
    for name in sorted(set(prisma_enums) | set(shared_enums)):
        pv = prisma_enums[name].values if name in prisma_enums else []
        sv = shared_enums[name][0] if name in shared_enums else []
        values = pv or sv
        meta = overlay.get(f"enum:{name}", {})
        status = STATUS_MARK.get(meta.get("status", ""), "shipped")
        where = []
        if name in prisma_enums:
            where.append("db")
        if name in shared_enums:
            where.append("shared")

        usages = [
            (m.name, f.name) for m in models.values() for f in m.fields if f.type == name
        ]
        vlabels = value_labels(i18n, name, values, usages)
        rendered = []
        for v in values:
            labels = vlabels.get(v, [])
            if labels:
                rendered.append(f'`{v}` = "{" / ".join(labels)}"')
            else:
                rendered.append(f"`{v}`")

        a(
            f"| `{name}`<br><sub>{'+'.join(where)}</sub> | {esc('<br>'.join(rendered))} "
            f"| {len(values)} | {esc(status)} | {esc(meta.get('means-not', '-'))} |"
        )
    a("")

    for name in sorted(set(prisma_enums) | set(shared_enums)):
        doc = (prisma_enums[name].doc if name in prisma_enums else "") or (
            shared_enums[name][1] if name in shared_enums else ""
        )
        meta = overlay.get(f"enum:{name}", {})
        if not doc and not meta.get("note"):
            continue
        a(f"**`{name}`** - {truncate(doc)}" if doc else f"**`{name}`**")
        if meta.get("note"):
            a("")
            a(f"> {meta['note']}")
        a("")

    # Part 4 - entity registry
    a("---")
    a("")
    a("## 4. Entity registry (generated)")
    a("")
    model_names = set(models)
    for name in sorted(models):
        model = models[name]
        meta = overlay.get(f"model:{name}", {})
        a(f"### `{name}`")
        a("")
        if model.table:
            a(f"Table `{model.table}`.")
            a("")
        if model.doc:
            a(f"{truncate(model.doc, 400)}")
            a("")
        if meta.get("note"):
            a(f"> {meta['note']}")
            a("")

        rels = [f for f in model.fields if f.type in model_names]
        scalars = [f for f in model.fields if f.type not in model_names]

        a("| Field | Type | Required | Min / max | Column | Values | Display name | Description | Notes |")
        a("|---|---|---|---|---|---|---|---|---|")
        for f in scalars:
            fmeta = overlay.get(f"field:{name}.{f.name}", {})

            # Values - the checked list, inline, so nobody has to scroll to part 3.
            if f.type in prisma_enums:
                vals = ", ".join(f"`{v}`" for v in prisma_enums[f.type].values)
            elif f.type in shared_enums:
                vals = ", ".join(f"`{v}`" for v in shared_enums[f.type][0])
            elif f.type == "String" and f.name in ("type", "kind") and name + "Type" in shared_enums:
                vals = ", ".join(f"`{v}`" for v in shared_enums[name + "Type"][0]) + " <sub>(list lives in the shared contract, column is untyped)</sub>"
            else:
                vals = "-"

            # Display name - what the UI actually calls it, from the i18n files.
            if fmeta.get("display"):
                shown = esc(fmeta["display"])
            else:
                labels = field_labels(i18n, f.name, name)
                distinct = sorted({t for _, _, t in labels})
                if not distinct:
                    shown = "-"
                elif len(distinct) == 1 and labels[0][0] == "strings":
                    shown = f'"{distinct[0]}"<br><sub>suggested · `{labels[0][1]}`</sub>'
                elif len(distinct) == 1:
                    shown = f'**"{distinct[0]}"**<br><sub>`{labels[0][1]}`</sub>'
                else:
                    shown = (
                        " / ".join(f'**"{d}"**' for d in distinct)
                        + "<br><sub>differs by screen</sub>"
                    )
            # Description is what the field IS: the schema's own /// doc, or an overlay
            # `description:` for a field the schema leaves undocumented.
            desc = (
                truncate(f.doc, 300)
                or fmeta.get("description", "")
                or conventional_description(f, model_names)
                or "_undocumented_"
            )
            # Notes is authored only: the warning, the ruling, the status.
            note = " ".join(
                x for x in (
                    fmeta.get("means-not", ""),
                    ("ACCEPTED - " + fmeta["accepted"]) if fmeta.get("accepted") else "",
                    STATUS_MARK.get(fmeta.get("status", ""), "") if fmeta.get("status") else "",
                ) if x
            )
            req = fmeta.get("required") or ("yes" if f.required else "no")
            lim = " · ".join(x for x in (
                f"min {fmeta['min']}" if fmeta.get("min") else "",
                f"max {fmeta.get('max') or f.max_length}" if (fmeta.get("max") or f.max_length) else "",
            ) if x) or "-"
            a(
                f"| `{f.name}` | `{f.rendered_type}` | {esc(req)} | {esc(lim)} | `{f.effective_column}` | {vals} "
                f"| {shown} | {esc(desc)} | {esc(note) or '-'} |"
            )
        a("")
        if rels:
            # Some of the sharpest reasoning in the schema sits on relation fields (delete
            # behaviour, cardinality carve-outs). Give them a table when they are documented.
            if any(f.doc for f in rels):
                a("| Relation | Points at | Description |")
                a("|---|---|---|")
                for f in rels:
                    a(
                        f"| `{f.name}` | `{f.rendered_type}` "
                        f"| {esc(truncate(f.doc, 300)) or '_undocumented_'} |"
                    )
            else:
                a("Relations: " + ", ".join(f"`{f.name}` -> `{f.rendered_type}`" for f in rels) + ".")
            a("")

    # Part 5 - screens
    a("---")
    a("")
    a("## 5. Screens and UI labels (authored)")
    a("")
    a("A screen name is not in any schema, so nothing else can catch two screens sharing a label.")
    a("")
    screens = {k: v for k, v in overlay.items() if k.startswith("screen:")}
    if screens:
        a("| Screen | Where it lives | Who sees it | Never confuse with |")
        a("|---|---|---|---|")
        for key, meta in sorted(screens.items()):
            a(
                f"| **{esc(key.split(':', 1)[1])}** | {esc(meta.get('where', '-'))} "
                f"| {esc(meta.get('who', '-'))} | {esc(meta.get('means-not', '-'))} |"
            )
    else:
        a("_No screens recorded yet. Add `### screen:<name>` entries to the overlay._")
    a("")

    # Part 6 - planned terms
    a("---")
    a("")
    a("## 6. Planned terms - named but not built (authored)")
    a("")
    a("A name reserved by a PRD or a spec but absent from the schema. Reserving it here is what")
    a("stops a second spec spending the same word on something else.")
    a("")
    planned = {
        k: v for k, v in overlay.items()
        if v.get("status") in ("planned", "partial") and not k.startswith("word:")
    }
    if planned:
        a("| Term | Kind | Status | Source | Never means |")
        a("|---|---|---|---|---|")
        for key, meta in sorted(planned.items()):
            kind, _, term = key.partition(":")
            a(
                f"| **{esc(term)}** | {esc(kind)} | {esc(STATUS_MARK.get(meta.get('status', ''), '-'))} "
                f"| {esc(meta.get('source', '-'))} | {esc(meta.get('means-not', '-'))} |"
            )
    else:
        a("_None recorded._")
    a("")

    return "\n".join(L) + "\n"


# --- main --------------------------------------------------------------------


def main() -> int:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="the project root")
    ap.add_argument("--config", default="docs/BA/data-dictionary.config.yaml")
    ap.add_argument("--check", action="store_true", help="exit 1 if the output is stale")
    args = ap.parse_args()
    ROOT = Path(args.root).resolve()
    cfg_path = ROOT / args.config
    if not cfg_path.is_file():
        print(f"ERROR: no config at {cfg_path} — start one from the skill's assets/config.example.yaml", file=sys.stderr)
        return 2
    load_config(cfg_path)

    models: dict[str, Model] = {}
    prisma_enums: dict[str, Enum] = {}
    for entry in CFG.get("schemas", []):
        src = read_source(entry)
        if not src:
            print(f"ERROR: cannot read the schema {source_label(entry)}", file=sys.stderr)
            return 2
        m, e = parse_prisma(src)
        prefix = entry.get("prefix", "") if isinstance(entry, dict) else ""
        for name, model in m.items():
            key = f"{prefix}{name}" if (prefix or name not in models) else f"{name} ({source_label(entry).split(' ')[0]})"
            model.name = key
            models[key] = model
        prisma_enums.update(e)
    shared_enums: dict = {}
    for d in CFG.get("shared_enums", []) or []:
        shared_enums.update(parse_shared_enums(ROOT / d))
    overlay = parse_overlay(OVERLAY)
    i18n = load_i18n()
    checks = collision_report(models, prisma_enums, shared_enums, i18n)
    text = render(models, prisma_enums, shared_enums, overlay, checks, i18n)

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != text:
            print(f"STALE: {OUTPUT.name} does not match the code. Re-run the generator.")
            return 1
        print(f"OK: {OUTPUT.name} is current.")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"ok": True, "wrote": OUTPUT.relative_to(ROOT).as_posix(), "entities": len(models),
                      "db_enums": len(prisma_enums), "shared_enums": len(shared_enums), "overlay_entries": len(overlay),
                      "labels_from_strings": len(STRINGS),
                      "checks": {k: len(v) for k, v in checks.items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
