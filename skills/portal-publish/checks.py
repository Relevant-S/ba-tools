"""Contract checks for portal-publish (contract/checks.md).

check_publish(doc) runs the version check, the schema and the named cross-field checks, in that order.
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

# Fields no_html_entities skips: light HTML (cleaned by the Portal) and fields with a format.
# Paths are JSON Pointers with every array index replaced by "*".
ENTITY_SKIP = {
    "/features/*/summary",
    "/items/*/text",
    "/features/*/clar_url",
    "/client_contacts/*/email",
}


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


@lru_cache(maxsize=None)
def validator(contract: str) -> Draft202012Validator:
    schema = load_json(index()["schemas"][contract])
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=format_checker())


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


def check_entities(doc) -> list[dict]:
    out: list[dict] = []

    def walk(value, parts, shape):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, parts + [k], shape + [k])
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, parts + [i], shape + ["*"])
        elif isinstance(value, str) and pointer(shape) not in ENTITY_SKIP:
            m = ENTITY.search(value)
            if m:
                path = pointer(parts)
                out.append(detail(path, "no_html_entities",
                                  f"{path} holds an HTML entity ({m.group(0)}). "
                                  "This field is plain text: use the character itself."))

    walk(doc, [], [])
    return out


def cross_field(doc: dict) -> list[dict]:
    return (check_unique(doc, "features", "id", "unique_feature_id", "Feature id")
            + check_unique(doc, "items", "key", "unique_item_key", "Item key")
            + check_entities(doc))


def accepted_for(kind: str) -> list[str]:
    """The accepted versions of one contract type, oldest first, e.g. ["dashboard/1"]."""
    return [c for c in index()["accepted"] if c.startswith(kind + "/")]


def check_publish(doc, kind: str = "dashboard") -> dict | None:
    """Check one Publish document of a contract type. None = it passes."""
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
    found = cross_field(doc)
    if found:
        return {"code": "contract_invalid", "details": found}
    return None


def check_reply(doc, contract: str) -> list[dict]:
    """Schema-check a Portal reply (publish-reply/1, status/1). [] = it passes."""
    return schema_details(validator(contract), doc)
