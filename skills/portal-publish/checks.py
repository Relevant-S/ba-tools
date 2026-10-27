"""Contract checks for portal-publish (contract/checks.md).

check_publish(doc, kind, parts) runs the version check, the schema and the named cross-field checks, in that
order; for a page given its screenshot part names it then runs screens_match_parts.
It returns None when the document passes, else {"code": ..., "details": [{"path", "check", "message"}]}.
The Portal runs the same checks in TypeScript; both sides test against contract/fixtures/.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_DIR = Path(__file__).resolve().parent / "contract"

VISIBILITY = ("client", "id", "portal", "admin")

ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")

# Fields no_html_entities skips, per contract type: light HTML (cleaned by the Portal) and fields with a
# format that may hold "&". Paths are JSON Pointers with every array index replaced by "*".
ENTITY_SKIP = {
    "dashboard": {
        "/features/*/summary",
        "/items/*/text",
        "/features/*/clar_url",
        "/client_contacts/*/email",
    },
    "clarification": {
        "/description",
        "/problem",
        "/solution",
        "/design/summary",
        "/design/detail",
        "/questions/*/body",
        "/questions/*/body2",
        "/questions/*/snag",
        "/url",
        "/design/screens/*/file",
        "/questions/*/screens/*/file",
    },
}

# At most this many screenshots in one page, design and Questions together (check max_screenshots).
MAX_SCREENSHOTS = 30

# A screen file name may not hold these (bare_file_names): control characters and ":".
BAD_NAME_CHARS = re.compile(r"[\x00-\x1f\x7f:]")
# The multipart part that holds the page JSON; no screenshot may take its name.
RESERVED_PART = "publish"


# The ajv-formats full-mode email regex (the Portal's check), so both sides judge an email the same way.
# jsonschema's own email check only looks for "@". re.ASCII keeps IGNORECASE to A-Z, as in JavaScript.
EMAIL = re.compile(
    r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",
    re.IGNORECASE | re.ASCII,
)


def format_checker() -> FormatChecker:
    checker = FormatChecker()
    checker.checks("email")(lambda value: not isinstance(value, str) or EMAIL.fullmatch(value) is not None)
    return checker


def load_json(name: str):
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def index() -> dict:
    return load_json("index.json")


# Stands in for a `false` field schema ("this field may not be here"). It means the same, but jsonschema
# reports a `false` under "properties" with an empty path, and Ajv with the field's path.
NOT_ALLOWED = {"not": {}}


def no_false_fields(schema):
    """The schema with every `false` under "properties" replaced by NOT_ALLOWED."""
    if isinstance(schema, dict):
        return {k: ({n: NOT_ALLOWED if sub is False else no_false_fields(sub) for n, sub in v.items()}
                    if k == "properties" and isinstance(v, dict) else no_false_fields(v))
                for k, v in schema.items()}
    if isinstance(schema, list):
        return [no_false_fields(v) for v in schema]
    return schema


@lru_cache(maxsize=None)
def validator(contract: str) -> Draft202012Validator:
    schema = load_json(index()["schemas"][contract])
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(no_false_fields(schema), format_checker=format_checker())


def pointer(parts) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def detail(path: str, check: str, message: str) -> dict:
    return {"path": path, "check": check, "message": message}


def schema_details(v: Draft202012Validator, doc) -> list[dict]:
    out: list[dict] = []
    for err in v.iter_errors(doc):
        base = list(err.absolute_path)
        if err.validator == "required":
            missing = [p for p in err.validator_value if isinstance(err.instance, dict) and p not in err.instance]
            for p in missing:
                path = pointer(base + [p])
                d = detail(path, "schema", f"{path or '/'}: required field is missing")
                if d not in out:
                    out.append(d)
        elif err.validator == "additionalProperties" and isinstance(err.instance, dict):
            known = set(err.schema.get("properties", {}))
            for p in err.instance:
                if p not in known:
                    path = pointer(base + [p])
                    out.append(detail(path, "schema", f"{path}: unknown field"))
        elif err.validator == "not" and err.validator_value == {}:
            path = pointer(base)
            out.append(detail(path, "schema", f"{path}: this field is not allowed here"))
        else:
            path = pointer(base)
            out.append(detail(path, "schema", f"{path or '/'}: {err.message}"))
    return out


def check_unique(doc: dict, listname: str, field: str, check: str, label: str) -> list[dict]:
    out, seen = [], {}
    for i, entry in enumerate(doc.get(listname, [])):
        value = entry[field]
        here = f"/{listname}/{i}/{field}"
        if value in seen:
            out.append(detail(here, check, f'{label} "{value}" is used twice: {seen[value]} and {here}'))
        else:
            seen[value] = here
    return out


def check_entities(doc, kind: str = "dashboard") -> list[dict]:
    out: list[dict] = []
    skip = ENTITY_SKIP[kind]

    def walk(value, parts, shape):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, parts + [k], shape + [k])
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, parts + [i], shape + ["*"])
        elif isinstance(value, str) and pointer(shape) not in skip:
            m = ENTITY.search(value)
            if m:
                path = pointer(parts)
                out.append(detail(path, "no_html_entities",
                                  f"{path} holds an HTML entity ({m.group(0)}). "
                                  "This field is plain text: use the character itself."))

    walk(doc, [], [])
    return out


def page_screens(doc: dict) -> list[tuple[str, dict]]:
    """Every screen of a page in page order, with its path: the design screens, then each Question's."""
    out = [(f"/design/screens/{j}", s) for j, s in enumerate(doc.get("design", {}).get("screens", []))]
    for i, q in enumerate(doc.get("questions", [])):
        out += [(f"/questions/{i}/screens/{j}", s) for j, s in enumerate(q.get("screens", []))]
    return out


def check_option_values(doc: dict) -> list[dict]:
    out: list[dict] = []
    for i, q in enumerate(doc.get("questions", [])):
        seen: dict = {}
        for j, opt in enumerate(q["options"]):
            value, here = opt["v"], f"/questions/{i}/options/{j}/v"
            if value in seen:
                out.append(detail(here, "unique_option_v",
                                  f'Option value "{value}" is used twice in one Question: {seen[value]} and {here}'))
            else:
                seen[value] = here
    return out


def check_one_rec(doc: dict) -> list[dict]:
    out: list[dict] = []
    for i, q in enumerate(doc.get("questions", [])):
        first = None
        for j, opt in enumerate(q["options"]):
            if opt.get("rec") is True:
                here = f"/questions/{i}/options/{j}/rec"
                if first is None:
                    first = here
                else:
                    out.append(detail(here, "one_rec_max",
                                      f"A Question may have at most one recommended option: {first} and {here}"))
    return out


def check_file_names(doc: dict) -> list[dict]:
    out: list[dict] = []
    seen: dict = {}
    for where, screen in page_screens(doc):
        name, here = screen["file"], where + "/file"
        key = name.lower()
        if "/" in name or "\\" in name:
            problem = "is not a bare file name. Leave out the folder."
        elif name in (".", ".."):
            problem = "is not a file name."
        elif BAD_NAME_CHARS.search(name):
            problem = 'holds a control character or ":". Rename the file.'
        elif key == RESERVED_PART:
            problem = f'is the name of the "{RESERVED_PART}" part. Rename the file.'
        elif key in seen:
            out.append(detail(here, "bare_file_names",
                              f'File name "{name}" is used twice (letter case aside): {seen[key]} and {here}'))
            continue
        else:
            seen[key] = here
            continue
        out.append(detail(here, "bare_file_names", f'{here} "{name}" {problem}'))
    return out


def check_one_hero(doc: dict) -> list[dict]:
    out: list[dict] = []
    first = None
    for where, screen in page_screens(doc):
        if screen.get("hero") is True:
            here = where + "/hero"
            if first is None:
                first = here
            else:
                out.append(detail(here, "one_hero_max",
                                  f"A page may have at most one hero screen: {first} and {here}"))
    return out


def check_screenshot_count(doc: dict) -> list[dict]:
    screens = page_screens(doc)
    if len(screens) <= MAX_SCREENSHOTS:
        return []
    where = screens[MAX_SCREENSHOTS][0]
    return [detail(where, "max_screenshots",
                   f"This page has {len(screens)} screenshots; at most {MAX_SCREENSHOTS} are allowed, design and "
                   f"Questions together. The first one over the limit is {where}.")]


def screens_match_parts(doc: dict, parts) -> list[dict]:
    """Every named screenshot has a part, and every part is named (the caller leaves out the publish part)."""
    out: list[dict] = []
    sent = set(parts)
    named = set()
    for where, screen in page_screens(doc):
        name = screen["file"]
        named.add(name)
        if name not in sent:
            out.append(detail(where + "/file", "screens_match_parts",
                              f'{where}/file names "{name}", but no screenshot of that name was sent.'))
    counted: dict = {}
    for name in parts:
        counted[name] = counted.get(name, 0) + 1
    for name, times in counted.items():
        if name not in named:
            out.append(detail("", "screens_match_parts",
                              f'A screenshot named "{name}" was sent, but no screen in the page names it.'))
        if times > 1:
            out.append(detail("", "screens_match_parts",
                              f'A screenshot named "{name}" was sent {times} times. Send each one once.'))
    return out


def cross_field(doc: dict, kind: str = "dashboard") -> list[dict]:
    if kind == "clarification":
        return (check_unique(doc, "questions", "id", "unique_question_id", "Question id")
                + check_option_values(doc)
                + check_one_rec(doc)
                + check_file_names(doc)
                + check_one_hero(doc)
                + check_screenshot_count(doc)
                + check_unique(doc, "decisions", "id", "unique_decision_id", "Decision id")
                + check_entities(doc, kind))
    return (check_unique(doc, "features", "id", "unique_feature_id", "Feature id")
            + check_unique(doc, "items", "key", "unique_item_key", "Item key")
            + check_entities(doc, kind))


def accepted_for(kind: str) -> list[str]:
    """The accepted versions of one contract type, oldest first, e.g. ["dashboard/1"]."""
    return [c for c in index()["accepted"] if c.startswith(kind + "/")]


def check_publish(doc, kind: str = "dashboard", parts=None) -> dict | None:
    """Check one Publish document of a contract type (dashboard or clarification). None = it passes.

    parts: for a page, the names of the screenshot parts sent with it (not the publish part). When given,
    screens_match_parts runs last, only on a page that passed everything else."""
    accepted = accepted_for(kind)
    contract = doc.get("contract") if isinstance(doc, dict) else None
    if isinstance(contract, str) and contract not in accepted:
        return {"code": "contract_version_not_accepted", "details": [detail(
            "/contract", "contract_version",
            f"{contract} is not accepted. This Portal accepts {', '.join(accepted)}.")]}
    # A missing or non-string contract is left to the schema: the newest accepted version reports it.
    schema_for = contract if isinstance(contract, str) else accepted[-1]
    found = schema_details(validator(schema_for), doc)
    if found:
        return {"code": "contract_invalid", "details": found}
    found = cross_field(doc, kind)
    if found:
        return {"code": "contract_invalid", "details": found}
    if kind == "clarification" and parts is not None:
        found = screens_match_parts(doc, parts)
        if found:
            return {"code": "screenshot_mismatch", "details": found}
    return None


def check_reply(doc, contract: str) -> list[dict]:
    """Schema-check a reply or request body that is not a Publish (publish-reply/1, status/1, answers/1,
    ack-request/1, ack/1). [] = it passes."""
    return schema_details(validator(contract), doc)
