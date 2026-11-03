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
SCHEMA_BY_PREFIX = {"ack-request-1": "ack-request/1", "reserve-request-1": "reserve-request/1",
                    "connect-request-1": "connect-request/1"}


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
    # dashboard/2 (contract 1.2.0)
    "v2-duplicate-area-id", "v2-duplicate-feature-id", "v2-duplicate-topic-id", "v2-topic-id-is-a-feature-id",
    "v2-duplicate-item-key", "v2-duplicate-card-id", "v2-duplicate-ticket-in-card", "v2-unknown-card-area",
    "v2-unknown-feature-area", "v2-unknown-parent", "v2-unknown-card-feature", "v2-unknown-release",
    "v2-html-entity", "v2-products-field", "v2-prod-field", "v2-missing-jira-base",
    "v2-release-name-too-long", "v2-ticket-summary-too-long", "v2-feature-summary-too-long",
    "v2-too-many-open-tickets", "v2-bad-ticket-key", "v2-bad-card-kind", "v2-version-not-accepted",
    # Story 3.7 review fixes
    "v2-unknown-topic-area", "v2-duplicate-release-name", "v2-duplicate-special", "v2-duplicate-ticket-in-feature",
    "v2-duplicate-open-ticket", "v2-feature-card-without-feature", "v2-epic-card-with-feature",
    "v2-other-card-with-epic", "v2-answered-over-total", "v2-jira-base-javascript", "v2-jira-base-http",
    # clarification_pages (contract 1.3.0)
    "v2-duplicate-page-slug", "v2-bad-page-slug", "v2-too-many-pages",
    # the optional 1.4.0 fields
    "v2-hot-not-yes-no", "v2-stage-why-too-long", "v2-area-how-empty", "v2-ticket-updated-not-utc",
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
    "reply-pages-removed-without-title": "publish-reply/1",
    "reply-page-with-pages-removed": "publish-reply/1",
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
    # answers/2 and reserve-request/1 (contract 1.4.0)
    "answers2-missing-updates": "answers/2",
    "answers2-no-batch-with-updates": "answers/2",
    "answers2-batch-with-nothing": "answers/2",
    "answers2-update-bad-item-key": "answers/2",
    "answers2-update-todo-item": "answers/2",
    "answers2-update-note-too-long": "answers/2",
    "answers2-update-empty-note": "answers/2",
    "answers2-update-missing-resolved": "answers/2",
    "answers2-sent-as-answers1": "answers/1",
    "reserve-request-empty": "reserve-request/1",
    "reserve-request-empty-accept": "reserve-request/1",
    "reserve-request-accept-twice": "reserve-request/1",
    "reserve-request-with-contract": "reserve-request/1",
    # connect-request/1 and connect/1 (contract 1.5.0)
    "connect-request-with-contract": "connect-request/1",
    "connect-request-missing-code": "connect-request/1",
    "connect-request-code-look-alike": "connect-request/1",
    "connect-request-code-too-long": "connect-request/1",
    "connect-request-code-dash-in-wrong-place": "connect-request/1",
    "connect-request-code-trailing-newline": "connect-request/1",
    "connect-request-empty-label": "connect-request/1",
    "connect-request-label-too-long": "connect-request/1",
    "connect-missing-key": "connect/1",
    "connect-key-too-short": "connect/1",
    "connect-key-not-base64url": "connect/1",
    "connect-last4-too-long": "connect/1",
    "connect-project-bad-id": "connect/1",
    "connect-project-empty-name": "connect/1",
    "connect-unknown-field": "connect/1",
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
    doc["contract"] = "dashboard/3"
    (d,) = checks.check_publish(doc)["details"]
    assert d["message"] == "dashboard/3 is not accepted. This Portal accepts dashboard/1, dashboard/2."


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
        "bad_request": 400, "connect_code_invalid": 400, "invalid_key": 401, "batch_unknown": 404, "project_archived": 409,
        "round_has_answers": 409, "batch_expired": 409, "payload_too_large": 413,
        "contract_version_not_accepted": 422, "contract_invalid": 422, "screenshot_mismatch": 422,
        "too_many_tries": 429, "server_error": 500,
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
    assert idx["contract_folder"] == "1.5.0"
    assert idx["accepted"] == ["dashboard/1", "dashboard/2", "clarification/1"]
    assert set(idx["schemas"]) == {"dashboard/1", "dashboard/2", "clarification/1", "publish-reply/1", "status/1",
                                   "answers/1", "answers/2", "reserve-request/1", "ack-request/1", "ack/1",
                                   "connect-request/1", "connect/1"}
    assert {p.name for p in SCHEMAS} == set(idx["schemas"].values())
    for contract, name in idx["schemas"].items():
        assert (checks.CONTRACT_DIR / name).is_file(), contract
        schema = read(checks.CONTRACT_DIR / name)
        if contract in ("ack-request/1", "reserve-request/1", "connect-request/1"):  # requests carry no contract field (AD-12)
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


# ---- dashboard/2 (Story 3.7) ------------------------------------------------------------------------

def dashboard2_schema():
    return checks.load_json("dashboard-2.schema.json")


def small2():
    return read(FIXTURES / "valid" / "dashboard-2-small.json")


def real2():
    return read(FIXTURES / "valid" / "dashboard-2-real-size.json")


def test_real_size_is_the_easy_payday_upper_bound():
    doc = real2()
    assert len(doc["areas"]) == 48 and all(len(a["jira"]["open_tickets"]) == 5 for a in doc["areas"])
    assert (len(doc["features"]), len(doc["topics"]), len(doc["items"]), len(doc["releases"])) == (18, 10, 70, 60)
    assert len(doc["cards"]) == 436
    assert [sum(c["kind"] == k for c in doc["cards"]) for k in ("feature", "epic", "other")] == [29, 290, 117]
    assert sum(len(c["tickets"]) for c in doc["cards"]) == 2042
    assert max(len(f["summary"]) for f in doc["features"]) == 4598
    assert max(len(r["name"]) for r in doc["releases"]) == 130
    text = json.dumps(doc)
    assert "@" not in text  # no email address anywhere
    assert checks.check_publish(doc) is None
    body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(body) < 5 * 1024 * 1024


def test_every_dashboard2_check_has_a_fixture():
    checks_seen = set()
    for case in INVALID:
        if case.name.startswith("v2-"):
            checks_seen |= {d["check"] for d in read(case / "expected.json")["details"]}
    assert checks_seen == {
        "schema", "contract_version", "unique_area_id", "unique_feature_id", "unique_topic_id", "unique_item_key",
        "unique_card_id", "unique_release_name", "unique_special", "unique_ticket_in_list", "known_area",
        "known_parent", "known_card_feature", "known_release", "card_kind_fields", "answered_in_range",
        "no_html_entities", "unique_page_slug",
    }


def test_valid_small_file_has_an_item_under_a_topic():
    doc = small2()
    topics = {t["id"] for t in doc["topics"]}
    assert any(i["parent"] in topics for i in doc["items"])
    assert checks.check_publish(doc) is None


def test_dashboard2_item_key_includes_the_parent():
    """sha1("<kind>|<parent>|<title>"): two Items with one title under two parents get two keys."""
    import hashlib
    for doc in (small2(), real2()):
        for it in doc["items"]:
            raw = f'{it["kind"]}|{it["parent"]}|{it["title"].strip()}'
            assert it["key"] == hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def test_dashboard2_jira_text_may_hold_entities():
    """Text copied from Jira never blocks a send; the Portal shows it as escaped plain text."""
    doc = small2()
    jira = doc["areas"][0]["jira"]
    jira["open_tickets"][0]["summary"] = "Fix &amp; ship"
    jira["open_tickets"][0]["status"] = "To&nbsp;Do"
    jira["description"] = "Fees &amp; limits"
    doc["areas"][0]["name"] = "Fees &amp; limits"
    doc["features"][1]["tickets"][0]["summary"] = "A &lt;b&gt; tag"
    doc["cards"][2]["title"] = "Epic &mdash; payouts"
    assert checks.check_publish(doc) is None


def test_jira_base_must_be_https():
    for bad in ("javascript:alert(1)", "http://example.atlassian.net", "https://", "https://a b"):
        doc = small2()
        doc["jira_base"] = bad
        result = checks.check_publish(doc)
        assert result is not None and ("schema", "/jira_base") in {(d["check"], d["path"]) for d in result["details"]}, bad


def test_dashboard2_leaves_have_visibility_and_objects_are_closed():
    assert visibility_problems(dashboard2_schema()) == []


def test_dashboard2_visibility_levels_are_the_agreed_ones():
    vis = {path: prop["x-visibility"] for path, prop in leaves(dashboard2_schema())}
    assert sorted(p for p, v in vis.items() if v == "admin") == sorted(
        ["#/contract", "#/sent_at", "#/sent_by", "#/ba_tools_version", "#/source_commit"])
    assert sorted(p for p, v in vis.items() if v == "id") == sorted(
        ["#/areas[]/id", "#/features[]/id", "#/features[]/area", "#/topics[]/id", "#/topics[]/area",
         "#/items[]/key", "#/items[]/parent", "#/cards[]/id", "#/cards[]/area", "#/cards[]/feature"])
    assert sorted(p for p, v in vis.items() if v == "portal") == sorted(
        ["#/features[]/clar_url", "#/client_contacts[]/name", "#/client_contacts[]/email",
         "#/client_contacts[]/slack", "#/clarification_pages"])
    # Decision 1 and 3: ticket keys, assignees, and Item who, since and kind are shown; so is jira_base.
    for p in ("#/jira_base", "#/items[]/who", "#/items[]/since", "#/items[]/kind", "#/cards[]/tickets[]/key",
              "#/cards[]/tickets[]/assignee", "#/areas[]/jira/open_tickets[]/key"):
        assert vis[p] == "client", p


def test_dashboard2_has_no_product_field():
    text = json.dumps(dashboard2_schema())
    assert '"prod"' not in text and '"products"' not in text and '"product"' not in text


def test_dashboard2_limits_match_the_spec():
    p = dashboard2_schema()["properties"]
    maxima = {"areas": 1000, "features": 1000, "topics": 1000, "items": 5000, "releases": 2000, "cards": 10000,
              "client_contacts": 200}
    assert {k: p[k]["maxItems"] for k in maxima} == maxima
    a = p["areas"]["items"]["properties"]
    assert (a["id"]["maxLength"], a["name"]["maxLength"]) == (300, 255)
    j = a["jira"]["properties"]
    assert (j["description"]["maxLength"], j["shipped"]["maxItems"], j["open_tickets"]["maxItems"]) == (5000, 20, 20)
    f = p["features"]["items"]["properties"]
    assert (f["title"]["maxLength"], f["short"]["maxLength"], f["summary"]["maxLength"]) == (500, 100, 20000)
    assert (f["open"]["maxItems"], f["open"]["items"]["maxLength"], f["tickets"]["maxItems"]) == (200, 2000, 5000)
    i = p["items"]["items"]["properties"]
    assert (i["who"]["maxLength"], i["title"]["maxLength"], i["text"]["maxLength"],
            i["how_to_send"]["maxLength"]) == (255, 500, 10000, 2000)
    assert p["releases"]["items"]["properties"]["name"]["maxLength"] == 255
    c = p["cards"]["items"]["properties"]
    assert (c["title"]["maxLength"], c["tickets"]["maxItems"]) == (255, 5000)
    t = c["tickets"]["items"]["properties"]
    assert (t["key"]["maxLength"], t["summary"]["maxLength"], t["status"]["maxLength"],
            t["assignee"]["maxLength"]) == (50, 255, 100, 255)
    assert p["jira_base"]["maxLength"] == 2000


@pytest.mark.parametrize("listname,limit", [
    ("areas", 1000), ("features", 1000), ("topics", 1000), ("items", 5000), ("releases", 2000), ("cards", 10000),
])
def test_dashboard2_list_limits(listname, limit):
    """One over each list limit fails the schema at the list (no fixture: the files would be large)."""
    doc = small2()
    doc[listname] = (doc[listname] * (limit // len(doc[listname]) + 1))[:limit + 1]
    result = checks.check_publish(doc)
    assert result["code"] == "contract_invalid"
    assert ("schema", f"/{listname}") in {(d["check"], d["path"]) for d in result["details"]}


def test_dashboard2_255_character_release_name_passes():
    doc = small2()
    old, new = doc["releases"][0]["name"], "R" * 255
    doc["releases"][0]["name"] = new
    for card in doc["cards"]:
        if card["release"] == old:
            card["release"] = new
    assert checks.check_publish(doc) is None


def test_dashboard2_not_planned_card_and_shared_ticket_pass():
    doc = small2()
    doc["cards"][0]["release"] = None
    doc["cards"][1]["tickets"].append(copy.deepcopy(doc["cards"][0]["tickets"][0]))  # a ticket on two cards
    assert checks.check_publish(doc) is None


def test_dashboard2_entities_allowed_in_light_html_and_jira_base():
    doc = small2()
    doc["features"][0]["summary"] = "<p>Fees &amp; limits</p>"
    doc["items"][0]["text"] = "<p>a &amp; b</p>"
    doc["jira_base"] = "https://example.atlassian.net/?a=1&amp;b=2"
    assert checks.check_publish(doc) is None


def test_dashboard2_known_messages_name_the_value():
    doc = small2()
    doc["items"][2]["parent"] = "no-such-feature"
    (d,) = checks.check_publish(doc)["details"]
    assert d["check"] == "known_parent" and '"no-such-feature"' in d["message"] and "/items/2/parent" in d["message"]


def test_dashboard2_ticket_twice_names_both():
    doc = small2()
    doc["cards"][2]["tickets"][2]["key"] = doc["cards"][2]["tickets"][0]["key"]
    (d,) = checks.check_publish(doc)["details"]
    assert "/cards/2/tickets/0/key" in d["message"] and "/cards/2/tickets/2/key" in d["message"]


def test_dashboard1_fields_are_refused_in_dashboard2():
    doc = small2()
    doc["release_rows"] = []
    result = checks.check_publish(doc)
    assert ("schema", "/release_rows") in {(d["check"], d["path"]) for d in result["details"]}


def test_missing_contract_is_checked_as_the_oldest_version():
    """A missing contract is reported by the dashboard/1 schema, so adding dashboard/2 changed nothing there."""
    doc = small2()
    del doc["contract"]
    paths = {d["path"] for d in checks.check_publish(doc)["details"]}
    assert "/contract" in paths and "/jira_base" in paths  # jira_base is unknown to dashboard/1


def test_reply_holds_either_view():
    reply = read(FIXTURES / "valid" / "publish-reply-1-dashboard-2-dry-run.json")
    assert checks.check_reply(reply, "publish-reply/1") == []
    v1_view = read(FIXTURES / "valid" / "publish-reply-1-dry-run.json")["client_view"]
    assert checks.check_reply({**reply, "client_view": v1_view}, "publish-reply/1") == []
    broken = copy.deepcopy(reply["client_view"])
    broken["release_rows"] = []  # a v1 field in a v2 view
    assert checks.check_reply({**reply, "client_view": broken}, "publish-reply/1") != []
    leaked = copy.deepcopy(reply["client_view"])
    leaked["features"][0]["clar_url"] = "https://pages.example.com/x/"
    assert checks.check_reply({**reply, "client_view": leaked}, "publish-reply/1") != []
    schema = read(checks.CONTRACT_DIR / "publish-reply-1.schema.json")
    for form in ("client_dashboard_1", "client_dashboard_2", "client_ticket"):
        assert schema["$defs"][form]["additionalProperties"] is False, form


# ---- clarification_pages (contract 1.3.0) -------------------------------------------------------------

def test_page_list_is_optional():
    """Without the list nothing changes for older senders; an empty list is allowed (every page goes)."""
    doc = small2()
    assert "clarification_pages" not in doc and checks.check_publish(doc) is None
    doc["clarification_pages"] = []
    assert checks.check_publish(doc) is None
    assert "clarification_pages" not in dashboard2_schema()["required"]


def test_page_list_uses_the_page_slug_rule():
    slug_rule = checks.load_json("clarification-1.schema.json")["properties"]["slug"]
    item = dashboard2_schema()["properties"]["clarification_pages"]["items"]
    assert (item["pattern"], item["minLength"], item["maxLength"]) == (
        slug_rule["pattern"], slug_rule["minLength"], slug_rule["maxLength"])
    assert dashboard2_schema()["properties"]["clarification_pages"]["maxItems"] == 1000
    for bad in ("Payouts", "two words", "trailing\n", "", "a--b", "x" * 81):
        doc = small2()
        doc["clarification_pages"] = [bad]
        assert checks.check_publish(doc) is not None, bad


def test_page_slug_twice_names_both():
    doc = small2()
    doc["clarification_pages"] = ["payouts", "probate-decisions", "payouts"]
    details = checks.check_publish(doc)["details"]
    assert [(d["check"], d["path"]) for d in details] == [("unique_page_slug", "/clarification_pages/2")]
    assert "/clarification_pages/0" in details[0]["message"]


def test_page_list_is_refused_in_dashboard1():
    doc = read(FIXTURES / "valid" / "dashboard-1-small.json")
    doc["clarification_pages"] = ["payouts"]
    result = checks.check_publish(doc)
    assert ("schema", "/clarification_pages") in {(d["check"], d["path"]) for d in result["details"]}


def test_pages_removed_is_on_dashboard_replies_only():
    dry = read(FIXTURES / "valid" / "publish-reply-1-dashboard-2-pages-removed-dry-run.json")
    sent = read(FIXTURES / "valid" / "publish-reply-1-dashboard-2-pages-removed.json")
    assert dry["dry_run"] is True and dry["pages_removed"]
    assert sent["dry_run"] is False and sent["pages_removed"]
    for reply in (dry, sent):
        assert checks.check_reply(reply, "publish-reply/1") == []
        assert checks.check_reply({**reply, "pages_removed": []}, "publish-reply/1") == []
    page = read(FIXTURES / "valid" / "publish-reply-1-page-sent.json")
    assert checks.check_reply({**page, "pages_removed": []}, "publish-reply/1") != []


# ---- contract 1.4.0: hot, stage_why, area_how, ticket updated; answers/2; reserve-request/1 -----------

NEW_FIELDS = {"hot", "stage_why", "area_how", "updated"}


def test_older_dashboard2_sends_without_the_new_fields_still_pass():
    for name in ("dashboard-2-small.json", "dashboard-2-real-size.json", "dashboard-2-with-pages.json"):
        doc = read(FIXTURES / "valid" / name)
        assert NEW_FIELDS.isdisjoint(re_keys(doc)), name
        assert checks.check_publish(doc) is None, name


def re_keys(value) -> set[str]:
    """Every field name anywhere in a document."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in re_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in re_keys(v)}
    return set()


def test_the_new_fields_fixture_holds_every_new_field():
    doc = read(FIXTURES / "valid" / "dashboard-2-with-1-4-fields.json")
    assert NEW_FIELDS <= re_keys(doc)
    updated = [t["updated"] for a in doc["areas"] for t in a["jira"].get("open_tickets", []) if "updated" in t]
    assert {len(u) for u in updated} == {10, 24}                      # a date and a UTC time both pass
    assert {it.get("hot") for it in doc["items"]} == {True, False, None}
    assert checks.check_publish(doc) is None


def test_new_fields_are_client_and_optional():
    schema = dashboard2_schema()["properties"]
    feature = schema["features"]["items"]
    item = schema["items"]["items"]
    ticket = schema["areas"]["items"]["properties"]["jira"]["properties"]["open_tickets"]["items"]
    for obj, field in ((feature, "stage_why"), (feature, "area_how"), (item, "hot"), (ticket, "updated")):
        assert field not in obj["required"], field
        assert obj["properties"][field]["x-visibility"] == "client", field
    assert feature["properties"]["stage_why"]["maxLength"] == 400
    assert feature["properties"]["area_how"]["maxLength"] == 200


def test_new_fields_are_refused_in_dashboard1():
    doc = read(FIXTURES / "valid" / "dashboard-1-small.json")
    doc["items"][0]["hot"] = True
    result = checks.check_publish(doc)
    assert ("schema", "/items/0/hot") in {(d["check"], d["path"]) for d in result["details"]}


def test_answers2_update_keys_are_the_ba_page_keys():
    """item.key = sha1("<kind>|<title>"), the key sync.py matches on (not the dashboard/2 key)."""
    import hashlib
    batch = read(FIXTURES / "valid" / "answers-2-batch.json")
    assert batch["answers"] and batch["updates"]
    for u in batch["updates"]:
        it = u["item"]
        assert it["key"] == hashlib.sha1(f'{it["kind"]}|{it["title"].strip()}'.encode("utf-8")).hexdigest()[:12]
    order = [(u["sent_at"], u["id"]) for u in batch["updates"]]
    assert order == sorted(order)


def test_answers2_batch_may_hold_only_updates_or_only_answers():
    batch = read(FIXTURES / "valid" / "answers-2-batch.json")
    assert checks.check_reply(read(FIXTURES / "valid" / "answers-2-updates-only.json"), "answers/2") == []
    assert checks.check_reply({**batch, "updates": []}, "answers/2") == []
    nothing = read(FIXTURES / "valid" / "answers-2-nothing-to-fetch.json")
    assert nothing["batch_id"] is None and nothing["answers"] == [] and nothing["updates"] == []


def test_answers2_answers_are_the_answers1_answers():
    one = read(checks.CONTRACT_DIR / "answers-1.schema.json")
    two = read(checks.CONTRACT_DIR / "answers-2.schema.json")
    assert one["properties"]["answers"] == two["properties"]["answers"]
    assert set(two["required"]) == set(one["required"]) | {"updates"}


def test_reserve_request_says_which_versions_it_reads():
    assert checks.check_reply({"accept": ["answers/1", "answers/2"]}, "reserve-request/1") == []
    assert checks.check_reply({"accept": ["answers/1"]}, "reserve-request/1") == []
    assert checks.check_reply({"accept": [f"answers/{n}" for n in range(6)]}, "reserve-request/1") != []


# ---- contract 1.5.0: connect a repo with a one-time code -----------------------------------------------

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def connect_request(code: str, label: str = "acme-docs · Sample BA") -> list[dict]:
    return checks.check_reply({"code": code, "label": label}, "connect-request/1")


@pytest.mark.parametrize("code", ["K7P4XM", "K7P-4XM", "k7p-4xm", "k7P4xM", "222-ZZZ", "ABCDEF"])
def test_connect_code_with_or_without_the_dash_in_any_case_passes(code):
    assert connect_request(code) == []


@pytest.mark.parametrize("code", ["K7P 4XM", "K7P--4XM", "-K7P4XM", "K7P4X", "K7P4XMA", "K7P-4X", " K7P4XM",
                                  "0OI1L2", "K7P-4XO", "K7P-4XL", "K7P-4X1", "K7P‐4XM"])
def test_connect_code_outside_the_rule_fails(code):
    assert ("schema", "/code") in {(d["check"], d["path"]) for d in connect_request(code)}


def test_connect_code_alphabet_has_no_look_alikes():
    for ch in CODE_ALPHABET:
        assert connect_request(ch * 6) == [], ch
        assert connect_request(ch.lower() * 6) == [], ch
    for ch in "01ILO":
        assert connect_request(ch * 6) != [], ch
        assert connect_request(ch.lower() * 6) != [], ch


def test_connect_label_limits():
    assert connect_request("K7P4XM", "x" * 100) == []
    assert connect_request("K7P4XM", "x") == []
    assert connect_request("K7P4XM", "x" * 101) != []


def test_connect_reply_last4_is_the_keys_last4():
    reply = read(FIXTURES / "valid" / "connect-1.json")
    assert reply["key_last4"] == reply["key"][-4:]
    assert len(reply["key"]) == 43


def test_connect_reply_needs_every_field():
    reply = read(FIXTURES / "valid" / "connect-1.json")
    for field in ("contract", "project", "key", "key_last4"):
        doc = {k: v for k, v in reply.items() if k != field}
        assert ("schema", f"/{field}") in {(d["check"], d["path"]) for d in checks.check_reply(doc, "connect/1")}


def test_connect_errors_are_in_errors_json():
    errors = checks.load_json("errors.json")
    assert errors["connect_code_invalid"] == {
        "status": 400, "message": "This code does not work. Ask an Admin for a new one."}
    assert errors["too_many_tries"]["status"] == 429
