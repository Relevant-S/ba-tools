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


# Valid files with no contract field are matched to a schema by file-name prefix.
SCHEMA_BY_PREFIX = {"ack-request-1": "ack-request/1"}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def page_files(doc: dict) -> list[str]:
    """A page's screenshot file names in page order: the parts a correct send carries."""
    return [screen["file"] for _, screen in checks.page_screens(doc)]


def contract_of(path: Path, doc) -> str:
    if isinstance(doc, dict) and "contract" in doc:
        return doc["contract"]
    for prefix, contract in SCHEMA_BY_PREFIX.items():
        if path.name.startswith(prefix):
            return contract
    raise AssertionError(f"{path.name}: no contract field, and no known file-name prefix in SCHEMA_BY_PREFIX")


# ---- fixtures ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixture_passes(path):
    doc = read(path)
    contract = contract_of(path, doc)
    if contract in checks.index()["accepted"]:
        kind = contract.split("/")[0]
        parts = page_files(doc) if kind == "clarification" else None
        assert checks.check_publish(doc, kind, parts) is None
    else:
        assert checks.check_reply(doc, contract) == []


def case_input(case: Path):
    """The kind, document and screenshot parts of an invalid case (parts.json, else the page's own files)."""
    expected = read(case / "expected.json")
    kind = expected.get("kind", "dashboard")
    doc = read(case / "input.json")
    parts = None
    if kind == "clarification":
        parts = read(case / "parts.json") if (case / "parts.json").is_file() else page_files(doc)
    return kind, doc, parts


@pytest.mark.parametrize("case", INVALID, ids=lambda p: p.name)
def test_invalid_fixture_fails_as_expected(case):
    expected = read(case / "expected.json")
    if "contract" in expected:  # a reply or request: checked with that schema, no code
        result = {"details": checks.check_reply(read(case / "input.json"), expected["contract"])}
        assert result["details"], "should fail"
    else:
        kind, doc, parts = case_input(case)
        result = checks.check_publish(doc, kind, parts)
        assert result is not None, "should fail"
        assert result["code"] == expected["code"]
    pairs = {(d["check"], d["path"]) for d in result["details"]}
    assert pairs == {(d["check"], d["path"]) for d in expected["details"]}, result["details"]
    assert all(d["message"] for d in result["details"])


def test_easy_payday_size():
    doc = read(FIXTURES / "valid" / "dashboard-1-easy-payday-size.json")
    assert (len(doc["features"]), len(doc["items"])) == (18, 148)


DASHBOARD_CASES = {
    "unknown-field-feature", "unknown-field-top", "missing-feature-title", "missing-sent-by",
    "too-many-features", "too-many-items", "too-many-contacts", "feature-title-too-long",
    "item-title-too-long", "bad-stage", "bad-date", "impossible-date", "bad-time", "leap-second",
    "bad-email", "email-no-dot-domain", "bad-uri", "bad-item-key", "contract-not-text",
    "empty-required-text", "duplicate-feature-id", "duplicate-item-key", "html-entity", "entity-in-list",
    "version-not-accepted",
}
PAGE_CASES = {
    "page-too-many-questions", "page-too-many-screenshots", "question-no-options",
    "question-too-many-options", "slug-capital", "slug-space", "slug-trailing-newline", "slug-too-long",
    "page-name-too-long", "design-summary-too-long", "question-title-too-long", "option-text-too-long",
    "question-missing-body", "page-unknown-field", "screen-unknown-field", "duplicate-question-id",
    "duplicate-option-v", "two-recommended", "file-with-folder", "duplicate-file-name",
    "screen-without-part", "part-without-screen", "page-html-entity", "page-entity-in-option",
    "page-version-not-accepted", "part-sent-twice", "file-dot", "file-dotdot", "file-control-char",
    "file-colon", "file-named-publish", "file-case-duplicate", "two-heroes", "duplicate-decision-id",
    "slug-leading-hyphen", "slug-trailing-hyphen", "slug-double-hyphen", "slug-only-hyphens",
}
REPLY_CASES = {
    "reply-page-sent-with-client-view": "publish-reply/1",
    "reply-page-sent-without-publish-id": "publish-reply/1",
    "reply-page-dry-run-without-client-view": "publish-reply/1",
    "reply-page-with-contact-names": "publish-reply/1",
    "reply-page-with-dashboard-counts": "publish-reply/1",
    "reply-dashboard-with-round": "publish-reply/1",
    "reply-page-screen-file-name": "publish-reply/1",
    "reply-page-media-not-a-uuid": "publish-reply/1",
    "reply-page-media-only-hyphens": "publish-reply/1",
    "answers-no-batch-with-answers": "answers/1",
    "answers-no-batch-with-hold": "answers/1",
    "answers-batch-without-answers": "answers/1",
    "answers-batch-without-hold": "answers/1",
    "answers-note-too-long": "answers/1",
    "answers-missing-replaces": "answers/1",
    "answers-no-option-no-note": "answers/1",
    "answers-replaces-no-option-no-note": "answers/1",
    "ack-request-with-contract": "ack-request/1",
    "ack-request-bad-batch-id": "ack-request/1",
    "ack-request-empty": "ack-request/1",
}


def test_every_invalid_rule_has_a_fixture():
    assert {p.name for p in INVALID} == DASHBOARD_CASES | PAGE_CASES | set(REPLY_CASES)


def test_each_case_names_its_kind():
    """The 1.0.0 cases keep expected.json byte for byte, so they carry no kind (= dashboard)."""
    for case in INVALID:
        expected = read(case / "expected.json")
        if case.name in REPLY_CASES:
            assert expected["contract"] == REPLY_CASES[case.name] and "code" not in expected, case.name
            continue
        kind = expected.get("kind", "dashboard")
        assert kind == ("dashboard" if case.name in DASHBOARD_CASES else "clarification"), case.name


def test_every_page_check_has_a_fixture():
    checks_seen = set()
    for case in INVALID:
        expected = read(case / "expected.json")
        if expected.get("kind") == "clarification":
            checks_seen |= {d["check"] for d in expected["details"]}
    assert checks_seen == {
        "schema", "contract_version", "unique_question_id", "unique_option_v", "one_rec_max",
        "bare_file_names", "max_screenshots", "screens_match_parts", "no_html_entities", "one_hero_max",
        "unique_decision_id",
    }


def test_merchants_v7_size():
    doc = read(FIXTURES / "valid" / "clarification-1-merchants-v7-size.json")
    assert len(doc["questions"]) == 6
    assert sum(len(q["options"]) for q in doc["questions"]) == 18
    assert len(page_files(doc)) == 4


def test_probate_is_converted():
    doc = read(FIXTURES / "valid" / "clarification-1-probate.json")
    assert doc["slug"] == "probate-decisions" and doc["name"] == "Probate"
    assert doc["description"].startswith("What happens to an investor")  # description beats standfirst
    assert len(doc["questions"]) == 3 and len(doc["decisions"]) == 12
    assert page_files(doc) == ["probate-355-2271.png", "probate-356-4676.png", "probate-356-5259.png"]
    never_sent = {"spec", "product", "doc_title", "eyebrow", "copy_header", "copy_noun", "stage", "events",
                  "settled", "standfirst", "title"}
    assert never_sent.isdisjoint(doc)
    assert not {"figma_file", "figma_page"} & set(doc["design"])
    assert all(set(s) <= {"file", "cap", "hero"} for s in doc["design"]["screens"])
    assert all("spec_ref" not in q for q in doc["questions"])


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


# ---- page messages ----------------------------------------------------------------------------------

def page():
    return read(FIXTURES / "valid" / "clarification-1-merchants-v7-size.json")


def page_result(doc, parts=None):
    return checks.check_publish(doc, "clarification", page_files(doc) if parts is None else parts)


def test_page_version_message_lists_accepted():
    doc = page()
    doc["contract"] = "clarification/2"
    result = page_result(doc)
    assert result["code"] == "contract_version_not_accepted"
    (d,) = result["details"]
    assert d["message"] == "clarification/2 is not accepted. This Portal accepts clarification/1."


def test_dashboard_sent_as_a_page_is_not_accepted():
    result = checks.check_publish(small(), "clarification", [])
    assert result["code"] == "contract_version_not_accepted"


def test_duplicate_question_id_names_both():
    doc = page()
    doc["questions"][3]["id"] = doc["questions"][1]["id"]
    (d,) = page_result(doc)["details"]
    assert d["check"] == "unique_question_id"
    assert "/questions/1/id" in d["message"] and "/questions/3/id" in d["message"]


def test_duplicate_option_value_names_both():
    doc = page()
    doc["questions"][2]["options"][2]["v"] = doc["questions"][2]["options"][0]["v"]
    (d,) = page_result(doc)["details"]
    assert d["check"] == "unique_option_v"
    assert "/questions/2/options/0/v" in d["message"] and "/questions/2/options/2/v" in d["message"]


def test_same_option_value_in_two_questions_is_fine():
    doc = page()
    doc["questions"][1]["options"][0]["v"] = doc["questions"][0]["options"][0]["v"]
    assert page_result(doc) is None


def test_two_recommended_names_both():
    doc = page()
    doc["questions"][0]["options"][2]["rec"] = True
    (d,) = page_result(doc)["details"]
    assert (d["check"], d["path"]) == ("one_rec_max", "/questions/0/options/2/rec")
    assert "/questions/0/options/0/rec" in d["message"]


def test_rec_false_does_not_count():
    doc = page()
    doc["questions"][0]["options"][1]["rec"] = False
    assert page_result(doc) is None


@pytest.mark.parametrize("name", ["screens/a.png", "screens\\a.png"])
def test_folder_in_file_name(name):
    doc = page()
    doc["questions"][2]["screens"][0]["file"] = name
    (d,) = checks.check_publish(doc, "clarification")["details"]
    assert (d["check"], d["path"]) == ("bare_file_names", "/questions/2/screens/0/file")
    assert name in d["message"]


def test_file_named_twice_names_both():
    doc = page()
    doc["questions"][4]["screens"][0]["file"] = doc["design"]["screens"][0]["file"]
    (d,) = page_result(doc)["details"]
    assert d["check"] == "bare_file_names"
    assert "/design/screens/0/file" in d["message"] and "/questions/4/screens/0/file" in d["message"]


def test_thirty_screenshots_pass_and_a_thirty_first_gives_one_detail():
    doc = page()
    doc["design"]["screens"] = [{"file": f"d{i}.png"} for i in range(28)]  # + 2 on Questions = 30
    assert page_result(doc) is None
    doc["questions"][0]["screens"] = [{"file": "q0.png"}, {"file": "q1.png"}]  # 32 in all
    (d,) = page_result(doc)["details"]
    assert (d["check"], d["path"]) == ("max_screenshots", "/questions/2/screens/0")  # page order: design, Q1, Q3
    assert "32" in d["message"] and "30" in d["message"]


def test_a_named_screen_with_no_part():
    doc = page()
    result = page_result(doc, ["payouts-overview.png", "payout-schedule.png", "failed-payout-banner.png"])
    assert result["code"] == "screenshot_mismatch"
    (d,) = result["details"]
    assert (d["check"], d["path"]) == ("screens_match_parts", "/questions/4/screens/0/file")
    assert "statement-email.png" in d["message"]


def test_a_part_no_screen_names():
    doc = page()
    result = page_result(doc, page_files(doc) + ["old.png"])
    assert result["code"] == "screenshot_mismatch"
    (d,) = result["details"]
    assert (d["check"], d["path"]) == ("screens_match_parts", "") and "old.png" in d["message"]


def test_parts_are_checked_only_when_given_and_only_last():
    doc = page()
    assert checks.check_publish(doc, "clarification") is None  # no parts: the skill's own check
    doc["questions"][0]["title"] = "A &amp; B"
    result = checks.check_publish(doc, "clarification", [])
    assert result["code"] == "contract_invalid"
    assert {d["check"] for d in result["details"]} == {"no_html_entities"}


def test_page_entities_allowed_in_light_html_and_url():
    doc = page()
    for key in ("description", "problem", "solution"):
        doc[key] = "<p>Fees &amp; limits</p>"
    doc["design"]["summary"] = doc["design"]["detail"] = "<p>a &mdash; b</p>"
    for field in ("body", "body2", "snag"):
        doc["questions"][3][field] = "<p>a &rsquo; b</p>"
    doc["url"] = "https://pages.example.com/p?a=1&amp;b=2"
    assert page_result(doc) is None


def test_page_entity_message_names_field():
    doc = page()
    doc["decisions"][0]["detail"] = "No cards &#8212; or wallets"
    (d,) = page_result(doc)["details"]
    assert (d["check"], d["path"]) == ("no_html_entities", "/decisions/0/detail")
    assert "/decisions/0/detail" in d["message"]


def test_a_part_sent_twice():
    doc = page()
    result = page_result(doc, page_files(doc) + ["statement-email.png"])
    assert result["code"] == "screenshot_mismatch"
    (d,) = result["details"]
    assert (d["check"], d["path"]) == ("screens_match_parts", "") and "statement-email.png" in d["message"]


@pytest.mark.parametrize("name", [".", "..", "a\x00.png", "a\x7f.png", "c:a.png", "publish", "PUBLISH",
                                  "Payouts-Overview.png"])
def test_unusable_file_names(name):
    doc = page()
    doc["design"]["screens"][1]["file"] = name
    (d,) = checks.check_publish(doc, "clarification")["details"]
    assert (d["check"], d["path"]) == ("bare_file_names", "/design/screens/1/file")


def test_file_name_entity_is_not_an_entity_error():
    doc = page()
    doc["design"]["screens"][1]["file"] = "fees&amp;limits.png"
    assert page_result(doc) is None


def test_two_heroes_name_both():
    doc = page()
    doc["design"]["screens"][1]["hero"] = True
    (d,) = page_result(doc)["details"]
    assert (d["check"], d["path"]) == ("one_hero_max", "/design/screens/1/hero")
    assert "/design/screens/0/hero" in d["message"]


def test_duplicate_decision_id_names_both():
    doc = page()
    doc["decisions"][1]["id"] = doc["decisions"][0]["id"]
    (d,) = page_result(doc)["details"]
    assert (d["check"], d["path"]) == ("unique_decision_id", "/decisions/1/id")
    assert "/decisions/0/id" in d["message"]


def test_page_with_old_settled_decisions_passes():
    doc = page()
    doc["decisions"] = [{"id": "s1", "title": "Payouts go only to a bank account"}]
    assert page_result(doc) is None


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


def clarification_schema():
    return checks.load_json("clarification-1.schema.json")


def test_clarification_leaves_have_visibility_and_objects_are_closed():
    assert visibility_problems(clarification_schema()) == []


def test_clarification_visibility_levels_are_the_agreed_ones():
    vis = {path: prop["x-visibility"] for path, prop in leaves(clarification_schema())}
    envelope = ["#/contract", "#/sent_at", "#/sent_by", "#/ba_tools_version", "#/source_commit"]
    assert sorted(p for p, v in vis.items() if v == "admin") == sorted(envelope)
    assert sorted(p for p, v in vis.items() if v == "id") == sorted(
        ["#/slug", "#/questions[]/id", "#/questions[]/options[]/v"])
    assert sorted(p for p, v in vis.items() if v == "portal") == sorted(
        ["#/store_key", "#/url", "#/design/screens[]/file", "#/design/screens[]/hero",
         "#/questions[]/screens[]/file", "#/decisions[]/id"])


def test_clarification_limits_match_the_spec():
    p = clarification_schema()["properties"]
    q = p["questions"]["items"]["properties"]
    assert p["questions"]["maxItems"] == 50
    assert (q["options"]["minItems"], q["options"]["maxItems"]) == (1, 20)
    assert p["slug"]["maxLength"] == 80
    assert checks.MAX_SCREENSHOTS == 30
    lengths = {
        "name": 120, "round": 200, "store_key": 100, "description": 1000, "problem": 1000, "solution": 1000,
    }
    assert {k: p[k]["maxLength"] for k in lengths} == lengths
    d = p["design"]["properties"]
    assert (d["label"]["maxLength"], d["more_label"]["maxLength"], d["summary"]["maxLength"],
            d["detail"]["maxLength"]) == (80, 80, 700, 3000)
    assert {k: q[k]["maxLength"] for k in ("id", "section", "title", "meta", "body", "body2", "snag",
                                           "note", "note_placeholder")} == {
        "id": 80, "section": 300, "title": 300, "meta": 300, "body": 5000, "body2": 5000, "snag": 5000,
        "note": 300, "note_placeholder": 300}
    o = q["options"]["items"]["properties"]
    assert (o["v"]["maxLength"], o["t"]["maxLength"], o["d"]["maxLength"]) == (80, 200, 1000)


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
            if is_form_picker(sub):
                continue
            assert sub.get("additionalProperties") is False, where


def is_form_picker(sub: dict) -> bool:
    """publish-reply/1's top level: it names no field itself, only picks a closed form from $defs by kind.
    It says type object only because Ajv's strict mode wants a type beside the if's "required"."""
    return ("properties" not in sub and set(sub.get("then", {})) == {"$ref"}
            and set(sub.get("else", {})) == {"$ref"})


def test_publish_reply_forms():
    schema = read(checks.CONTRACT_DIR / "publish-reply-1.schema.json")
    assert is_form_picker(schema)
    assert schema["then"] == {"$ref": "#/$defs/page"} and schema["else"] == {"$ref": "#/$defs/dashboard"}
    for form in ("page", "dashboard", "client_round", "client_screen"):
        assert schema["$defs"][form]["additionalProperties"] is False, form


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_patterns_are_ascii_and_fixed_length(path):
    for where, sub in walk_objects(read(path)):
        if "pattern" in sub:
            assert sub["pattern"].isascii(), where
            if sub["pattern"].endswith("(?![\\s\\S])"):
                # The slug: not fixed length, so it ends in "nothing follows" instead of `$`.
                assert sub.get("maxLength") is not None, where
                continue
            # Python's `$` also matches before a final line break; a fixed length makes that harmless.
            assert sub.get("minLength") == sub.get("maxLength") is not None, where


@pytest.mark.parametrize("slug,ok", [
    ("probate-decisions", True), ("a", True), ("x" * 80, True),
    ("Probate", False), ("two words", False), ("trailing\n", False), ("", False), ("x" * 81, False),
    ("caf\u00e9", False), ("-a", False), ("a-", False), ("a--b", False), ("-", False), ("a-b-c", True),
])
def test_slug_rule(slug, ok):
    doc = read(FIXTURES / "valid" / "clarification-1-merchants-v7-size.json")
    doc["slug"] = slug
    assert (checks.check_publish(doc, "clarification") is None) == ok


def test_limits_match_the_spec():
    p = dashboard_schema()["properties"]
    assert p["features"]["maxItems"] == 300
    assert p["items"]["maxItems"] == 1000
    assert p["client_contacts"]["maxItems"] == 200
    assert p["features"]["items"]["properties"]["stage"]["enum"] == ["concept", "spec", "ready", "dev", "qa", "done"]


def test_index_names_existing_schemas():
    idx = checks.index()
    assert idx["contract_folder"] == "1.1.0"
    assert idx["accepted"] == ["dashboard/1", "clarification/1"]
    assert set(idx["schemas"]) == {"dashboard/1", "clarification/1", "publish-reply/1", "status/1",
                                   "answers/1", "ack-request/1", "ack/1"}
    assert {p.name for p in SCHEMAS} == set(idx["schemas"].values())
    for contract, name in idx["schemas"].items():
        assert (checks.CONTRACT_DIR / name).is_file(), contract
        schema = read(checks.CONTRACT_DIR / name)
        if contract == "ack-request/1":  # the ack request carries no contract field (AD-12)
            assert "contract" not in schema["properties"]
        elif contract == "publish-reply/1":
            for form in schema["$defs"]["dashboard"], schema["$defs"]["page"]:
                assert form["properties"]["contract"]["const"] == contract
        else:
            assert schema["properties"]["contract"]["const"] == contract


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


def test_client_round_holds_no_portal_fields():
    view = read(FIXTURES / "valid" / "publish-reply-1-page-dry-run.json")["client_view"]
    text = json.dumps(view)
    for portal_only in ('"store_key"', '"url"', '"file"', '"hero"', '"contract"', '"sent_by"'):
        assert portal_only not in text
    assert all("id" not in d for d in view["decisions"])
    assert all(s["media"] is None for s in view["design"]["screens"])
    reply = read(FIXTURES / "valid" / "publish-reply-1-page-dry-run.json")
    assert reply["round"]["new"] is True  # a dry run before the first send: the Round would be new
    stored = copy.deepcopy(view)
    stored["design"]["screens"][0]["media"] = "/media/019a2b10-7e2c-7a35-8c4d-5e6f7a8b9c0d"
    assert checks.check_reply({**reply, "client_view": stored}, "publish-reply/1") == []
