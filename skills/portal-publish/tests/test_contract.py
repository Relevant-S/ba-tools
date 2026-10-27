"""Tests for the portal-publish contract (contract/checks.md). The Portal runs the same fixtures."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import checks

FIXTURES = checks.CONTRACT_DIR / "fixtures"
VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted(p for p in (FIXTURES / "invalid").iterdir() if p.is_dir())
SCHEMAS = sorted(checks.CONTRACT_DIR.glob("*.schema.json"))


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---- fixtures ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_passes(path):
    doc = read(path)
    if doc["contract"] in checks.index()["accepted"]:
        assert checks.check_publish(doc) is None
    else:
        assert checks.check_reply(doc, doc["contract"]) == []


@pytest.mark.parametrize("case", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_fails_as_expected(case):
    expected = read(case / "expected.json")
    result = checks.check_publish(read(case / "input.json"))
    assert result is not None, "should fail"
    assert result["code"] == expected["code"]
    pairs = {(d["check"], d["path"]) for d in result["details"]}
    assert pairs == {(d["check"], d["path"]) for d in expected["details"]}, result["details"]
    assert all(d["message"] for d in result["details"])


def test_easy_payday_size():
    doc = read(FIXTURES / "valid" / "dashboard-1-easy-payday-size.json")
    assert (len(doc["features"]), len(doc["items"])) == (18, 148)


def test_every_invalid_rule_has_a_fixture():
    assert {p.name for p in INVALID} == {
        "unknown-field-feature", "unknown-field-top", "missing-feature-title", "missing-sent-by",
        "too-many-features", "too-many-items", "too-many-contacts", "feature-title-too-long",
        "item-title-too-long", "bad-stage", "bad-date", "impossible-date", "bad-time", "leap-second",
        "bad-email", "email-no-dot-domain", "bad-uri", "bad-item-key", "contract-not-text",
        "empty-required-text", "duplicate-feature-id", "duplicate-item-key", "html-entity", "entity-in-list",
        "version-not-accepted",
    }


# ---- messages ---------------------------------------------------------------------------------------

def small():
    return read(FIXTURES / "valid" / "dashboard-1-small.json")


def test_duplicate_message_names_both():
    doc = small()
    doc["features"][3]["id"] = doc["features"][1]["id"]
    (d,) = checks.check_publish(doc)["details"]
    assert "/features/1/id" in d["message"] and "/features/3/id" in d["message"]


def test_entity_message_names_field():
    doc = small()
    doc["items"][0]["how_to_send"] = "Reply &#8212; by email"
    (d,) = checks.check_publish(doc)["details"]
    assert d["path"] == "/items/0/how_to_send" and "/items/0/how_to_send" in d["message"]


def test_entities_allowed_in_light_html():
    doc = small()
    doc["features"][0]["summary"] = "<p>Fees &amp; limits</p>"
    doc["items"][0]["text"] = "<p>a &amp; b</p>"
    assert checks.check_publish(doc) is None


def test_body_that_is_not_an_object_fails_the_schema():
    assert checks.check_publish([])["code"] == "contract_invalid"
    assert checks.check_publish(None)["code"] == "contract_invalid"


def test_version_message_lists_accepted():
    doc = small()
    doc["contract"] = "dashboard/2"
    (d,) = checks.check_publish(doc)["details"]
    assert d["message"] == "dashboard/2 is not accepted. This Portal accepts dashboard/1."


def test_missing_contract_is_a_schema_error():
    doc = small()
    del doc["contract"]
    result = checks.check_publish(doc)
    assert result["code"] == "contract_invalid"
    assert ("schema", "/contract") in {(d["check"], d["path"]) for d in result["details"]}


def test_errors_json_matches_the_spine_table():
    errors = checks.load_json("errors.json")
    assert {k: v["status"] for k, v in errors.items()} == {
        "bad_request": 400, "invalid_key": 401, "batch_unknown": 404, "project_archived": 409,
        "round_has_answers": 409, "batch_expired": 409, "payload_too_large": 413,
        "contract_version_not_accepted": 422, "contract_invalid": 422, "screenshot_mismatch": 422,
        "server_error": 500,
    }
    assert all(v["message"] for v in errors.values())


# ---- schema shape -----------------------------------------------------------------------------------

def walk_objects(schema, path="#"):
    """Yield (path, schema) for every subschema."""
    if isinstance(schema, dict):
        yield path, schema
        for key, value in schema.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    yield from walk_objects(sub, f"{path}/{key}/{name}")
            elif key in ("items", "if", "then", "else", "not"):
                yield from walk_objects(value, f"{path}/{key}")
            elif key in ("anyOf", "oneOf", "allOf"):
                for i, sub in enumerate(value):
                    yield from walk_objects(sub, f"{path}/{key}/{i}")


def is_container(prop: dict) -> bool:
    if prop.get("type") == "object":
        return True
    return prop.get("type") == "array" and prop.get("items", {}).get("type") == "object"


def leaves(schema, path="#"):
    """Yield (path, schema) for every leaf field: a property that is not an object or a list of objects."""
    for name, prop in schema.get("properties", {}).items():
        here = f"{path}/{name}"
        if prop.get("type") == "object":
            yield from leaves(prop, here)
        elif prop.get("type") == "array" and prop.get("items", {}).get("type") == "object":
            yield from leaves(prop["items"], here + "[]")
        else:
            yield here, prop


def visibility_problems(schema) -> list[str]:
    problems = []
    for path, prop in leaves(schema):
        if prop.get("x-visibility") not in checks.VISIBILITY:
            problems.append(f"{path}: x-visibility {prop.get('x-visibility')!r}")
    for path, sub in walk_objects(schema):
        if sub.get("type") == "object" and sub.get("additionalProperties") is not False:
            problems.append(f"{path}: object without additionalProperties: false")
    return problems


def dashboard_schema():
    return checks.load_json("dashboard-1.schema.json")


def test_dashboard_leaves_have_visibility_and_objects_are_closed():
    assert visibility_problems(dashboard_schema()) == []


def test_unknown_visibility_is_caught():
    schema = copy.deepcopy(dashboard_schema())
    schema["properties"]["features"]["items"]["properties"]["title"]["x-visibility"] = "secret"
    assert visibility_problems(schema) == ["#/features[]/title: x-visibility 'secret'"]


def test_visibility_levels_are_the_agreed_ones():
    vis = {path: prop["x-visibility"] for path, prop in leaves(dashboard_schema())}
    assert sorted(p for p, v in vis.items() if v == "id") == ["#/features[]/id", "#/items[]/key"]
    for p in ("#/contract", "#/sent_at", "#/sent_by", "#/ba_tools_version", "#/source_commit"):
        assert vis[p] == "admin"
    for p in ("#/client_contacts[]/name", "#/client_contacts[]/email", "#/client_contacts[]/slack",
              "#/features[]/clar_url", "#/features[]/done_date", "#/items[]/kind", "#/items[]/feature",
              "#/items[]/who", "#/items[]/since"):
        assert vis[p] == "portal"
    assert sorted(p for p, v in vis.items() if v == "admin") == sorted(
        ["#/contract", "#/sent_at", "#/sent_by", "#/ba_tools_version", "#/source_commit"])


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_schema_is_valid_2020_12(path):
    schema = read(path)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_every_object_is_closed(path):
    for where, sub in walk_objects(read(path)):
        if sub.get("type") == "object":
            assert sub.get("additionalProperties") is False, where


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_patterns_are_ascii_and_fixed_length(path):
    for where, sub in walk_objects(read(path)):
        if "pattern" in sub:
            assert sub["pattern"].isascii(), where
            # Python's `$` also matches before a final line break; a fixed length makes that harmless.
            assert sub.get("minLength") == sub.get("maxLength") is not None, where


def test_limits_match_the_spec():
    p = dashboard_schema()["properties"]
    assert p["features"]["maxItems"] == 300
    assert p["items"]["maxItems"] == 1000
    assert p["client_contacts"]["maxItems"] == 200
    assert p["features"]["items"]["properties"]["stage"]["enum"] == ["concept", "spec", "ready", "dev", "qa", "done"]


def test_index_names_existing_schemas():
    idx = checks.index()
    assert idx["accepted"] == ["dashboard/1"]
    for contract, name in idx["schemas"].items():
        assert (checks.CONTRACT_DIR / name).is_file(), contract
        assert read(checks.CONTRACT_DIR / name)["properties"]["contract"]["const"] == contract


def test_light_html_list():
    lh = checks.load_json("light-html.json")
    assert lh["tags"] == ["p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "code", "span"]
    assert lh["classes"] == {"*": ["lead"]}


def test_reply_dry_run_rules():
    sent = read(FIXTURES / "valid" / "publish-reply-1-sent.json")
    dry = read(FIXTURES / "valid" / "publish-reply-1-dry-run.json")
    assert checks.check_reply({**sent, "client_contact_names": []}, "publish-reply/1") != []
    assert checks.check_reply({**sent, "publish_id": None}, "publish-reply/1") != []
    no_view = {k: v for k, v in dry.items() if k != "client_view"}
    assert checks.check_reply(no_view, "publish-reply/1") != []
