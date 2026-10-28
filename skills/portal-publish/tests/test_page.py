"""Tests for publish.py `page plan | send | discard <slug>` (a Clarification page). One test (or one group) per row of
the Story 4.3 matrix, plus the dry-run-then-confirm flow, the multipart part names and a screenshot changed between
plan and send.

The Portal is faked with httpx.MockTransport. Each test runs in a temp git repo copied from tests/page/project/, with
clarification-page's example-probate-decisions.yaml copied in and small PNGs written for its screens (the example
names screens it does not ship).
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

import checks
import publish

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "page" / "project"
PROBATE = publish.SKILLS / "clarification-page" / "assets" / "example-probate-decisions.yaml"
VALID = checks.CONTRACT_DIR / "fixtures" / "valid"
ERRORS = json.loads((checks.CONTRACT_DIR / "errors.json").read_text(encoding="utf-8"))
KEY = "pk_test_0a1b2c3d4e5f60718293a4b5c6d7e8f9"
OTHER = "pk_test_other_product_key_0000000000"     # the second product's key (Story 4.10)
URL = "http://portal.test"
CLAR = "docs/BA/clarifications"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
# Fields the Portal must never get (contract clarification-1.md, "It never sends …").
NEVER_SENT = {"spec", "product", "doc_title", "eyebrow", "copy_header", "copy_noun", "stage", "events", "settled",
              "figma_file", "figma_page", "node", "frame", "spec_ref", "figma", "src", "standfirst"}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def parts_of(request: httpx.Request) -> list[tuple[str, str | None, str, bytes]]:
    """The multipart parts of a request: (name, filename, content type, bytes), in order."""
    boundary = re.search(r"boundary=([^;]+)", request.headers["Content-Type"]).group(1).strip('"').encode()
    out = []
    for chunk in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = chunk.strip(b"\r\n").partition(b"\r\n\r\n")
        head = head.decode("utf-8")
        name = re.search(r'name="([^"]*)"', head).group(1)
        filename = re.search(r'filename="([^"]*)"', head)
        ctype = re.search(r"Content-Type: (\S+)", head, re.I)
        out.append((name, filename.group(1) if filename else None, ctype.group(1) if ctype else "", body))
    return out


# ---- helpers (no conftest.py) ------------------------------------------------------------------------

class FakePortal:
    """Answers like the Portal's page endpoint: the contract's own page reply fixtures, or an error envelope."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.error: tuple[int, dict] | None = None
        self.raise_exc: Exception | None = None
        self.echo_key = True                     # the reply names the round key that was sent
        self.projects = {KEY: "Sample App", OTHER: "Sample Admin"}     # the Portal project each key opens
        self.refuse: dict[str, tuple[int, dict]] = {}                    # a page send refused for one key only
        self.dry = read(VALID / "publish-reply-1-page-dry-run.json")
        self.sent = read(VALID / "publish-reply-1-page-sent.json")

    def handler(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        key = request.headers["Authorization"].removeprefix("Bearer ")
        if request.url.path == publish.STATUS_ENDPOINT:          # which Portal project a key opens
            return httpx.Response(200, json={"contract": "status/1", "project_name": self.projects[key],
                                             "archived": False, "waiting": 0, "last_fetched_at": None,
                                             "accepted_contracts": ["dashboard/2", "clarification/1"]})
        if key in self.refuse:
            return httpx.Response(self.refuse[key][0], json=self.refuse[key][1])
        if self.error is not None:
            return httpx.Response(self.error[0], json=self.error[1])
        dry = request.url.params.get("dry_run") == "1"
        reply = copy.deepcopy(self.dry if dry else self.sent)
        if self.echo_key and isinstance(reply.get("round"), dict):
            reply["round"]["key"] = json.loads(parts_of(request)[0][3])["store_key"]
        return httpx.Response(200, json=reply)


@pytest.fixture
def portal(monkeypatch):
    fake = FakePortal()
    monkeypatch.setattr(publish, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
    return fake


def write_screens(folder: Path, cfg: dict, data: bytes = PNG) -> None:
    srcs = [s["src"] for s in (cfg.get("design") or {}).get("screens") or []]
    srcs += [s["src"] for q in cfg.get("questions") or [] for s in q.get("screens") or []]
    for src in srcs:
        (folder / src).parent.mkdir(parents=True, exist_ok=True)
        (folder / src).write_bytes(data)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(PROJECT, root)
    clar = root / CLAR
    shutil.copyfile(PROBATE, clar / "probate-decisions.yaml")     # slug probate-decisions → <slug>.yaml
    for name in ("probate-decisions.yaml", "old-page-decisions.yaml"):
        write_screens(clar, yaml.safe_load((clar / name).read_text(encoding="utf-8")))
    git(root, "init", "-q")
    git(root, "config", "user.name", "Sample BA")
    git(root, "config", "user.email", "ba@example.com")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def run(capsys, root: Path, *args: str) -> tuple[int, dict]:
    code = publish.main([*args, "--root", str(root)])
    printed = capsys.readouterr().out
    assert KEY not in printed and OTHER not in printed, "a key must never be printed"
    return code, json.loads(printed.strip().splitlines()[-1])


def edit_yaml(path: Path, change) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def built(root: Path, name: str = "probate-decisions.yaml"):
    path = root / CLAR / name
    prof = yaml.safe_load((root / publish.PROFILE).read_text(encoding="utf-8"))
    return publish.build_page(root, path, yaml.safe_load(path.read_text(encoding="utf-8")), prof)


def all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in all_keys(v)}
    return set()


# ---- Happy path: plan, the BA's yes, send ----------------------------------------------------------------

def test_happy_path_plan_then_send(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 0 and plan["ok"] is True, plan
    assert len(portal.requests) == 1
    dry = portal.requests[0]
    assert str(dry.url) == f"{URL}/api/v1/publish/page?dry_run=1"
    assert dry.headers["Authorization"] == f"Bearer {KEY}"
    assert dry.headers["Content-Type"].startswith("multipart/form-data")

    parts = parts_of(dry)
    assert [p[0] for p in parts] == ["publish", "probate-355-2271.png", "probate-356-4676.png",
                                     "probate-356-5259.png"]
    name, filename, ctype, body = parts[0]
    assert filename is None and ctype == "application/json"
    page = json.loads(body)
    assert page["contract"] == "clarification/1" and page["slug"] == "probate-decisions"
    assert page["sent_by"] == "Sample BA" and page["ba_tools_version"] == "0.8.0" and page["source_commit"]
    for _, filename, ctype, data in parts[1:]:
        assert filename and ctype == "image/png" and data == PNG

    shown = plan["client_view"]
    for words in ("What the Client will read", "Page: Merchant payouts", "Round label: Round V7",
                  "A new Round.", "Every Monday (recommended)", "Answered questions (2):",
                  "Payouts go only to a bank account (2026-10-13, Sample Client, on the client call)",
                  "Counts: 6 Questions, 4 screenshots."):
        assert words in shown, words
    assert "<p" not in shown and "<strong" not in shown
    assert plan["round"]["new"] is True and plan["counts"] == {"questions": 6, "screenshots": 4}
    payload_file = Path(plan["payload"])
    assert payload_file.exists() and project not in payload_file.parents
    saved = read(payload_file)
    assert saved["publish"].encode("utf-8") == body
    assert [p["name"] for p in saved["parts"]] == [p[0] for p in parts[1:]]
    assert all(len(p["sha256"]) == 64 for p in saved["parts"])
    assert "data" not in json.dumps(saved["parts"]), "screenshots are never copied to temp"

    code, sent = run(capsys, project, "page", "send", "--payload", str(payload_file))
    assert code == 0 and sent["ok"] is True, sent
    assert len(portal.requests) == 2
    real = portal.requests[1]
    assert str(real.url) == f"{URL}/api/v1/publish/page"
    assert parts_of(real) == parts, "the dry run and the real send carry the same parts"
    report = sent["report"]
    for words in ('"Probate" (probate-decisions)', "Round V7 · sent 20 Oct 2026", "a new Round",
                  "6 Questions, 4 screenshots", "2026-10-27T10:15:02.480Z (UTC)",
                  "019a2b10-7e2c-7a35-8c4d-5e6f7a8b9c0d"):
        assert words in report, words
    assert not payload_file.exists()


def test_page_slug_alone_is_plan(capsys, project, portal):
    code, plan = run(capsys, project, "page", "probate-decisions")
    try:
        assert code == 0 and plan["ok"] is True and len(portal.requests) == 1
    finally:
        Path(plan["payload"]).unlink(missing_ok=True)


def test_replaced_round_says_so(capsys, project, portal):
    portal.dry["round"]["new"] = False
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    Path(plan["payload"]).unlink(missing_ok=True)
    assert "This replaces the Round with the same key (probate-decisions-v4)" in plan["client_view"]


def test_ba_says_no_discards(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    code, result = run(capsys, project, "page", "discard", "--payload", str(path))
    assert code == 0 and result["sent"] is None and not path.exists()
    assert len(portal.requests) == 1


def test_probate_converted_matches_the_contract_fixture(project):
    page, parts, _, left_out, warnings = built(project)
    assert checks.check_publish(page, "clarification", [p["name"] for p in parts]) is None
    fixture = read(VALID / "clarification-1-probate.json")
    envelope = ("contract", "sent_at", "sent_by", "ba_tools_version", "source_commit", "url")
    assert {k: v for k, v in page.items() if k not in envelope} == \
        {k: v for k, v in fixture.items() if k not in envelope}
    assert not all_keys(page) & NEVER_SENT
    assert "url" not in page                                 # the example's url is a placeholder
    for field in ("spec", "product", "events", "design.figma_file", "design.screens[].node",
                  "questions[].spec_ref", "title", "standfirst", "url (a placeholder)"):
        assert field in left_out, field


# ---- Unknown slug, slug mismatch, no round ---------------------------------------------------------------

def test_unknown_slug_names_each_path(capsys, project, portal):
    code, result = run(capsys, project, "page", "plan", "nothing-here")
    assert code == 1
    assert f"{CLAR}/nothing-here-decisions.yaml" in result["error"]
    assert f"{CLAR}/nothing-here.yaml" in result["error"]
    assert portal.requests == []


@pytest.mark.parametrize("bad", ["../secrets", "Probate", "a--b"])
def test_slug_that_is_not_a_slug(capsys, project, portal, bad):
    code, result = run(capsys, project, "page", "plan", bad)
    assert code == 1 and "is not a page slug" in result["error"] and portal.requests == []


def test_decisions_file_found_first(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "old-page")
    Path(plan.get("payload") or "x").unlink(missing_ok=True)
    assert code == 0, plan
    assert plan["yaml"] == f"{CLAR}/old-page-decisions.yaml"


def test_slug_mismatch_names_both(capsys, project, portal):
    shutil.copyfile(project / CLAR / "probate-decisions.yaml", project / CLAR / "other-decisions.yaml")
    code, result = run(capsys, project, "page", "plan", "other")
    assert code == 1
    assert "'probate-decisions'" in result["error"] and "'other'" in result["error"]
    assert portal.requests == []


def test_no_round_line_stops(capsys, project, portal):
    edit_yaml(project / CLAR / "probate-decisions.yaml", lambda d: d.pop("round"))
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "no `round:` line" in result["error"] and portal.requests == []


def test_settings_checks_are_the_dashboards(capsys, project, portal):
    (project / ".env").unlink()
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "Run `ba-setup project`" in result["error"] and portal.requests == []


# ---- Old page: settled lines and never-sent fields -------------------------------------------------------

def test_old_page_settled_lines_become_decisions(project):
    page, parts, _, left_out, _ = built(project, "old-page-decisions.yaml")
    assert checks.check_publish(page, "clarification", [p["name"] for p in parts]) is None
    assert page["decisions"] == [
        {"id": "s1", "title": "Phone numbers are checked by SMS", "detail": "Agreed on the call — no email fallback."},
        {"id": "s2", "title": "Only adults can sign up"},
        {"id": "s3", "title": "A plain line with “quotes” and no strong part"},
    ]
    assert page["name"] == "Two questions on sign-up"                 # title stands in for name
    assert page["description"] == "<strong>Two questions</strong> are left &mdash; both small."
    assert not all_keys(page) & NEVER_SENT
    for field in ("spec", "product", "doc_title", "eyebrow", "stage", "copy_header", "copy_noun", "events",
                  "design.figma_file", "design.figma_page", "design.screens[].node", "design.screens[].frame",
                  "questions[].spec_ref", "questions[].screens[].figma"):
        assert field in left_out, field
    assert "settled" not in left_out and "title" not in left_out      # both were used


# ---- Screens: missing, clash, type, size -----------------------------------------------------------------

def test_missing_screen_stops(capsys, project, portal):
    (project / CLAR / "screens" / "probate-356-4676.png").unlink()
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert f"{CLAR}/probate-decisions.yaml → design.screens[1] → src" in result["error"]
    assert "screens/probate-356-4676.png is not there" in result["error"]
    assert portal.requests == []


def test_name_clash_is_renamed(capsys, project, portal):
    def change(d):
        d["questions"][0]["screens"] = [{"src": "other/probate-355-2271.png", "cap": "Same name, other folder"},
                                        {"src": "third/PROBATE-355-2271.png"}]
    edit_yaml(project / CLAR / "probate-decisions.yaml", change)
    for folder in ("other", "third"):
        (project / CLAR / folder).mkdir()
    (project / CLAR / "other" / "probate-355-2271.png").write_bytes(JPEG)
    (project / CLAR / "third" / "PROBATE-355-2271.png").write_bytes(WEBP)
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    Path(plan.get("payload") or "x").unlink(missing_ok=True)
    assert code == 0, plan
    parts = parts_of(portal.requests[0])
    names = [p[0] for p in parts]
    assert names == ["publish", "probate-355-2271.png", "probate-356-4676.png", "probate-356-5259.png",
                     "probate-355-2271-2.png", "PROBATE-355-2271-3.png"]
    assert parts[4][2] == "image/jpeg" and parts[5][2] == "image/webp"
    page = json.loads(parts[0][3])
    assert [s["file"] for s in page["questions"][0]["screens"]] == ["probate-355-2271-2.png",
                                                                   "PROBATE-355-2271-3.png"]


def test_a_gif_stops(capsys, project, portal):
    (project / CLAR / "screens" / "probate-356-5259.png").write_bytes(GIF)
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert "design.screens[2] → src: screens/probate-356-5259.png is not a PNG, JPEG or WebP" in result["error"]
    assert portal.requests == []


def test_an_11_mb_screenshot_stops(capsys, project, portal):
    (project / CLAR / "screens" / "probate-355-2271.png").write_bytes(PNG + b"\x00" * (11 * 1024 * 1024))
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert "design.screens[0] → src: screens/probate-355-2271.png is 11.0 MB" in result["error"]
    assert "at most 10 MB" in result["error"] and portal.requests == []


def test_91_mb_in_all_stops(capsys, project, portal, monkeypatch):
    monkeypatch.setattr(publish, "PAGE_MAX_BYTES", 1000)             # stands in for 90 MB
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "at most 90 MB in one send" in result["error"] and portal.requests == []


def test_limits_match_the_contract():
    assert publish.SCREEN_MAX_BYTES == 10 * 1024 * 1024
    assert publish.PAGE_MAX_BYTES == 90 * 1024 * 1024


def test_51_questions_stop(capsys, project, portal):
    def change(d):
        q = d["questions"][0]
        d["questions"] = [{**copy.deepcopy(q), "id": f"q{i}"} for i in range(51)]
    edit_yaml(project / CLAR / "probate-decisions.yaml", change)
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert "does not match the contract" in result["error"]
    assert f"{CLAR}/probate-decisions.yaml" in result["error"] and "(/questions)" in result["error"]
    assert portal.requests == []


def test_31_screens_stop(capsys, project, portal):
    def change(d):
        d["questions"][0]["screens"] = [{"src": f"many/s{i}.png"} for i in range(28)]
    edit_yaml(project / CLAR / "probate-decisions.yaml", change)
    (project / CLAR / "many").mkdir()
    for i in range(28):
        (project / CLAR / "many" / f"s{i}.png").write_bytes(PNG)
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert "31 screenshots; at most 30" in result["error"]
    assert "questions[0] 'q1-transferee-vs-grant' → screens[27]" in result["error"]
    assert portal.requests == []


def test_field_problem_names_file_row_and_field(capsys, project, portal):
    edit_yaml(project / CLAR / "probate-decisions.yaml",
              lambda d: d["questions"][1]["options"][0].update(t="Known &amp; accepted"))
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert (f"{CLAR}/probate-decisions.yaml → questions[1] 'q2-readonly-compliance' → options.0.t"
            in result["error"])
    assert portal.requests == []


# ---- Placeholder url, _fixyaml ---------------------------------------------------------------------------

def test_placeholder_url_left_out_with_a_warning(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    Path(plan["payload"]).unlink(missing_ok=True)
    assert code == 0
    assert any("is a placeholder" in w for w in plan["warnings"])
    assert "url" not in json.loads(parts_of(portal.requests[0])[0][3])


def test_real_url_is_sent(project):
    edit_yaml(project / CLAR / "probate-decisions.yaml",
              lambda d: d.update(url="https://claude.ai/artifact/5b3f1c2e-8d4a-4e6f-9a1b-0c2d4e6f8a0b"))
    page, *_rest, warnings = built(project)
    assert page["url"] == "https://claude.ai/artifact/5b3f1c2e-8d4a-4e6f-9a1b-0c2d4e6f8a0b" and warnings == []


def test_fixyaml_runs_first_and_is_reported(capsys, project, portal):
    path = project / CLAR / "old-page-decisions.yaml"
    text = path.read_text(encoding="utf-8").replace("  title: How is age checked?",
                                                    "  meta: Decides: whether the form asks for a birth date\n"
                                                    "  title: How is age checked?")
    path.write_bytes(text.encode("utf-8"))                       # \n line endings
    code, plan = run(capsys, project, "page", "plan", "old-page")
    Path(plan.get("payload") or "x").unlink(missing_ok=True)
    assert code == 0, plan
    assert plan["fixed_lines"] == 1
    assert "_fixyaml.py quoted 1 line(s)" in plan["warnings"][0]
    after = path.read_bytes()
    assert b'meta: "Decides: whether the form asks for a birth date"' in after
    assert b"\r\n" not in after                                  # line endings kept
    page = json.loads(parts_of(portal.requests[0])[0][3])
    assert page["questions"][1]["meta"] == "Decides: whether the form asks for a birth date"


def test_fixyaml_with_nothing_to_fix_leaves_the_file_alone(capsys, project, portal):
    path = project / CLAR / "probate-decisions.yaml"
    before = path.read_bytes()
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    Path(plan["payload"]).unlink(missing_ok=True)
    assert code == 0 and plan["fixed_lines"] == 0 and path.read_bytes() == before


# ---- Portal refusals -------------------------------------------------------------------------------------

def test_round_has_answers(capsys, project, portal):
    portal.error = (409, {"error": {"code": "round_has_answers", "message": ERRORS["round_has_answers"]["message"],
                                    "details": []}})
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert result["error"].startswith("Round V4 · sent 11 Sep 2026 by Vadim, your BA · replaces V3 was already "
                                      "used (it has answers, or it was replaced and deleted) — give it a new round key")
    assert "store_key" in result["error"] and "Nothing more was sent." in result["error"]
    assert len(portal.requests) == 1 and "payload" not in result


@pytest.mark.parametrize("code", ["screenshot_mismatch", "contract_invalid", "project_archived",
                                  "payload_too_large", "invalid_key"])
def test_portal_refusal_in_plain_words(capsys, project, portal, code):
    details = [{"path": "/questions/0/title", "check": "schema", "message": "/questions/0/title: too long"}] \
        if code == "contract_invalid" else []
    portal.error = (ERRORS[code]["status"], {"error": {"code": code, "message": ERRORS[code]["message"],
                                                       "details": details}})
    rc, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert rc == 1
    assert ERRORS[code]["message"] in result["error"]
    assert publish.PAGE_NEXT_STEP[code] in result["error"]
    if details:
        assert (f"{CLAR}/probate-decisions.yaml → questions[0] 'q1-transferee-vs-grant' → title: too long"
                in result["error"])
    assert len(portal.requests) == 1 and "payload" not in result


def test_refusal_on_send(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    portal.error = (409, {"error": {"code": "round_has_answers", "message": "x", "details": []}})
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "was already used (it has answers, or it was replaced and deleted) — give it a new round key" in result["error"]
    assert len(portal.requests) == 2 and not path.exists()


def test_dashboard_reply_to_a_page_is_not_understood(capsys, project, portal):
    portal.dry = read(VALID / "publish-reply-1-dry-run.json")
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "not understood (HTTP 200)" in result["error"]


# ---- Not reachable, timeout on send ----------------------------------------------------------------------

def test_not_reachable(capsys, project, portal):
    portal.raise_exc = httpx.ConnectError("refused")
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and f"The Portal is not reachable at {URL}" in result["error"]
    assert "payload" not in result


def test_timeout_on_send_may_have_arrived(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    portal.raise_exc = httpx.ReadTimeout("slow")
    try:
        code, result = run(capsys, project, "page", "send", "--payload", str(path))
        assert code == 1 and "may have arrived" in result["error"]
        assert "`page send` again" in result["error"]
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


# ---- Between plan and send -------------------------------------------------------------------------------

def test_screenshot_changed_between_plan_and_send(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    (project / CLAR / "screens" / "probate-356-4676.png").write_bytes(PNG + b"changed")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1
    assert "changed (or is gone) since `page plan`" in result["error"]
    assert "probate-356-4676.png" in result["error"]
    assert len(portal.requests) == 1 and not path.exists()


def test_page_send_refuses_a_payload_it_did_not_write(capsys, project, portal):
    path = publish.write_payload(b'{"something": "else"}')
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "is not a payload `page plan` wrote" in result["error"]
    assert portal.requests == [] and not path.exists()


# ---- Review fixes ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["send", "discard"])
def test_page_command_refuses_a_dashboard_payload(capsys, project, portal, action):
    path = publish.save_dashboard("App", "Sample App", "http://portal.test", "PORTAL_PUBLISH_KEY",
                                  b'{"contract": "dashboard/2"}')
    try:
        code, result = run(capsys, project, "page", action, "--payload", str(path))
        assert code == 1 and f"is a dashboard payload, not a page one: use `dashboard {action}`" in result["error"]
        assert portal.requests == [] and path.exists(), "nothing sent, nothing deleted"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("action", ["send", "discard"])
def test_dashboard_command_refuses_a_page_payload(capsys, project, portal, action):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    try:
        code, result = run(capsys, project, "dashboard", action, "--payload", str(path))
        assert code == 1 and f"is a page payload, not a dashboard one: use `page {action}`" in result["error"]
        assert len(portal.requests) == 1 and path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_payload_without_a_checksum_stops(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    saved = read(path)
    del saved["parts"][0]["sha256"]
    path.write_text(json.dumps(saved), encoding="utf-8")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "changed (or is gone) since `page plan`" in result["error"]
    assert len(portal.requests) == 1 and not path.exists()


def test_payload_naming_a_file_outside_the_repo_stops(capsys, project, portal, tmp_path):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    outside = tmp_path / "secret.png"
    outside.write_bytes(PNG)
    saved = read(path)
    saved["parts"][0]["path"] = str(outside)
    path.write_text(json.dumps(saved), encoding="utf-8")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "outside the project repo" in result["error"]
    assert len(portal.requests) == 1 and not path.exists()


def test_portal_changed_between_plan_and_send(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    prof = project / publish.PROFILE
    prof.write_text(prof.read_text(encoding="utf-8").replace("http://portal.test/", "https://other.example.com"),
                    encoding="utf-8")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "tools.portal.url is now https://other.example.com" in result["error"]
    assert len(portal.requests) == 1


def test_reply_with_another_round_key_is_not_understood(capsys, project, portal):
    portal.echo_key = False                      # the fixture's key is merchant-payouts-v7
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "not understood (HTTP 200)" in result["error"] and "round key" in result["error"]
    assert "payload" not in result


@pytest.mark.parametrize("src", ["../../../../outside.png", "ABSOLUTE"])
def test_screenshot_outside_the_repo_stops(capsys, project, portal, tmp_path, src):
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    src = str(outside) if src == "ABSOLUTE" else src
    edit_yaml(project / CLAR / "probate-decisions.yaml", lambda d: d["design"]["screens"][1].update(src=src))
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1
    assert f"{CLAR}/probate-decisions.yaml → design.screens[1] → src" in result["error"]
    assert "is outside the project repo" in result["error"] and portal.requests == []


def test_wrong_extension_warns(capsys, project, portal):
    (project / CLAR / "screens" / "probate-356-4676.png").write_bytes(JPEG)
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    Path(plan["payload"]).unlink(missing_ok=True)
    assert code == 0
    assert any("probate-356-4676.png is really a JPEG image" in w for w in plan["warnings"])


def test_quoted_false_on_rec_and_hero_is_not_sent(project):
    def change(d):
        d["design"]["screens"][0]["hero"] = "false"
        d["questions"][0]["options"][0]["rec"] = "no"
    edit_yaml(project / CLAR / "probate-decisions.yaml", change)
    page, *_ = built(project)
    assert "hero" not in page["design"]["screens"][0]
    assert "rec" not in page["questions"][0]["options"][0]


def test_datetime_decision_date_sends_the_date_only(project):
    path = project / CLAR / "probate-decisions.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("  date: 2026-09-11\n", "  date: 2026-09-11 10:30:00\n",
                                                             1), encoding="utf-8")
    page, *_ = built(project)
    assert page["decisions"][0]["date"] == "2026-09-11"


@pytest.mark.parametrize("url", ["TBD", "todo", "https://claude.ai/artifact/", "claude.ai/artifact/abc"])
def test_more_placeholder_urls(url):
    assert publish.is_placeholder_url(url)


def test_settled_entity_tags_and_line_numbers(project):
    edit_yaml(project / CLAR / "old-page-decisions.yaml", lambda d: d.update(settled=[
        "<strong>Already decided:</strong>", "<strong>Use &lt;b&gt;bold&lt;/b&gt; &lt; plain</strong>",
        "<strong>Third</strong>"]))
    page, _, sources, _, _ = built(project, "old-page-decisions.yaml")
    assert page["decisions"][0]["title"] == "Use bold ‹ plain"
    assert sources["/decisions/1"].startswith("settled[2]")      # the real line, not the kept-decision index


def test_fixyaml_failure_stops_and_leaves_the_file(capsys, project, portal):
    path = project / CLAR / "old-page-decisions.yaml"
    before = path.read_bytes().replace(b"Two questions", b"Two questions \xff")    # not UTF-8
    path.write_bytes(before)
    code, result = run(capsys, project, "page", "plan", "old-page")
    assert code == 1 and "_fixyaml.py failed" in result["error"]
    assert path.read_bytes() == before and portal.requests == []


def test_fixyaml_keeps_crlf(capsys, project, portal):
    path = project / CLAR / "old-page-decisions.yaml"
    text = path.read_text(encoding="utf-8").replace("  title: How is age checked?",
                                                    "  meta: Decides: whether the form asks for a birth date\n"
                                                    "  title: How is age checked?")
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    code, plan = run(capsys, project, "page", "plan", "old-page")
    Path(plan.get("payload") or "x").unlink(missing_ok=True)
    assert code == 0, plan
    after = path.read_bytes()
    assert b'meta: "Decides: whether the form asks for a birth date"\r\n' in after
    assert after.count(b"\n") == after.count(b"\r\n")


def test_stop_after_fixyaml_says_the_file_changed(capsys, project, portal):
    path = project / CLAR / "old-page-decisions.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("  title: How is age checked?",
                                                             "  meta: Decides: x\n  title: How is age checked?")
                    .replace("src: screens/country.png", "src: screens/gone.png"), encoding="utf-8")
    code, result = run(capsys, project, "page", "plan", "old-page")
    assert code == 1 and "screens/gone.png is not there" in result["error"]
    assert f"_fixyaml.py quoted 1 line(s) in {CLAR}/old-page-decisions.yaml" in result["error"]


def test_slug_mismatch_does_not_rewrite_the_file(capsys, project, portal):
    path = project / CLAR / "other-decisions.yaml"
    text = (project / CLAR / "old-page-decisions.yaml").read_text(encoding="utf-8")
    path.write_text(text.replace("doc_title: Old page", "doc_title: Old page # note: kept"), encoding="utf-8")
    before = path.read_bytes()
    code, result = run(capsys, project, "page", "plan", "other")
    assert code == 1 and "has slug 'old-page'" in result["error"]
    assert path.read_bytes() == before, "_fixyaml.py would have quoted the doc_title line"


def test_bad_request_refusal(capsys, project, portal):
    portal.error = (400, {"error": {"code": "bad_request", "message": ERRORS["bad_request"]["message"],
                                    "details": []}})
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and ERRORS["bad_request"]["message"] in result["error"]
    assert publish.PAGE_NEXT_STEP["bad_request"] in result["error"]


def test_timeout_on_the_dry_run_says_nothing_was_sent(capsys, project, portal):
    portal.raise_exc = httpx.ReadTimeout("slow")
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "the dry run got no reply" in result["error"] and "Nothing was sent" in result["error"]
    assert "may have arrived" not in result["error"] and "payload" not in result


# ---- Story 4.10: a repo with two products sends each page to its products' Portal projects -------------

PROBATE_URL = "https://pages.example.com/clarifications/probate/"
OLD_URL = "https://claude.ai/artifact/0f3e2d1c-aaaa-4bbb-8ccc-old-page-example"


def two_products(root: Path, probate_prod: str | None = "Admin", env: str | None = None) -> None:
    """Make the sample a repo with two products, App and Admin, each with its own key. The probate page gets a
    real url; a Feature with `probate_prod` links it (None: no Feature links it)."""
    edit_yaml(root / publish.PROFILE, lambda d: d["tools"]["portal"].update(
        products={"App": "PORTAL_PUBLISH_KEY_APP", "Admin": "PORTAL_PUBLISH_KEY_ADMIN"}))
    edit_yaml(root / CLAR / "probate-decisions.yaml", lambda d: d.update(url=PROBATE_URL))
    features = [{"area": "Old page feature", "prod": "App", "s": "x", "clar": {"url": OLD_URL}}]
    if probate_prod:
        features.append({"area": "Probate", "prod": probate_prod, "s": "x", "clar": {"url": PROBATE_URL}})
    (root / "docs/BA/dashboard.yaml").write_text(yaml.safe_dump({"products": ["App", "Admin"],
                                                                 "features": features}), encoding="utf-8")
    (root / ".env").write_text(env if env is not None else
                               f"PORTAL_PUBLISH_KEY_APP={KEY}\nPORTAL_PUBLISH_KEY_ADMIN={OTHER}\n", encoding="utf-8")


def bearer(request: httpx.Request) -> str:
    return request.headers["Authorization"].removeprefix("Bearer ")


def drop_payloads(plan: dict) -> None:
    for p in plan.get("products") or []:
        Path(p["payload"]).unlink(missing_ok=True)


def test_page_goes_to_its_products_project(capsys, project, portal):
    two_products(project, "Admin")
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 0, plan
    status, dry = portal.requests
    assert status.method == "GET" and status.url.path == publish.STATUS_ENDPOINT
    assert bearer(status) == bearer(dry) == OTHER
    assert [p["product"] for p in plan["products"]] == ["Admin"]
    assert plan["project_name"] == "Sample Admin"
    assert plan["client_view"].startswith('Admin → Portal project "Sample Admin"')
    assert "A new Round." in plan["client_view"]
    assert not any("first product" in w for w in plan["warnings"])
    saved = read(Path(plan["payload"]))
    assert saved["product"] == "Admin" and saved["key_var"] == "PORTAL_PUBLISH_KEY_ADMIN"
    assert saved["project_name"] == "Sample Admin" and OTHER not in json.dumps(saved)
    assert "product" not in json.loads(saved["publish"]), "no product field in the payload"
    code, sent = run(capsys, project, "page", "send", "--payload", plan["payload"])
    assert code == 0, sent
    status2, real = portal.requests[2:]
    assert status2.url.path == publish.STATUS_ENDPOINT, "the project is checked again before the real send"
    assert bearer(real) == OTHER and "dry_run" not in str(real.url)
    assert 'to Portal project "Sample Admin" at http://portal.test' in sent["report"]


def test_both_page_two_dry_runs_two_payloads(capsys, project, portal):
    two_products(project, "Both")
    code, plan = run(capsys, project, "page", "probate-decisions")
    paths = [Path(p["payload"]) for p in plan.get("products") or []]
    try:
        assert code == 0, plan
        assert [bearer(r) for r in portal.requests] == [KEY, KEY, OTHER, OTHER]
        assert [(p["product"], p["project_name"]) for p in plan["products"]] == [("App", "Sample App"),
                                                                                  ("Admin", "Sample Admin")]
        assert "payload" not in plan, "two projects: one entry each, no single payload at the top"
        assert len(set(paths)) == 2 and all(p.exists() for p in paths)
        assert [read(p)["key_var"] for p in paths] == ["PORTAL_PUBLISH_KEY_APP", "PORTAL_PUBLISH_KEY_ADMIN"]
        assert plan["products"][1]["client_view"].startswith('Admin → Portal project "Sample Admin"')
        # The BA says yes to one and no to the other.
        code, sent = run(capsys, project, "page", "send", "--payload", str(paths[0]))
        assert code == 0 and bearer(portal.requests[-1]) == KEY, sent
        code, gone = run(capsys, project, "page", "discard", "--payload", str(paths[1]))
        assert code == 0 and gone["sent"] is None and not paths[1].exists()
    finally:
        drop_payloads(plan)


def test_one_project_refuses_nothing_is_kept(capsys, project, portal):
    two_products(project, "Both")
    portal.refuse[OTHER] = (ERRORS["round_has_answers"]["status"], {"error": {
        "code": "round_has_answers", "message": ERRORS["round_has_answers"]["message"]}})
    before = set(Path(publish.tempfile.gettempdir()).glob(publish.PAYLOAD_GLOB))
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and "products" not in result
    assert result["error"].startswith('Admin → Portal project "Sample Admin": Round')
    assert "was already used" in result["error"] and "nothing was sent to any Portal project" in result["error"]
    assert set(Path(publish.tempfile.gettempdir()).glob(publish.PAYLOAD_GLOB)) <= before, "no payload kept"
    assert all("dry_run=1" in str(r.url) for r in portal.requests if r.method == "POST")


def test_unlinked_page_goes_to_the_first_product_with_a_warning(capsys, project, portal):
    two_products(project, None)
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    try:
        assert code == 0, plan
        assert [p["product"] for p in plan["products"]] == ["App"]
        assert any("No Feature in docs/BA/dashboard.yaml links this page" in w and "first product, App" in w
                   for w in plan["warnings"])
    finally:
        drop_payloads(plan)


def test_product_option_limits_the_page_to_one_project(capsys, project, portal):
    two_products(project, "Both")
    code, plan = run(capsys, project, "page", "plan", "probate-decisions", "--product", "Admin")
    try:
        assert code == 0, plan
        assert [p["product"] for p in plan["products"]] == ["Admin"]
        assert {bearer(r) for r in portal.requests} == {OTHER}
    finally:
        drop_payloads(plan)


@pytest.mark.parametrize("product,words", [("Nope", "There is no product called 'Nope'"),
                                           ("App", "goes with Admin, not App")])
def test_product_option_wrong_product_stops(capsys, project, portal, product, words):
    two_products(project, "Admin")
    code, result = run(capsys, project, "page", "plan", "probate-decisions", "--product", product)
    assert code == 1 and words in result["error"] and portal.requests == []


def test_page_send_needs_the_saved_key_variable(capsys, project, portal):
    two_products(project, "Admin")
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY_APP={KEY}\n", encoding="utf-8")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and ".env has no PORTAL_PUBLISH_KEY_ADMIN (the Publish key for Admin)" in result["error"]
    assert len(portal.requests) == 2 and not path.exists()


def test_page_send_stops_when_the_variable_no_longer_belongs_to_the_product(capsys, project, portal):
    two_products(project, "Admin")
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(
        products={"App": "PORTAL_PUBLISH_KEY_APP", "Admin": "PORTAL_PUBLISH_KEY_ADMIN_NEW"}))
    code, result = run(capsys, project, "page", "send", "--payload", plan["payload"])
    assert code == 1 and "used the key in PORTAL_PUBLISH_KEY_ADMIN for Admin" in result["error"]
    assert "PORTAL_PUBLISH_KEY_ADMIN_NEW" in result["error"] and len(portal.requests) == 2


def test_page_send_stops_when_the_key_now_opens_another_project(capsys, project, portal):
    two_products(project, "Admin")
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    try:
        portal.projects[OTHER] = "Someone Else"
        code, result = run(capsys, project, "page", "send", "--payload", str(path))
        assert code == 1 and 'now opens Portal project "Someone Else"' in result["error"]
        assert path.exists(), "kept, as for the Dashboard"
        assert [r.method for r in portal.requests] == ["GET", "POST", "GET"]
    finally:
        path.unlink(missing_ok=True)


def test_page_payload_without_a_key_variable_stops(capsys, project, portal):
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    path = Path(plan["payload"])
    doc = read(path)
    doc.pop("key_var")
    path.write_text(json.dumps(doc), encoding="utf-8")
    code, result = run(capsys, project, "page", "send", "--payload", str(path))
    assert code == 1 and "does not say which key" in result["error"] and len(portal.requests) == 1


def test_two_keys_opening_the_same_project_stop_a_both_page(capsys, project, portal):
    two_products(project, "Both")
    portal.projects[OTHER] = "Sample App"
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and 'both open the same Portal project, "Sample App"' in result["error"]
    assert "products" not in result


def test_one_product_repo_page_unchanged(capsys, project, portal):
    """One product: one dry run with PORTAL_PUBLISH_KEY, no /status call, no project line."""
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    try:
        assert code == 0 and len(portal.requests) == 1 and bearer(portal.requests[0]) == KEY
        assert "project_name" not in plan and plan["client_view"].startswith("What the Client will read")
        assert len(plan["products"]) == 1 and plan["payload"] == plan["products"][0]["payload"]
        saved = read(Path(plan["payload"]))
        assert saved["key_var"] == "PORTAL_PUBLISH_KEY" and saved["project_name"] == ""
    finally:
        drop_payloads(plan)


def test_page_names_the_missing_product_key(capsys, project, portal):
    two_products(project, "Admin", env=f"PORTAL_PUBLISH_KEY_APP={KEY}\n")
    code, result = run(capsys, project, "page", "plan", "probate-decisions")
    assert code == 1 and ".env has no PORTAL_PUBLISH_KEY_ADMIN (the Publish key for Admin)" in result["error"]
    assert portal.requests == []


def test_page_product_option_needs_a_name(capsys, project, portal):
    code, result = run(capsys, project, "page", "plan", "probate-decisions", "--product", "")
    assert code == 1 and "--product needs a product name" in result["error"]


def test_product_option_on_an_unlinked_page_says_no_feature_links_it(capsys, project, portal):
    two_products(project, None)
    code, result = run(capsys, project, "page", "plan", "probate-decisions", "--product", "Admin")
    assert code == 1 and portal.requests == []
    assert ("No Feature in docs/BA/dashboard.yaml links the page probate-decisions (by clar.url), so it goes with "
            "the first product, App, not Admin. To send it with Admin, put the page's url in the clar.url of a "
            "Admin Feature") in result["error"]


def test_page_link_with_a_trailing_slash_still_matches(capsys, project, portal):
    two_products(project, "Admin")
    edit_yaml(project / CLAR / "probate-decisions.yaml", lambda d: d.update(url=PROBATE_URL.rstrip("/")))
    code, plan = run(capsys, project, "page", "plan", "probate-decisions")
    try:
        assert code == 0, plan
        assert [p["product"] for p in plan["products"]] == ["Admin"]
    finally:
        drop_payloads(plan)
