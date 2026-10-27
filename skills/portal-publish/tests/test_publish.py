"""Tests for publish.py (portal-publish dashboard). One test (or one group) per row of the Story 3.4 matrix.

The Portal is faked with httpx.MockTransport, the build step is stubbed, and each test runs in a temp git repo
copied from tests/publish/project/.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest
import yaml

import checks
import publish

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "publish" / "project"
VALID = checks.CONTRACT_DIR / "fixtures" / "valid"
ERRORS = json.loads((checks.CONTRACT_DIR / "errors.json").read_text(encoding="utf-8"))
KEY = "pk_test_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
URL = "http://portal.test"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


# ---- helpers (no conftest.py: Story 4.1 may add one) --------------------------------------------------

class FakePortal:
    """Answers like the Portal: the contract's own reply fixtures, or an error envelope."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.error: tuple[int, dict] | None = None
        self.raw: tuple[int, bytes] | None = None
        self.raise_exc: Exception | None = None
        self.dry = read(VALID / "publish-reply-1-dry-run.json")
        self.sent = read(VALID / "publish-reply-1-sent.json")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.raw is not None:
            return httpx.Response(self.raw[0], content=self.raw[1], headers={"Content-Type": "text/html"})
        if self.error is not None:
            return httpx.Response(self.error[0], json=self.error[1])
        dry = request.url.params.get("dry_run") == "1"
        return httpx.Response(200, json=self.dry if dry else self.sent)


@pytest.fixture
def portal(monkeypatch):
    fake = FakePortal()
    monkeypatch.setattr(publish, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return fake


@pytest.fixture
def builds(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(publish, "run_build", lambda root, refresh: calls.append(refresh))
    return calls


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    git(root, "init", "-q")
    git(root, "config", "user.name", "Sample BA")
    git(root, "config", "user.email", "ba@example.com")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text(f"# Portal\nPORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def run(capsys, root: Path, *args: str) -> tuple[int, dict, str]:
    code = publish.main([*args, "--root", str(root)])
    printed = capsys.readouterr().out
    assert KEY not in printed, "the key must never be printed"
    return code, json.loads(printed.strip().splitlines()[-1]), printed


def edit_yaml(path: Path, change) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def payload_of(root: Path) -> dict:
    prof = yaml.safe_load((root / publish.PROFILE).read_text(encoding="utf-8"))
    return publish.build_payload(root, prof)[0]


# ---- Happy path --------------------------------------------------------------------------------------

def test_happy_path_plan_then_send(capsys, project, portal, builds):
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0 and plan["ok"] is True, plan
    assert builds == [False]
    assert len(portal.requests) == 1
    dry = portal.requests[0]
    assert str(dry.url) == f"{URL}/api/v1/publish/dashboard?dry_run=1"
    assert dry.headers["Authorization"] == f"Bearer {KEY}"
    assert dry.headers["Content-Type"] == "application/json"
    payload_file = Path(plan["payload"])
    assert payload_file.exists() and project not in payload_file.parents
    assert payload_file.read_bytes() == dry.content

    shown = plan["client_list"]
    for words in ("Waiting on you (1):", "Next-call agenda (0):", "Sign-up with phone number (Sign-up)",
                  "Spec & design", "Open question: Which employers first?", "Clarification page: Questions coming",
                  "Short answer is fine.", "How to send: Reply in Slack.",
                  "Client contacts (3): Maria Lopez, Tom Baker, Priya Shah"):
        assert words in shown, words
    assert "<p" not in shown

    code, sent, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
    assert code == 0 and sent["ok"] is True, sent
    assert len(portal.requests) == 2
    real = portal.requests[1]
    assert str(real.url) == f"{URL}/api/v1/publish/dashboard"
    assert real.content == dry.content, "the dry run and the real send carry the same bytes"
    assert sent["sent"] == "Dashboard"
    assert sent["counts"] == {"features": 18, "items": 148, "client_contacts": 3}
    assert sent["publish_id"] == portal.sent["publish_id"]
    assert sent["received_at"] == portal.sent["received_at"]
    assert portal.sent["publish_id"] in sent["report"] and "18 Features, 148 Items, 3 Client contacts" in sent["report"]
    assert not payload_file.exists()


def test_payload_passes_the_contract_and_holds_only_contract_fields(project):
    payload = payload_of(project)
    assert checks.check_publish(payload) is None
    feature_fields = {"id", "title", "short", "summary", "open", "clar_url", "stage", "map_area", "releases",
                      "done_date"}
    item_fields = {"key", "kind", "feature", "who", "since", "title", "text", "how_to_send"}
    assert set(payload) <= {"contract", "sent_at", "sent_by", "ba_tools_version", "source_commit", "features",
                            "items", "areas", "release_rows", "client_contacts"}
    assert all(set(f) <= feature_fields for f in payload["features"])
    assert all(set(i) <= item_fields for i in payload["items"])
    assert all(set(c) <= {"name", "email", "slack"} for c in payload["client_contacts"])


def test_envelope(project):
    payload = payload_of(project)
    assert payload["contract"] == "dashboard/1"
    assert payload["sent_by"] == "Sample BA"
    assert payload["ba_tools_version"] == "0.8.0"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True).stdout.strip()
    assert payload["source_commit"] == head
    assert len(payload["sent_at"]) == 24 and payload["sent_at"].endswith("Z")


def test_envelope_without_commit_or_profile_version(tmp_path):
    project = tmp_path / "no-commit"
    shutil.copytree(PROJECT, project)
    git(project, "init", "-q")
    git(project, "config", "user.name", "Sample BA")
    edit_yaml(project / publish.PROFILE, lambda d: d.pop("ba_tools_version"))
    payload = payload_of(project)
    assert "source_commit" not in payload
    assert payload["ba_tools_version"]            # from ba-setup's tools_version()


def test_map_facts_areas_releases_and_dates(project):
    payload = payload_of(project)
    assert payload["areas"] == ["Onboarding", "Back office", "Quiet area", "No area"]
    assert payload["release_rows"] == [{"name": "1.5", "released": False}, {"name": "1.4", "released": True},
                                       {"name": "2.0", "released": False}]
    by_id = {f["id"]: f for f in payload["features"]}
    assert by_id["sign-up"]["releases"] == ["1.5", "1.4"]
    assert by_id["sign-up"]["map_area"] == "Onboarding" and by_id["sign-up"]["stage"] == "spec"
    assert by_id["identity-check"]["map_area"] == "No area"
    assert by_id["identity-check"]["done_date"] == "2026-10-01"
    assert "releases" not in by_id["identity-check"]
    key = publish.item_key("agenda", "Decide the limit for identity check")
    assert key in {i["key"] for i in payload["items"]}


def test_long_release_names_are_cut_the_same_in_rows_and_features():
    long = "Release 1.9.0 - " + "Application expiration; Investment Preferences; Auto logout; " * 3
    data = {"board": {"releases": {"p": [{"name": long, "released": True}, {"name": "2.0"}]},
                      "cards": [{"kind": "feature", "fid": "f1", "row": long}, {"kind": "feature", "fid": "f1", "row": "2.0"}]}}
    _, _, rows, releases = publish.map_facts(data)
    cut = rows[0]["name"]
    assert len(cut) == publish.RELEASE_NAME_MAX and cut.endswith("…") and long.startswith(cut[:-1])
    assert rows[1]["name"] == "2.0"
    assert releases["f1"] == [cut, "2.0"]
    assert publish.release_name("x" * publish.RELEASE_NAME_MAX) == "x" * publish.RELEASE_NAME_MAX


# ---- BA says no --------------------------------------------------------------------------------------

def test_ba_says_no_discards_the_payload(capsys, project, portal, builds):
    _, plan, _ = run(capsys, project, "dashboard", "plan")
    payload_file = Path(plan["payload"])
    code, result, _ = run(capsys, project, "dashboard", "discard", "--payload", str(payload_file))
    assert code == 0 and result["sent"] is None
    assert not payload_file.exists()
    assert len(portal.requests) == 1            # only the dry run


# ---- No settings -------------------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["no-portal", "no-env", "no-key", "no-profile"])
def test_missing_settings_stop(capsys, project, portal, builds, case):
    if case == "no-portal":
        edit_yaml(project / publish.PROFILE, lambda d: d["tools"].pop("portal"))
    elif case == "no-env":
        (project / ".env").unlink()
    elif case == "no-key":
        (project / ".env").write_text("OTHER=1\n", encoding="utf-8")
    else:
        (project / publish.PROFILE).unlink()
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and result["ok"] is False
    assert "Run `ba-setup project`" in result["error"]
    assert portal.requests == [] and builds == []


# ---- .env not ignored --------------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["not-in-gitignore", "tracked"])
def test_env_not_ignored_stops(capsys, project, portal, builds, case):
    if case == "not-in-gitignore":
        (project / ".gitignore").write_text("", encoding="utf-8")
    else:
        git(project, "add", "-f", ".env")
        git(project, "commit", "-qm", "oops")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert ".env is not ignored by git" in result["error"]
    assert portal.requests == [] and builds == []


def test_env_not_ignored_stops_send_too(capsys, project, portal, tmp_path):
    payload_file = publish.write_payload(publish.encode(payload_of(project)))
    (project / ".gitignore").write_text("", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
    assert code == 1 and ".env is not ignored" in result["error"]
    assert portal.requests == []
    assert not payload_file.exists()


# ---- Filter ------------------------------------------------------------------------------------------

def test_filter(project):
    payload = payload_of(project)
    ids = [f["id"] for f in payload["features"]]
    assert ids == ["sign-up", "identity-check"]                        # client: false Feature absent
    titles = [i["title"] for i in payload["items"]]
    assert "Back office question" not in titles                        # Item of a hidden Feature
    assert "BA to-do never sent" not in titles                         # to-do
    assert "Already answered" not in titles                            # done Item
    assert "Internal only item" not in titles                          # client: false Item
    assert "Refund rules" in titles                                    # under a topic: sent as written
    sign_up = payload["features"][0]
    assert sign_up["summary"] == '<p class="lead">Sign up with your phone number.</p>'   # client_s replaces s
    assert sign_up["open"] == ["Which employers get it first?"]       # empty string left out
    assert sign_up["clar_url"] == "https://pages.example.com/clarifications/sign-up/"
    assert "short" not in payload["features"][1]                       # empty string left out
    first = payload["items"][0]
    assert first["text"] == "<p>A short answer is fine.</p>" and first["kind"] == "waiting"
    assert first["since"] == "2026-10-01" and first["how_to_send"] == "Reply in Slack."
    agenda = [i for i in payload["items"] if i["kind"] == "agenda"]
    assert len(agenda) == 1 and "text" not in agenda[0]


def test_left_out_counts_in_plan(capsys, project, portal, builds):
    _, plan, _ = run(capsys, project, "dashboard", "plan")
    assert plan["left_out"] == {"features": 1, "items": 4}             # 3 Items + 1 to-do


# ---- Contacts ----------------------------------------------------------------------------------------

def test_contacts_from_the_profile(project):
    assert payload_of(project)["client_contacts"] == [
        {"name": "Maria Lopez", "email": "maria.lopez@example.com", "slack": "maria.lopez"},
        {"name": "Tom Baker", "email": "tom.baker@example.com"},
        {"name": "Priya Shah"}]


def test_contacts_fall_back_to_client_owners(project):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"].pop("client_contacts"))
    assert payload_of(project)["client_contacts"] == [{"name": "Maria Lopez"}, {"name": "Tom Baker"}]


def test_no_contacts_warns(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"].pop("client_contacts"))
    (project / publish.SLACK).unlink()
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0
    assert any("Nothing will show under \"Waiting on you\"" in w for w in plan["warnings"])
    assert json.loads(portal.requests[0].content)["client_contacts"] == []


# ---- Local check fails -------------------------------------------------------------------------------

def test_entity_in_a_title_stops(capsys, project, portal, builds):
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"][0].update(area="Sign-up &mdash; phone"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "docs/BA/dashboard.yaml → features 'Sign-up &mdash; phone' → area: holds an HTML entity" in result["error"]
    assert portal.requests == []


def test_too_many_features_stops(capsys, project, portal, builds):
    def many(d):
        base = d["features"][1]
        d["features"] = [dict(base, area=f"Feature {n}", id="identity-check" if n == 0 else f"f-{n}")
                         for n in range(301)]
    edit_yaml(project / publish.DASHBOARD, many)
    data_path = project / publish.MAP_PAGE
    page = data_path.read_text(encoding="utf-8")
    at = page.index("const DATA = ") + len("const DATA = ")
    data, end = json.JSONDecoder().raw_decode(page, at)
    data["epics"][0]["features"] += [{"id": f"f-{n}", "feature": {}, "stageKey": "concept"} for n in range(1, 301)]
    data_path.write_text(page[:at] + json.dumps(data) + page[end:], encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "docs/BA/dashboard.yaml → features" in result["error"] and "(/features)" in result["error"]
    assert portal.requests == []


def test_bad_since_stops(capsys, project, portal, builds):
    edit_yaml(project / publish.DASHBOARD, lambda d: d["awaiting"][0].update(since="last week"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "docs/BA/dashboard.yaml → awaiting 'Confirm the wording for sign-up' → since:" in result["error"]
    assert portal.requests == []


def test_missing_summary_names_s(capsys, project, portal, builds):
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"][1].pop("s"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "features 'Identity check' → s: required field is missing" in result["error"]


# ---- Portal error ------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["invalid_key", "project_archived", "contract_invalid",
                                  "contract_version_not_accepted", "payload_too_large"])
def test_portal_error(capsys, project, portal, builds, code):
    details = [{"path": "/features/0/title", "check": "schema", "message": "/features/0/title: too long"}] \
        if code == "contract_invalid" else []
    portal.error = (ERRORS[code]["status"], {"error": {"code": code, "message": ERRORS[code]["message"],
                                                       "details": details}})
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1
    assert ERRORS[code]["message"] in result["error"] and code in result["error"]
    assert publish.NEXT_STEP[code] in result["error"]
    if details:
        assert "docs/BA/dashboard.yaml → features 'Sign-up with phone number' → area: too long" in result["error"]
    assert len(portal.requests) == 1
    assert "payload" not in result               # no payload file is kept after a refused dry run


def test_portal_error_on_send(capsys, project, portal, tmp_path):
    payload_file = publish.write_payload(publish.encode(payload_of(project)))
    portal.error = (409, {"error": {"code": "project_archived", "message": ERRORS["project_archived"]["message"],
                                    "details": []}})
    rc, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
    assert rc == 1 and "project_archived" in result["error"]
    assert len(portal.requests) == 1 and not payload_file.exists()


# ---- Not reachable -----------------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_not_reachable(capsys, project, portal, builds, exc):
    portal.raise_exc = exc
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1
    assert f"The Portal is not reachable at {URL}" in result["error"]
    assert "payload" not in result


# ---- Odd reply ---------------------------------------------------------------------------------------

def test_odd_reply_200_failing_the_schema(capsys, project, portal, builds):
    bad = copy.deepcopy(portal.dry)
    bad["surprise"] = True
    portal.dry = bad
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1 and "The Portal's reply was not understood (HTTP 200)" in result["error"]


def test_odd_reply_dry_run_flag_wrong(capsys, project, portal, builds):
    portal.dry = portal.sent                    # a real-send reply to a dry run
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1 and "not understood (HTTP 200)" in result["error"]


def test_odd_reply_not_json(capsys, project, portal, builds):
    portal.raw = (404, b"<html>Not found</html>")
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1 and "The Portal's reply was not understood (HTTP 404)" in result["error"]
    assert len(portal.requests) == 1


# ---- Stale Jira --------------------------------------------------------------------------------------

def test_stale_jira_warns_and_offers_refresh(capsys, project, portal, builds):
    old = time.time() - 3 * 24 * 3600
    for name in publish.JIRA_FILES:
        f = project / "docs/BA/mind-map" / name
        f.write_text("{}", encoding="utf-8")
        os.utime(f, (old, old))
    _, plan, _ = run(capsys, project, "dashboard", "plan")
    assert any("3 days old" in w and "--refresh" in w for w in plan["warnings"])
    _, plan, _ = run(capsys, project, "dashboard", "plan", "--refresh")
    assert builds == [False, True]
    assert not any("--refresh" in w for w in plan["warnings"])


def test_fresh_jira_no_warning(project):
    for name in publish.JIRA_FILES:
        (project / "docs/BA/mind-map" / name).write_text("{}", encoding="utf-8")
    assert publish.stale_warning(project) is None


# ---- Build step failure and other commands -----------------------------------------------------------

def test_build_failure_stops(capsys, project, portal, monkeypatch):
    def broken(root, refresh):
        raise publish.Stop("dashboard.py build failed: features[0] is missing ['who']. Nothing was sent.")
    monkeypatch.setattr(publish, "run_build", broken)
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1 and "dashboard.py build failed" in result["error"]
    assert portal.requests == []


# ---- Review fixes ------------------------------------------------------------------------------------

def test_quoted_false_hides_features_and_items(project):
    def change(d):
        d["features"][1]["client"] = " FALSE "
        d["awaiting"][0]["client"] = "false"
    edit_yaml(project / publish.DASHBOARD, change)
    payload = payload_of(project)
    assert [f["id"] for f in payload["features"]] == ["sign-up"]
    titles = [i["title"] for i in payload["items"]]
    assert "Confirm the wording for sign-up" not in titles
    assert "Decide the limit for identity check" not in titles     # Item of the now-hidden Feature


@pytest.mark.parametrize("url,ok", [("http://portal.example.com", False), ("http://10.0.0.5:3000", False),
                                    ("ftp://portal.test", False), ("https://portal.example.com", True),
                                    ("http://localhost:3000", True), ("http://127.0.0.1:3000", True),
                                    ("http://portal.localhost", True), ("http://portal.test", True)])
def test_plain_http_only_to_local_hosts(capsys, project, portal, builds, url, ok):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(url=url))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    if ok:
        assert code == 0, result
        Path(result["payload"]).unlink()
    else:
        assert code == 1 and "must start with https://" in result["error"]
        assert portal.requests == [] and builds == []


def test_env_with_byte_order_mark(capsys, project, portal, builds):
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8-sig")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0, result
    assert portal.requests[0].headers["Authorization"] == f"Bearer {KEY}"
    Path(result["payload"]).unlink()


def test_not_a_git_repository(capsys, tmp_path, portal, builds):
    root = tmp_path / "plain"
    shutil.copytree(PROJECT, root)
    (root / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8")
    code, result, _ = run(capsys, root, "dashboard", "plan")
    assert code == 1 and "is not a git repository" in result["error"]


def test_git_not_installed(capsys, project, portal, builds, monkeypatch):
    real = subprocess.run

    def no_git(cmd, *a, **k):
        if cmd[0] == "git":
            raise FileNotFoundError("git")
        return real(cmd, *a, **k)
    monkeypatch.setattr(publish.subprocess, "run", no_git)
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "git is not installed" in result["error"]


def test_broken_yaml_gives_one_json_line(capsys, project, portal, builds):
    (project / publish.DASHBOARD).write_text("features: [\n", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "YAML file could not be read" in result["error"]
    assert portal.requests == []


def test_error_detail_with_null_path(capsys, project, portal, builds):
    portal.error = (422, {"error": {"code": "contract_invalid", "message": "The data does not match the contract.",
                                    "details": [{"path": None, "check": "schema", "message": None}]}})
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "contract_invalid" in result["error"]


def test_httpx_decoding_error_is_a_plain_error(capsys, project, portal, builds):
    portal.raise_exc = httpx.DecodingError("bad gzip")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and result["ok"] is False


def test_contacts_not_a_list_stops(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"].update(client_contacts="Maria Lopez"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "tools.client_contacts" in result["error"] and "must be a list" in result["error"]
    assert portal.requests == []


def test_open_as_text_and_clar_as_text(project):
    def change(d):
        d["features"][0]["open"] = "One question only?"
        d["features"][0]["clar"] = "https://pages.example.com/clarifications/sign-up/"
    edit_yaml(project / publish.DASHBOARD, change)
    sign_up = payload_of(project)["features"][0]
    assert sign_up["open"] == ["One question only?"]
    assert sign_up["clar_url"] == "https://pages.example.com/clarifications/sign-up/"


# send / discard only touch a payload file plan wrote

@pytest.mark.parametrize("where", ["outside-temp", "wrong-name"])
def test_send_and_discard_refuse_other_files(capsys, project, portal, tmp_path, where):
    if where == "outside-temp":
        victim = tmp_path / "portal-publish-x.json"
    else:
        victim = Path(tempfile.gettempdir()) / "important-notes-portal-test.json"
    victim.write_text("{}", encoding="utf-8")
    try:
        for command in ("send", "discard"):
            code, result, _ = run(capsys, project, "dashboard", command, "--payload", str(victim))
            assert code == 1 and "Nothing was sent or deleted" in result["error"]
            assert victim.exists()
        assert portal.requests == []
    finally:
        victim.unlink(missing_ok=True)


def test_send_missing_payload_file(capsys, project, portal):
    path = Path(tempfile.gettempdir()) / "portal-publish-gone-0000.json"
    path.unlink(missing_ok=True)
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "is not there" in result["error"]
    assert portal.requests == [] and not path.exists()


def test_send_non_json_payload(capsys, project, portal):
    path = publish.write_payload(b"this is not json")
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "is not a payload" in result["error"]
    assert portal.requests == [] and not path.exists()


def test_send_payload_edited_to_break_the_contract(capsys, project, portal):
    payload = payload_of(project)
    payload["features"][0]["owner"] = "Maria Lopez"
    path = publish.write_payload(publish.encode(payload))
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "does not match the contract" in result["error"]
    assert portal.requests == [] and not path.exists()


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("dropped")])
def test_real_send_without_a_reply_may_have_arrived(capsys, project, portal, exc):
    path = publish.write_payload(publish.encode(payload_of(project)))
    portal.raise_exc = exc
    try:
        code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
        assert code == 1
        assert "may have arrived" in result["error"]
        assert "Admin → Projects → the Project → Publishing" in result["error"]
        assert "Nothing was sent" not in result["error"]
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_plan_deletes_old_payload_files(capsys, project, portal, builds):
    old = publish.write_payload(b"{}")
    new = publish.write_payload(b"{}")
    past = time.time() - 2 * 24 * 3600
    os.utime(old, (past, past))
    plan = {}
    try:
        code, plan, _ = run(capsys, project, "dashboard", "plan")
        assert code == 0
        assert not old.exists() and new.exists()
    finally:
        for f in (old, new, Path(plan.get("payload", old))):
            f.unlink(missing_ok=True)


def test_max_bytes_matches_the_portal():
    assert publish.MAX_BYTES == 2 * 1024 * 1024


# run_build with subprocess.run faked

class FakeRun:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, cmd, *a, **k):
        self.calls.append(cmd)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        code, stdout, stderr = reply
        return subprocess.CompletedProcess(cmd, code, stdout.encode(), stderr.encode())


OK = (0, '{"ok": true}\n', "")


@pytest.mark.parametrize("refresh", [False, True])
def test_run_build_commands(monkeypatch, tmp_path, refresh):
    fake = FakeRun([OK, OK])
    monkeypatch.setattr(publish.subprocess, "run", fake)
    publish.run_build(tmp_path, refresh)
    first, second = fake.calls
    assert first == [sys.executable, str(publish.DASHBOARD_PY), "build", "--root", str(tmp_path)]
    assert second[:4] == [sys.executable, str(publish.MAP_BUILD_PY), "--root", str(tmp_path)]
    assert ("--refresh" in second) is refresh and "--refresh" not in first


@pytest.mark.parametrize("reply,expected", [
    ((1, '{"ok": false, "error": "features[0] is missing [\'who\']"}\n', ""), "features[0] is missing ['who']"),
    ((0, "built something\n", ""), "built something"),
    ((1, "", "Traceback (most recent call last):\n  File x\nKeyError: 'updated'\n"), "KeyError: 'updated'"),
])
def test_run_build_failures(monkeypatch, tmp_path, reply, expected):
    monkeypatch.setattr(publish.subprocess, "run", FakeRun([reply]))
    with pytest.raises(publish.Stop) as stop:
        publish.run_build(tmp_path, False)
    assert expected in str(stop.value) and "dashboard.py build failed" in str(stop.value)


def test_run_build_map_failure_and_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(publish.subprocess, "run", FakeRun([OK, (1, "", "boom\nSystemExit: No Jira projects")]))
    with pytest.raises(publish.Stop, match="map/build.py failed: SystemExit: No Jira projects"):
        publish.run_build(tmp_path, False)
    monkeypatch.setattr(publish.subprocess, "run", FakeRun([subprocess.TimeoutExpired("x", 600)]))
    with pytest.raises(publish.Stop, match="did not finish in 10 minutes"):
        publish.run_build(tmp_path, False)


def test_real_build_then_payload(project):
    """The real dashboard.py build and map/build.py, then build_payload on the page they wrote."""
    (project / publish.MAP_PAGE).unlink()
    publish.run_build(project, False)
    by_id = {f["id"]: f for f in payload_of(project)["features"]}
    assert set(by_id) == {"sign-up", "identity-check"}
    assert by_id["sign-up"]["stage"] == "spec" and by_id["sign-up"]["map_area"] == "No area"
    assert by_id["identity-check"]["stage"] == "dev" and by_id["identity-check"]["map_area"] == "No area"
