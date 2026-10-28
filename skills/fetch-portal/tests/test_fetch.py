"""Tests for fetch.py (fetch-portal). One test (or one group) per row of the Story 4.8 matrix, plus "run again
writes nothing" and the settings stops.

The Portal is faked with httpx.MockTransport and answers with portal-publish's contract fixtures (answers/1, ack/1,
errors.json). Each test runs in a temp git repo copied from tests/project/.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

import fetch

fetch.checks = fetch.load_checks()
checks = fetch.checks

HERE = Path(__file__).resolve().parent
PROJECT = HERE / "project"
VALID = checks.CONTRACT_DIR / "fixtures" / "valid"
ERRORS = json.loads((checks.CONTRACT_DIR / "errors.json").read_text(encoding="utf-8"))
KEY = "pk_test_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
URL = "http://portal.test"
OTHER_BATCH = "019a2c40-0000-7000-8000-000000000001"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


BATCH = read(VALID / "answers-1-batch.json")
NOTHING = read(VALID / "answers-1-nothing-to-fetch.json")
ACKED = read(VALID / "ack-1.json")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def error(code: str) -> tuple[int, dict]:
    return ERRORS[code]["status"], {"error": {"code": code, "message": ERRORS[code]["message"]}}


class FakePortal:
    """Hands out one batch, then nothing — like the Portal after an ack. Acks answer per `ack_mode`."""

    def __init__(self):
        self.key = KEY                     # the key this Portal project takes
        self.requests: list[httpx.Request] = []
        self.batches: list[dict] = [copy.deepcopy(BATCH)]
        self.ack_mode = "ok"               # ok | expired | unknown | noreply | 500 | invalid_key | odd
        self.reserve_error: tuple[int, dict] | None = None
        self.reserve_raw: tuple[int, bytes] | None = None
        self.reserve_exc: Exception | None = None
        self.acked: list[str] = []
        self.last_fetched_at = NOTHING["last_fetched_at"]
        self.project = "Sample App"         # the Portal project's name (GET /status)
        self.status_calls = 0
        self.status_exc: Exception | None = None

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == fetch.STATUS:            # which Portal project the key opens (two or more products)
            self.status_calls += 1
            assert request.method == "GET" and request.headers["Authorization"] == f"Bearer {self.key}"
            if self.status_exc is not None:
                raise self.status_exc
            return httpx.Response(200, json={"contract": "status/1", "project_name": self.project,
                                             "archived": False, "waiting": 0, "last_fetched_at": None,
                                             "accepted_contracts": ["dashboard/2", "clarification/1"]})
        self.requests.append(request)
        assert request.method == "POST"
        assert request.headers["Authorization"] == f"Bearer {self.key}"
        if request.url.path == fetch.RESERVE:
            if self.reserve_exc is not None:
                raise self.reserve_exc
            if self.reserve_raw is not None:
                return httpx.Response(self.reserve_raw[0], content=self.reserve_raw[1])
            if self.reserve_error is not None:
                return httpx.Response(self.reserve_error[0], json=self.reserve_error[1])
            if self.batches:
                return httpx.Response(200, json=self.batches.pop(0))
            return httpx.Response(200, json={**NOTHING, "last_fetched_at": self.last_fetched_at})
        assert request.url.path == fetch.ACK
        body = json.loads(request.content)
        assert checks.check_reply(body, "ack-request/1") == []
        if self.ack_mode == "noreply":
            raise httpx.ConnectError("refused", request=request)
        if self.ack_mode == "500":
            status, doc = error("server_error")
            return httpx.Response(status, json=doc)
        if self.ack_mode in ("expired", "unknown", "invalid_key"):
            code = {"expired": "batch_expired", "unknown": "batch_unknown"}.get(self.ack_mode, self.ack_mode)
            status, doc = error(code)
            return httpx.Response(status, json=doc)
        if self.ack_mode == "odd":
            return httpx.Response(200, json={"ok": True})
        self.acked.append(body["batch_id"])
        self.last_fetched_at = ACKED["confirmed_at"]
        return httpx.Response(200, json={**ACKED, "batch_id": body["batch_id"]})


@pytest.fixture
def portal(monkeypatch):
    fake = FakePortal()
    monkeypatch.setattr(fetch, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(fetch, "sleep", lambda s: None)
    return fake


KEPT = [f"portal-{BATCH['batch_id']}-merchant-payouts.md.tmp", f"portal-{BATCH['batch_id']}.complete"]

FIXED_NOW = dt.datetime(2026, 10, 27, 11, 0, 31, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(fetch, "now", lambda: FIXED_NOW)


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


def run(capsys, root: Path) -> tuple[int, dict]:
    code = fetch.main(["--root", str(root)])
    printed = capsys.readouterr().out
    assert KEY not in printed, "the key must never be printed"
    lines = printed.strip().splitlines()
    assert len(lines) == 1, "one JSON line out"
    return code, json.loads(lines[0])


def intake(root: Path) -> list[str]:
    folder = root / fetch.INTAKE
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def header(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def two_pages() -> dict:
    b = copy.deepcopy(BATCH)
    b["answers"][1]["page"] = {"slug": "statements", "title": "Statements"}
    assert checks.check_reply(b, "answers/1") == []
    return b


# ---- Nothing new ----------------------------------------------------------------------------------------

def test_nothing_new_says_since_when(capsys, project, portal):
    portal.batches = []
    code, res = run(capsys, project)
    assert code == 0 and res["ok"] is True, res
    assert res["files"] == []
    assert res["message"] == "No new answers since 2026-10-27 11:00 UTC."
    assert portal.paths() == [fetch.RESERVE]
    assert intake(project) == []


def test_nothing_ever_fetched(capsys, project, portal):
    portal.batches, portal.last_fetched_at = [], None
    code, res = run(capsys, project)
    assert code == 0 and res["message"] == "No new answers. None have been fetched yet."


# ---- One page -------------------------------------------------------------------------------------------

def test_one_page_writes_one_file_after_the_ack(capsys, project, portal):
    assert not (project / fetch.INTAKE).exists()
    code, res = run(capsys, project)
    assert code == 0 and res["ok"] is True, res
    name = "2026-10-27-1100-portal-merchant-payouts.md"
    assert res["files"] == [f"docs/BA/intake/{name}"]
    assert intake(project) == [name], "created docs/BA/intake/, no .tmp left"
    assert res["message"].startswith("Wrote 1 intake file:\n  - docs/BA/intake/" + name)
    assert "(Merchant payouts, 2 answers)" in res["message"]
    assert portal.paths() == [fetch.RESERVE, fetch.ACK]
    assert json.loads(portal.requests[1].content) == {"batch_id": BATCH["batch_id"]}
    assert portal.requests[0].content == b""


def test_file_header_and_body(capsys, project, portal):
    run(capsys, project)
    path = project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md"
    h = header(path)
    assert h == {
        "source": "portal", "date": dt.date(2026, 10, 27), "project": "Sample", "page": "merchant-payouts",
        "page_title": "Merchant payouts",
        "rounds": [{"key": "merchant-payouts-v7", "label": "Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6",
                    "published": "2026-10-20 08:00 UTC"}],
        "participants": ["Sample Client <sample.client@example.com>", "Second Person <second.person@example.com>"],
        "answer_count": 2, "first_answer": "2026-10-26 14:03 UTC", "last_answer": "2026-10-26 14:03 UTC",
        "fetched_at": "2026-10-27 11:00 UTC", "processed": False}
    body = path.read_text(encoding="utf-8").split("---\n", 2)[2]
    for line in ("# Merchant payouts (portal answers)", "**Project:** Sample",
                 "**Rounds:** Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6 (published 2026-10-20 08:00 UTC)",
                 "**Answers:** 2", "**Fetched:** 2026-10-27 11:00 UTC", "## Answers",
                 "### payout-day — Sample Client — 2026-10-26 14:03 UTC",
                 "**Round:** Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6 (published 2026-10-20 08:00 UTC)",
                 "**Question:** Which day of the week should merchants be paid?",
                 "**Option:** Every Friday (`friday`)",
                 "    Friday suits our cash flow better.",
                 "### statement — Second Person — 2026-10-26 14:03 UTC",
                 "**Option:** none (note only)",
                 "    We need to ask our accountant first."):
        assert line in body.splitlines(), line
    assert body.index("### payout-day") < body.index("### statement"), "Portal order kept"


def test_every_time_in_the_file_ends_in_utc(capsys, project, portal):
    run(capsys, project)
    text = (project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md").read_text(encoding="utf-8")
    import re
    times = re.findall(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(.{4})", text)
    assert times and all(t == " UTC" for t in times)
    assert "T14:03" not in text and "Z'" not in text


def test_long_note_is_kept_whole_and_indented(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    note = "First line.\n\nThird line after a blank.\n" + "x" * 4900
    b["answers"][0]["note"] = note
    portal.batches = [b]
    run(capsys, project)
    text = (project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md").read_text(encoding="utf-8")
    assert "\n    First line.\n\n    Third line after a blank.\n    " + "x" * 4900 + "\n" in text


# ---- Two pages ------------------------------------------------------------------------------------------

def test_two_pages_two_files_in_portal_order(capsys, project, portal):
    portal.batches = [two_pages()]
    code, res = run(capsys, project)
    assert code == 0, res
    assert res["files"] == ["docs/BA/intake/2026-10-27-1100-portal-merchant-payouts.md",
                            "docs/BA/intake/2026-10-27-1100-portal-statements.md"]
    assert res["message"].startswith("Wrote 2 intake files:")
    first, second = (project / f for f in res["files"])
    assert header(first)["answer_count"] == 1 and header(second)["answer_count"] == 1
    assert header(second)["page_title"] == "Statements"
    assert "### statement — Second Person" in second.read_text(encoding="utf-8")
    assert portal.paths().count(fetch.ACK) == 1


# ---- Changed Answer -------------------------------------------------------------------------------------

def test_changed_answer_says_what_it_replaces(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    b["answers"][0]["replaces"]["note"] = "Monday was fine at first."
    portal.batches = [b]
    run(capsys, project)
    lines = (project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md").read_text(
        encoding="utf-8").splitlines()
    assert "Replaces the answer sent 2026-10-22 09:12 UTC by Sample Client:" in lines
    assert "- Earlier option: Every Monday (`monday`)" in lines
    assert "    Monday was fine at first." in lines
    # the second Answer replaces nothing
    assert sum("Replaces the answer sent" in ln for ln in lines) == 1


def test_changed_answer_with_no_earlier_note(capsys, project, portal):
    run(capsys, project)
    text = (project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md").read_text(encoding="utf-8")
    assert "- Earlier note: none" in text


# ---- Name taken -----------------------------------------------------------------------------------------

def test_name_taken_gets_2_then_3(capsys, project, portal):
    folder = project / fetch.INTAKE
    folder.mkdir(parents=True)
    (folder / "2026-10-27-1100-portal-merchant-payouts.md").write_text("earlier\n", encoding="utf-8")
    (folder / "2026-10-27-1100-portal-merchant-payouts-2.md").write_text("earlier\n", encoding="utf-8")
    code, res = run(capsys, project)
    assert code == 0, res
    assert res["files"] == ["docs/BA/intake/2026-10-27-1100-portal-merchant-payouts-3.md"]
    assert (folder / "2026-10-27-1100-portal-merchant-payouts.md").read_text(encoding="utf-8") == "earlier\n"


# ---- Leftover .tmp --------------------------------------------------------------------------------------

def leftover(root: Path, batch_id: str = OTHER_BATCH, when=dt.datetime(2026, 10, 20, 9, 15,
                                                                         tzinfo=dt.timezone.utc),
             complete: bool = True) -> Path:
    folder = root / fetch.INTAKE
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"portal-{batch_id}-merchant-payouts.md.tmp"
    path.write_text(fetch.render("Sample", "merchant-payouts", BATCH["answers"], when), encoding="utf-8")
    if complete:
        (folder / f"portal-{batch_id}.complete").write_text("1\n", encoding="utf-8")
    return path


def test_leftover_acked_then_renamed_to_its_fetch_time(capsys, project, portal):
    tmp = leftover(project)
    portal.batches = []
    code, res = run(capsys, project)
    assert code == 0, res
    assert portal.paths() == [fetch.ACK, fetch.RESERVE], "the leftover batch is acked before reserving"
    assert portal.acked == [OTHER_BATCH]
    assert not tmp.exists()
    assert res["files"] == ["docs/BA/intake/2026-10-20-0915-portal-merchant-payouts.md"]
    assert "Finished an earlier fetch" in res["message"] and "No new answers since" in res["message"]


def test_leftover_then_a_new_batch(capsys, project, portal):
    leftover(project)
    code, res = run(capsys, project)
    assert code == 0, res
    assert portal.paths() == [fetch.ACK, fetch.RESERVE, fetch.ACK]
    assert len(res["files"]) == 2
    assert intake(project) == ["2026-10-20-0915-portal-merchant-payouts.md",
                               "2026-10-27-1100-portal-merchant-payouts.md"]


@pytest.mark.parametrize("mode", ["expired", "unknown"])
def test_leftover_expired_or_unknown_is_deleted_then_reserve(capsys, project, portal, mode):
    tmp = leftover(project)
    portal.ack_mode = mode
    portal.batches = []
    code, res = run(capsys, project)
    assert code == 0, res
    assert not tmp.exists()
    assert res["files"] == [] and intake(project) == []
    assert portal.paths() == [fetch.ACK, fetch.RESERVE]
    assert "Deleted 1 unfinished file" in res["message"]


def test_leftover_no_reply_keeps_it_and_stops(capsys, project, portal):
    tmp = leftover(project)
    portal.ack_mode = "noreply"
    code, res = run(capsys, project)
    assert code == 1 and res["ok"] is False
    assert tmp.exists()
    assert "The Portal is not reachable at http://portal.test" in res["error"]
    assert fetch.RESERVE not in portal.paths(), "no reserve while a leftover batch is unconfirmed"
    assert portal.paths().count(fetch.ACK) == 3


# ---- Ack no reply / 5xx ---------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["noreply", "500"])
def test_ack_no_reply_after_3_tries_keeps_the_tmp(capsys, project, portal, mode, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(fetch, "sleep", waits.append)
    portal.ack_mode = mode
    code, res = run(capsys, project)
    assert code == 1 and res["ok"] is False
    assert portal.paths() == [fetch.RESERVE, fetch.ACK, fetch.ACK, fetch.ACK]
    assert len(waits) == 2 and all(w <= 10 for w in waits), "short waits between tries"
    assert intake(project) == KEPT
    assert "next fetch-portal run finishes them" in res["error"]

    portal.ack_mode = "ok"                     # the next run finishes it
    code, res = run(capsys, project)
    assert code == 0, res
    assert intake(project) == ["2026-10-27-1100-portal-merchant-payouts.md"]


# ---- Ack batch_expired ----------------------------------------------------------------------------------

def test_ack_batch_expired_deletes_this_batch(capsys, project, portal):
    portal.ack_mode = "expired"
    code, res = run(capsys, project)
    assert code == 1 and res["ok"] is False
    assert intake(project) == []
    assert "come in the next fetch" in res["error"]
    assert portal.paths() == [fetch.RESERVE, fetch.ACK], "batch_expired is an answer: no retry"


def test_ack_odd_reply_keeps_the_tmp(capsys, project, portal):
    portal.ack_mode = "odd"
    code, res = run(capsys, project)
    assert code == 1 and "not understood" in res["error"]
    assert intake(project) == KEPT


# ---- Write fails ----------------------------------------------------------------------------------------

def test_write_fails_mid_batch_deletes_tmp_and_does_not_ack(capsys, project, portal, monkeypatch):
    portal.batches = [two_pages()]
    real = Path.write_text
    calls = {"n": 0}

    def flaky(self, *a, **kw):
        if self.name.endswith(".md.tmp"):
            calls["n"] += 1
            if calls["n"] == 2:
                real(self, "half", encoding="utf-8")       # a partly written file
                raise OSError(28, "No space left on device")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", flaky)
    code, res = run(capsys, project)
    assert code == 1 and res["ok"] is False
    assert intake(project) == [], "no .tmp from this batch is left"
    assert fetch.ACK not in portal.paths()
    assert "No space left on device" in res["error"]
    assert "after 2026-10-27 11:10 UTC" in res["error"]


# ---- Wrong key / not reachable / odd reserve reply -------------------------------------------------------

def test_wrong_key(capsys, project, portal):
    portal.reserve_error = error("invalid_key")
    code, res = run(capsys, project)
    assert code == 1
    assert res["error"].startswith("This key is not valid for this Project")
    assert "Admin → Projects → the Project → Publishing" in res["error"]
    assert intake(project) == []


def test_not_reachable(capsys, project, portal):
    portal.reserve_exc = httpx.ConnectError("refused")
    code, res = run(capsys, project)
    assert code == 1
    assert res["error"].startswith("The Portal is not reachable at http://portal.test")
    assert "Nothing was written" in res["error"]
    assert intake(project) == []


@pytest.mark.parametrize("reply", [
    (200, b"<html>old portal</html>"),
    (200, json.dumps({**BATCH, "answers": []}).encode()),           # a batch with no Answers fails answers/1
    (200, json.dumps({**NOTHING, "contract": "answers/2"}).encode()),
    (502, b"Bad gateway"),
])
def test_reply_that_fails_the_contract_writes_nothing_and_acks_nothing(capsys, project, portal, reply):
    portal.reserve_raw = reply
    code, res = run(capsys, project)
    assert code == 1 and "not understood" in res["error"]
    assert intake(project) == []
    assert fetch.ACK not in portal.paths()


# ---- Run again writes nothing ----------------------------------------------------------------------------

def test_run_again_writes_nothing(capsys, project, portal):
    code, first = run(capsys, project)
    assert code == 0 and len(first["files"]) == 1
    before = intake(project)
    code, again = run(capsys, project)
    assert code == 0 and again["files"] == []
    assert again["message"] == "No new answers since 2026-10-27 11:00 UTC."
    assert intake(project) == before


# ---- Settings ---------------------------------------------------------------------------------------------

def edit_profile(root: Path, change) -> None:
    path = root / fetch.PROFILE
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_no_portal_in_profile_sends_to_ba_setup(capsys, project, portal):
    edit_profile(project, lambda d: d["tools"].pop("portal"))
    code, res = run(capsys, project)
    assert code == 1 and "Run `ba-setup project`" in res["error"]
    assert portal.requests == []


def test_no_key_sends_to_ba_setup(capsys, project, portal):
    (project / ".env").write_text("# nothing here\n", encoding="utf-8")
    code, res = run(capsys, project)
    assert code == 1 and "Run `ba-setup project`" in res["error"]
    assert portal.requests == []


def test_no_env_file_sends_to_ba_setup(capsys, project, portal):
    (project / ".env").unlink()
    code, res = run(capsys, project)
    assert code == 1 and "Run `ba-setup project`" in res["error"]


def test_env_not_ignored_stops(capsys, project, portal):
    (project / ".gitignore").write_text("", encoding="utf-8")
    code, res = run(capsys, project)
    assert code == 1 and ".env is not ignored by git" in res["error"]
    assert portal.requests == []


@pytest.mark.parametrize("url,ok", [("http://portal.example.com", False), ("https://portal.example.com", True),
                                    ("http://127.0.0.1:3000", True), ("http://app.localhost", True)])
def test_plain_http_only_for_local_hosts(url, ok):
    if ok:
        fetch.check_url(url)
    else:
        with pytest.raises(fetch.Stop):
            fetch.check_url(url)


def test_contract_is_portal_publish_s_not_a_copy():
    assert checks.CONTRACT_DIR == (HERE.parent.parent / "portal-publish" / "contract").resolve()
    assert not (HERE.parent / "contract").exists()


def test_line_break_in_a_title_stays_on_one_line(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    for a in b["answers"]:
        a["page"]["title"] = "Merchant\npayouts 'v7'"
    portal.batches = [b]
    run(capsys, project)
    path = project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md"
    assert header(path)["page_title"] == "Merchant payouts 'v7'"
    assert "# Merchant payouts 'v7' (portal answers)" in path.read_text(encoding="utf-8").splitlines()


def test_ack_refused_with_a_wrong_key_keeps_the_tmp(capsys, project, portal):
    portal.ack_mode = "invalid_key"
    code, res = run(capsys, project)
    assert code == 1 and res["error"].startswith("This key is not valid for this Project")
    assert "the next run finishes them" in res["error"]
    assert intake(project) == KEPT
    assert portal.paths().count(fetch.ACK) == 1


# ---- Review fixes ------------------------------------------------------------------------------------------

def test_cut_off_batch_without_marker_is_deleted_not_acked(capsys, project, portal):
    tmp = leftover(project, complete=False)
    portal.batches = []
    code, res = run(capsys, project)
    assert code == 0, res
    assert not tmp.exists() and intake(project) == []
    assert portal.paths() == [fetch.RESERVE], "an unmarked batch is never acked"
    assert "cut off while writing" in res["message"] and "about 10 minutes" in res["message"]


def test_run_killed_mid_write_leaves_no_marker(capsys, project, portal, monkeypatch):
    portal.batches = [two_pages()]
    real = Path.write_text
    calls = {"n": 0}

    def killed(self, *a, **kw):
        if self.name.endswith(".md.tmp"):
            calls["n"] += 1
            if calls["n"] == 2:
                raise KeyboardInterrupt          # the run is killed after page 1 is on disk
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", killed)
    with pytest.raises(KeyboardInterrupt):
        fetch.main(["--root", str(project)])
    capsys.readouterr()
    monkeypatch.setattr(Path, "write_text", real)
    assert intake(project) == [f"portal-{BATCH['batch_id']}-merchant-payouts.md.tmp"], "page 1 only, no marker"

    code, res = run(capsys, project)             # the next run: delete, never ack, reserve as normal
    assert code == 0, res
    assert fetch.ACK not in portal.paths()
    assert intake(project) == []
    assert "cut off while writing" in res["message"]


def test_marker_is_removed_after_rename(capsys, project, portal):
    run(capsys, project)
    assert not any(n.endswith(".complete") for n in intake(project))


def test_leftovers_renamed_then_reserve_fails_reports_the_files(capsys, project, portal):
    leftover(project)
    portal.reserve_exc = httpx.ConnectError("refused")
    code, res = run(capsys, project)
    assert code == 1 and res["ok"] is False
    assert res["files"] == ["docs/BA/intake/2026-10-20-0915-portal-merchant-payouts.md"]
    assert "Wrote 1 intake file" in res["error"] and "Nothing new was written" in res["error"]
    assert "Nothing was written" not in res["error"]


def test_answer_ids_are_written(capsys, project, portal):
    run(capsys, project)
    lines = (project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md").read_text(
        encoding="utf-8").splitlines()
    assert f"**Answer id:** {BATCH['answers'][0]['id']}" in lines
    assert f"**Answer id:** {BATCH['answers'][1]['id']}" in lines
    assert f"- Earlier answer id: {BATCH['answers'][0]['replaces']['id']}" in lines


def test_lone_surrogate_in_a_note_is_a_plain_stop(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    b["answers"][0]["note"] = "bad \ud800 text"
    portal.reserve_raw = (200, json.dumps(b).encode("ascii"))     # JSON sends it escaped, as \ud800
    code, res = run(capsys, project)
    assert code == 1 and "Could not write the intake files" in res["error"]
    assert intake(project) == [] and fetch.ACK not in portal.paths()


@pytest.mark.parametrize("text", ["- just a list\n", "tools: [a, b]\n", "tools:\n  portal: [x]\n"])
def test_profile_not_a_mapping_sends_to_ba_setup(capsys, project, portal, text):
    (project / fetch.PROFILE).write_text(text, encoding="utf-8")
    code, res = run(capsys, project)
    assert code == 1 and "Run `ba-setup project`" in res["error"]
    assert portal.requests == []


@pytest.mark.parametrize("slug", ["null", "true", "123", "2026-10-27"])
def test_slug_is_quoted_in_the_header(slug):
    a = copy.deepcopy(BATCH["answers"][1])
    a["page"]["slug"] = slug
    text = fetch.render("Sample", slug, [a], FIXED_NOW)
    assert yaml.safe_load(text.split("---\n")[1])["page"] == slug


def test_control_characters_do_not_break_the_header():
    a = copy.deepcopy(BATCH["answers"][1])
    a["page"]["title"] = "Pay\x00outs\x1b"
    a["round"]["label"] = "Round\x07 V7"
    a["person"]["name"] = "Second\x0b Person"
    text = fetch.render("Sam\x01ple", "statements", [a], FIXED_NOW)
    h = yaml.safe_load(text.split("---\n")[1])
    assert h["page_title"] == "Pay outs" and h["rounds"][0]["label"] == "Round V7"
    assert h["participants"] == ["Second Person <second.person@example.com>"] and h["project"] == "Sam ple"


def test_reserve_timeout_says_answers_come_after_the_hold(capsys, project, portal):
    portal.reserve_exc = httpx.ReadTimeout("slow")
    code, res = run(capsys, project)
    assert code == 1 and "about 10 minutes" in res["error"]


def test_help_exits_0(capsys):
    assert fetch.main(["--help"]) == 0
    assert "fetch-portal" in capsys.readouterr().out


def test_stray_tmp_names_are_reported(capsys, project, portal):
    folder = project / fetch.INTAKE
    folder.mkdir(parents=True)
    (folder / "portal-oops.md.tmp").write_text("x", encoding="utf-8")
    portal.batches = []
    code, res = run(capsys, project)
    assert code == 0 and "docs/BA/intake/portal-oops.md.tmp" in res["message"]
    assert (folder / "portal-oops.md.tmp").exists()


def test_ack_200_for_another_batch_keeps_the_tmp(capsys, project, portal, monkeypatch):
    real = portal.handler

    def other(request):
        r = real(request)
        if request.url.path == fetch.ACK:
            return httpx.Response(200, json={**ACKED, "batch_id": OTHER_BATCH})
        return r

    monkeypatch.setattr(fetch, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(other)))
    code, res = run(capsys, project)
    assert code == 1 and "not understood" in res["error"]
    assert intake(project) == KEPT


def test_first_and_last_answer_follow_send_time_not_order(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    b["answers"][0]["sent_at"] = "2026-10-26T18:00:00.000Z"
    b["answers"][1]["sent_at"] = "2026-10-25T09:30:00.000Z"
    portal.batches = [b]
    run(capsys, project)
    h = header(project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md")
    assert h["first_answer"] == "2026-10-25 09:30 UTC" and h["last_answer"] == "2026-10-26 18:00 UTC"


def test_two_rounds_on_one_page(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    b["answers"][0]["round"] = {"key": "merchant-payouts-v6", "label": "Round V6",
                                "published_at": "2026-10-10T08:00:00.000Z"}
    portal.batches = [b]
    run(capsys, project)
    path = project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md"
    assert [r["key"] for r in header(path)["rounds"]] == ["merchant-payouts-v6", "merchant-payouts-v7"]
    assert ("**Rounds:** Round V6 (published 2026-10-10 08:00 UTC); Round V7 · sent 20 Oct 2026 by Sample BA · "
            "replaces V6 (published 2026-10-20 08:00 UTC)") in path.read_text(encoding="utf-8").splitlines()


def test_ack_batch_unknown_on_a_fresh_batch_deletes_its_files(capsys, project, portal):
    portal.ack_mode = "unknown"
    code, res = run(capsys, project)
    assert code == 1 and "batch_unknown" in res["error"] and "next fetch" in res["error"]
    assert intake(project) == []


def test_apostrophe_title_shows_once_in_the_message(capsys, project, portal):
    b = copy.deepcopy(BATCH)
    for a in b["answers"]:
        a["page"]["title"] = "Merchant's payouts"
    portal.batches = [b]
    code, res = run(capsys, project)
    assert "(Merchant's payouts, 2 answers)" in res["message"]
    assert "Merchant''s" not in res["message"]


def test_portal_publish_missing_stops(capsys, project, monkeypatch):
    monkeypatch.setattr(fetch, "CHECKS_PY", project / "nowhere" / "checks.py")
    monkeypatch.setattr(fetch, "checks", None)
    code, res = run(capsys, project)
    assert code == 1 and "portal-publish" in res["error"]


def test_not_a_git_repository_stops(capsys, tmp_path, portal):
    root = tmp_path / "plain"
    shutil.copytree(PROJECT, root)
    (root / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8")
    code, res = run(capsys, root)
    assert code == 1 and "not a git repository" in res["error"]
    assert portal.requests == []


def test_leftover_ack_invalid_key_keeps_the_tmp(capsys, project, portal):
    tmp = leftover(project)
    portal.ack_mode = "invalid_key"
    code, res = run(capsys, project)
    assert code == 1 and res["error"].startswith("This key is not valid for this Project")
    assert tmp.exists() and (project / fetch.INTAKE / f"portal-{OTHER_BATCH}.complete").exists()
    assert fetch.RESERVE not in portal.paths()


# ---- Story 4.10: every product's Portal project, one key at a time ---------------------------------------

KEY_ADMIN = "pk_test_0a1b2c3d4e5f60718293a4b5c6d7e8f9"
ADMIN_BATCH = "019a2c40-0000-7000-8000-0000000000ad"


def per_product_keys(root: Path, env: str | None = None) -> None:
    """Make the sample a repo with two products, App then Admin, each with its own Portal project and key."""
    prof = root / fetch.PROFILE
    doc = yaml.safe_load(prof.read_text(encoding="utf-8"))
    doc["tools"]["portal"]["products"] = {"App": "PORTAL_PUBLISH_KEY_APP", "Admin": "PORTAL_PUBLISH_KEY_ADMIN"}
    prof.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / ".env").write_text(env if env is not None else
                               f"PORTAL_PUBLISH_KEY_APP={KEY}\nPORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n",
                               encoding="utf-8")


def admin_batch() -> dict:
    b = copy.deepcopy(BATCH)
    b["batch_id"] = ADMIN_BATCH
    for a in b["answers"]:
        a["page"] = {"slug": "back-office", "title": "Back office"}
    assert checks.check_reply(b, "answers/1") == []
    return b


@pytest.fixture
def two(monkeypatch):
    """Two fake Portal projects, one per key: App answers with KEY, Admin with KEY_ADMIN."""
    app, admin = FakePortal(), FakePortal()
    admin.key = KEY_ADMIN
    admin.project = "Sample Admin"
    admin.batches = [admin_batch()]
    by_key = {KEY: app, KEY_ADMIN: admin}

    def handler(request: httpx.Request) -> httpx.Response:
        return by_key[request.headers["Authorization"].removeprefix("Bearer ")].handler(request)
    monkeypatch.setattr(fetch, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(fetch, "sleep", lambda s: None)
    return app, admin


def run_two(capsys, root: Path) -> tuple[int, dict]:
    code = fetch.main(["--root", str(root)])
    printed = capsys.readouterr().out
    assert KEY not in printed and KEY_ADMIN not in printed, "a key must never be printed"
    return code, json.loads(printed.strip().splitlines()[-1])


def test_two_products_fetch_from_both_projects(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    code, res = run_two(capsys, project)
    assert code == 0 and res["ok"] is True, res
    assert app.paths() == [fetch.RESERVE, fetch.ACK] and admin.paths() == [fetch.RESERVE, fetch.ACK]
    assert app.acked == [BATCH["batch_id"]] and admin.acked == [ADMIN_BATCH]
    assert intake(project) == ["2026-10-27-1100-portal-back-office.md", "2026-10-27-1100-portal-merchant-payouts.md"]
    assert [(p["product"], p["ok"], len(p["files"])) for p in res["products"]] == [("App", True, 1),
                                                                                  ("Admin", True, 1)]
    assert header(project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md")["product"] == "App"
    assert header(project / fetch.INTAKE / "2026-10-27-1100-portal-back-office.md")["product"] == "Admin"
    msg = res["message"]
    assert msg.startswith('App → Portal project "Sample App":\n  Wrote 1 intake file:')
    assert "(App: Merchant payouts, 2 answers)" in msg
    assert '\n\nAdmin → Portal project "Sample Admin":\n  Wrote 1 intake file:' in msg
    assert "(Admin: Back office, 2 answers)" in msg
    assert app.status_calls == admin.status_calls == 1, "each key's project is named before the fetch"
    assert [p["project_name"] for p in res["products"]] == ["Sample App", "Sample Admin"]


def test_one_product_down_the_others_still_run(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    admin.reserve_exc = httpx.ConnectError("refused")
    code, res = run_two(capsys, project)
    assert code == 1 and res["ok"] is False
    assert intake(project) == ["2026-10-27-1100-portal-merchant-payouts.md"], "App's files are written"
    assert res["files"] == [f"{fetch.INTAKE}/2026-10-27-1100-portal-merchant-payouts.md"]
    assert [(p["product"], p["ok"]) for p in res["products"]] == [("App", True), ("Admin", False)]
    assert '\n\nAdmin → Portal project "Sample Admin" — stopped:\n  The Portal is not reachable' in res["error"]
    assert res["error"].endswith("Not fetched: Admin. The other products are done. Fix what stopped, then run "
                                 "fetch-portal again.")


def test_first_product_with_a_wrong_key_does_not_stop_the_second(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    app.reserve_error = error("invalid_key")
    code, res = run_two(capsys, project)
    assert code == 1 and res["ok"] is False
    assert 'App → Portal project "Sample App" — stopped:' in res["error"] and "The key in .env (PORTAL_PUBLISH_KEY_APP)" in res["error"]
    assert admin.acked == [ADMIN_BATCH] and intake(project) == ["2026-10-27-1100-portal-back-office.md"]


def test_marker_names_the_key_variable(capsys, project, portal):
    portal.ack_mode = "noreply"
    code, res = run(capsys, project)
    assert code == 1
    marker = project / fetch.INTAKE / f"portal-{BATCH['batch_id']}.complete"
    assert marker.read_text(encoding="utf-8") == "1\nPORTAL_PUBLISH_KEY\n"


def test_leftover_is_acked_with_its_own_projects_key(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    leftover(project)
    (project / fetch.INTAKE / f"portal-{OTHER_BATCH}.complete").write_text("1\nPORTAL_PUBLISH_KEY_ADMIN\n",
                                                                         encoding="utf-8")
    app.batches, admin.batches = [], []
    code, res = run_two(capsys, project)
    assert code == 0, res
    assert admin.acked == [OTHER_BATCH] and app.acked == []
    assert intake(project) == ["2026-10-20-0915-portal-merchant-payouts.md"]


def test_old_leftover_is_acked_with_portal_publish_key_when_env_has_it(capsys, project, two):
    app, admin = two
    per_product_keys(project, f"PORTAL_PUBLISH_KEY={KEY}\nPORTAL_PUBLISH_KEY_APP={KEY}\n"
                              f"PORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n")
    leftover(project)                                    # its marker is "1\n": written before Story 4.10
    app.batches, admin.batches = [], []
    code, res = run_two(capsys, project)
    assert code == 0, res
    assert app.acked == [OTHER_BATCH] and admin.acked == []
    assert intake(project) == ["2026-10-20-0915-portal-merchant-payouts.md"]


def test_old_leftover_without_portal_publish_key_is_left_alone(capsys, project, two):
    app, admin = two
    per_product_keys(project)                            # .env has no PORTAL_PUBLISH_KEY
    tmp = leftover(project)
    app.batches, admin.batches = [], []
    code, res = run_two(capsys, project)
    assert code == 0, res
    assert tmp.exists() and (project / fetch.INTAKE / f"portal-{OTHER_BATCH}.complete").exists()
    assert app.acked == [] and admin.acked == []
    assert "names no key, and .env has no PORTAL_PUBLISH_KEY" in res["message"]


def test_two_keys_opening_one_project_stop_before_fetching(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    admin.project = "Sample App"
    code, res = run_two(capsys, project)
    assert code == 1
    assert ('The keys for App (PORTAL_PUBLISH_KEY_APP) and Admin (PORTAL_PUBLISH_KEY_ADMIN) both open the same '
            'Portal project, "Sample App"') in res["error"]
    assert app.requests == [] and admin.requests == [] and intake(project) == []


def test_status_not_reachable_for_one_product_the_other_still_runs(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    app.status_exc = httpx.ConnectError("refused")
    code, res = run_two(capsys, project)
    assert code == 1 and "App — stopped:\n  The Portal is not reachable" in res["error"]
    assert app.requests == [] and admin.acked == [ADMIN_BATCH]


def test_unexpected_error_keeps_files_already_written_and_goes_on(capsys, project, two, monkeypatch):
    app, admin = two
    per_product_keys(project)
    leftover(project)
    (project / fetch.INTAKE / f"portal-{OTHER_BATCH}.complete").write_text("1\nPORTAL_PUBLISH_KEY_APP\n",
                                                                         encoding="utf-8")
    real = fetch.fetch_new

    def broken(root, url, key, *a, **k):
        if key == KEY:
            raise OSError(28, "No space left on device")
        return real(root, url, key, *a, **k)
    monkeypatch.setattr(fetch, "fetch_new", broken)
    code, res = run_two(capsys, project)
    assert code == 1
    left = f"{fetch.INTAKE}/2026-10-20-0915-portal-merchant-payouts.md"
    assert res["products"][0] == {"product": "App", "ok": False, "files": [left], "project_name": "Sample App"}
    assert left in res["files"] and admin.acked == [ADMIN_BATCH]
    app_block = res["error"].split("\n\n")[0]
    assert "No space left on device" in app_block and "Nothing was written" not in app_block


def test_leftover_of_a_variable_no_longer_in_the_profile_is_left_alone(capsys, project, two):
    app, admin = two
    per_product_keys(project)
    tmp = leftover(project)
    (project / fetch.INTAKE / f"portal-{OTHER_BATCH}.complete").write_text("1\nPORTAL_PUBLISH_KEY_GONE\n",
                                                                         encoding="utf-8")
    app.batches, admin.batches = [], []
    code, res = run_two(capsys, project)
    assert code == 0, res
    assert tmp.exists() and app.acked == [] and admin.acked == []
    assert "fetched with the key in PORTAL_PUBLISH_KEY_GONE, which tools.portal.products no longer names" in \
        res["message"]


def test_a_missing_product_key_stops_before_anything(capsys, project, two):
    app, admin = two
    per_product_keys(project, f"PORTAL_PUBLISH_KEY_APP={KEY}\n")
    code, res = run_two(capsys, project)
    assert code == 1 and ".env has no PORTAL_PUBLISH_KEY_ADMIN (the Publish key for Admin)" in res["error"]
    assert "Nothing was written" in res["error"]
    assert app.requests == [] and admin.requests == []


def test_one_product_has_no_product_line(capsys, project, portal):
    code, res = run(capsys, project)
    assert code == 0, res
    path = project / fetch.INTAKE / "2026-10-27-1100-portal-merchant-payouts.md"
    assert "product" not in header(path) and "products" not in res
    assert res["message"].startswith("Wrote 1 intake file:")
    assert "(Merchant payouts, 2 answers)" in res["message"]


def test_settings_come_from_portal_publish_targets():
    assert fetch.TARGETS_PY == (HERE.parent.parent / "portal-publish" / "targets.py").resolve()
    assert fetch.tg().portal_targets.__module__ == "portal_publish_targets"
