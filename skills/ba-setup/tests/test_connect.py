"""Tests for `setup.py connect` (Story 3.12): swap a one-time connect code for a Portal key and write it into .env.

The Portal is a real HTTP server on 127.0.0.1 (http:// is allowed there), answering with portal-publish's contract
fixtures and errors.json. setup.py runs as the BA's Claude runs it: a separate process, so the tests see exactly
what it prints. Every test checks that the key never appears in what it prints.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
SETUP = HERE.parent / "scripts" / "setup.py"
CONTRACT = HERE.parent.parent / "portal-publish" / "contract"
ERRORS = json.loads((CONTRACT / "errors.json").read_text(encoding="utf-8"))
CONNECT = json.loads((CONTRACT / "fixtures" / "valid" / "connect-1.json").read_text(encoding="utf-8"))
PROFILE = "docs/BA/specs/.ba-profile.yml"


def new_key() -> str:
    return secrets.token_urlsafe(32)          # 43 characters of base64url, like the Portal's


class FakePortal:
    """POST /api/v1/connect. `reply` is (status, body as dict or bytes, extra headers)."""

    def __init__(self):
        self.key = new_key()
        self.reply = None
        self.requests: list[dict] = []
        portal = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                portal.requests.append({"path": self.path, "headers": dict(self.headers),
                                        "body": json.loads(self.rfile.read(length) or b"null")})
                status, body, extra = portal.reply or (200, portal.ok(), {})
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in extra.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def ok(self, name: str = "Acme Lending") -> dict:
        return {**CONNECT, "project": {**CONNECT["project"], "name": name}, "key": self.key,
                "key_last4": self.key[-4:]}

    def error(self, code: str, **extra) -> None:
        self.reply = (ERRORS[code]["status"], {"error": {"code": code, "message": ERRORS[code]["message"], **extra}},
                      {})


@pytest.fixture
def portal():
    p = FakePortal()
    yield p
    p.server.shutdown()
    p.server.server_close()


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def profile(url: str | None, products: list[str] = ("AcmeLending",), portal_products: dict | None = None) -> dict:
    portal = {} if url is None else {"url": url}
    if portal_products:
        portal["products"] = portal_products
    return {"products": [{"key": p.lower(), "name": p, "jira_project": p[:3].upper()} for p in products],
            "tools": {"portal": portal}}


@pytest.fixture
def git_env(tmp_path):
    """No global or system git settings, so `git config user.name` gives only what a test sets."""
    empty = tmp_path / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    return {**os.environ, "GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.fixture
def make_repo(tmp_path, portal, git_env):
    def make(prof: dict | None = None, name: str | None = "Sample BA", ignore_env: bool = True) -> Path:
        root = tmp_path / "acme-docs"
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True, env=git_env)
        if name:
            subprocess.run(["git", "config", "user.name", name], cwd=root, check=True, env=git_env)
        if ignore_env:
            (root / ".gitignore").write_text(".env\n", encoding="utf-8")
        (root / PROFILE).parent.mkdir(parents=True)
        (root / PROFILE).write_text(yaml.safe_dump(prof if prof is not None else profile(portal.url)),
                                    encoding="utf-8")
        return root
    return make


def run(root: Path, env: dict, *args: str, keys: tuple[str, ...] = ()) -> tuple[int, dict, str]:
    """Run setup.py connect. Checks that no key is in what it prints."""
    r = subprocess.run([sys.executable, str(SETUP), "connect", str(root), *args], capture_output=True, env=env)
    stdout, stderr = r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")
    for key in keys:
        assert key not in stdout and key not in stderr
        assert key[:20] not in stdout and key[:20] not in stderr
    return r.returncode, json.loads(stdout), stderr


# ---- a good code ---------------------------------------------------------------------------------------

def test_good_code_writes_the_key_and_prints_only_name_variable_and_last4(make_repo, portal, git_env):
    root = make_repo()
    code, out, err = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 0 and err == ""
    assert out["ok"] is True
    assert out["project"] == "Acme Lending" and out["variable"] == "PORTAL_PUBLISH_KEY"
    assert out["key_last4"] == portal.key[-4:]
    assert out["message"] == (f'Connected to Portal project "Acme Lending". The key is in .env as PORTAL_PUBLISH_KEY '
                              f"(it ends in {portal.key[-4:]}).")
    assert out["env_created"] is True and out["replaced"] is False and out["warnings"] == []
    assert (root / ".env").read_bytes() == f"PORTAL_PUBLISH_KEY={portal.key}\n".encode()
    assert not (root / ".env.connect-tmp").exists()


def test_request_is_connect_request_1_without_authorization(make_repo, portal, git_env):
    root = make_repo()
    run(root, git_env, "--product", "", "--code", " k7p4xm ", keys=(portal.key,))
    [req] = portal.requests
    assert req["path"] == "/api/v1/connect"
    assert "Authorization" not in req["headers"]
    assert req["body"] == {"code": "k7p4xm", "label": "acme-docs · Sample BA"}


def test_label_is_the_folder_alone_without_a_git_name(make_repo, portal, git_env):
    root = make_repo(name=None)
    run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert portal.requests[0]["body"]["label"] == "acme-docs"


def test_existing_env_keeps_its_lines_and_crlf(make_repo, portal, git_env):
    root = make_repo()
    before = b"# Portal\r\nJIRA_THING=1\r\n\r\nOTHER='a b'"            # no line break at the end
    (root / ".env").write_bytes(before)
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 0 and out["env_created"] is False
    assert (root / ".env").read_bytes() == before + f"\r\nPORTAL_PUBLISH_KEY={portal.key}\r\n".encode()


def test_bom_is_kept(make_repo, portal, git_env):
    root = make_repo()
    (root / ".env").write_bytes(b"\xef\xbb\xbfA=1\n")
    run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert (root / ".env").read_bytes() == f"﻿A=1\nPORTAL_PUBLISH_KEY={portal.key}\n".encode()


def test_an_empty_variable_is_filled_in_place(make_repo, portal, git_env):
    root = make_repo()
    (root / ".env").write_bytes(b"A=1\nPORTAL_PUBLISH_KEY=\nB=2\n")
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 0 and out["replaced"] is False
    assert (root / ".env").read_bytes() == f"A=1\nPORTAL_PUBLISH_KEY={portal.key}\nB=2\n".encode()


# ---- the variable is already there ------------------------------------------------------------------

def test_existing_key_is_refused_without_replace_and_the_code_is_not_spent(make_repo, portal, git_env):
    root = make_repo()
    old = new_key()
    before = f"A=1\r\nPORTAL_PUBLISH_KEY={old}\r\nB=2\r\n".encode()
    (root / ".env").write_bytes(before)
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key, old))
    assert code == 1 and out["ok"] is False
    assert ".env already has PORTAL_PUBLISH_KEY" in out["error"] and "--replace" in out["error"]
    assert "the code still works" in out["error"]
    assert portal.requests == []
    assert (root / ".env").read_bytes() == before


def test_replace_swaps_the_line_in_place(make_repo, portal, git_env):
    root = make_repo()
    old = new_key()
    (root / ".env").write_bytes(f"A=1\r\nexport PORTAL_PUBLISH_KEY={old}\r\nB=2\r\n".encode())
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", "--replace", keys=(portal.key, old))
    assert code == 0 and out["replaced"] is True
    assert (root / ".env").read_bytes() == f"A=1\r\nPORTAL_PUBLISH_KEY={portal.key}\r\nB=2\r\n".encode()


# ---- two products ---------------------------------------------------------------------------------------

TWO = {"AcmeLending": "PORTAL_PUBLISH_KEY_ACME", "Bond Portal": "PORTAL_PUBLISH_KEY_BOND"}


def test_two_products_write_each_under_its_own_name(make_repo, portal, git_env):
    root = make_repo(profile(portal.url, ["AcmeLending", "Bond Portal"], TWO))
    first = portal.key
    code, out, _ = run(root, git_env, "--product", "Bond Portal", "--code", "K7P-4XM", keys=(first,))
    assert code == 0 and out["variable"] == "PORTAL_PUBLISH_KEY_BOND" and out["product"] == "Bond Portal"
    portal.key = new_key()
    code, out, _ = run(root, git_env, "--product", "AcmeLending", "--code", "ABC-DEF", keys=(first, portal.key))
    assert code == 0 and out["variable"] == "PORTAL_PUBLISH_KEY_ACME"
    assert (root / ".env").read_text(encoding="utf-8") == (f"PORTAL_PUBLISH_KEY_BOND={first}\n"
                                                           f"PORTAL_PUBLISH_KEY_ACME={portal.key}\n")


def test_two_products_need_product(make_repo, portal, git_env):
    root = make_repo(profile(portal.url, ["AcmeLending", "Bond Portal"], TWO))
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and "--product" in out["error"] and "AcmeLending, Bond Portal" in out["error"]
    code, out, _ = run(root, git_env, "--product", "Payroll", "--code", "K7P-4XM")
    assert code == 1 and "no product called 'Payroll'" in out["error"]
    assert portal.requests == [] and not (root / ".env").exists()


def test_two_products_without_portal_products_stop(make_repo, portal, git_env):
    root = make_repo(profile(portal.url, ["AcmeLending", "Bond Portal"]))
    code, out, _ = run(root, git_env, "--product", "AcmeLending", "--code", "K7P-4XM")
    assert code == 1 and "tools.portal.products" in out["error"] and "Nothing was sent." in out["error"]
    assert portal.requests == []


# ---- the Portal says no -------------------------------------------------------------------------------

def test_code_that_does_not_work(make_repo, portal, git_env):
    root = make_repo()
    portal.error("connect_code_invalid")
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 1
    assert out["error"].startswith("This code does not work. Ask an Admin for a new one (Admin → Projects → the "
                                   "project → Publishing → Connect a repo).")
    assert not (root / ".env").exists()


@pytest.mark.parametrize("wait,says", [(540, "in 9 minutes"), (61, "in 2 minutes"), (5, "in 1 minute"),
                                       (None, "in a few minutes")])
def test_too_many_tries(make_repo, portal, git_env, wait, says):
    root = make_repo()
    portal.error("too_many_tries", **({} if wait is None else {"retry_after_s": wait}))
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and out["error"] == f"Too many wrong codes were tried on the Portal. Try again {says}. Nothing was written."


def test_too_many_tries_reads_retry_after_header(make_repo, portal, git_env):
    root = make_repo()
    portal.reply = (429, {"error": {"code": "too_many_tries", "message": "x"}}, {"Retry-After": "300"})
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert "Try again in 5 minutes." in out["error"]


def test_an_older_portal_without_the_endpoint(make_repo, portal, git_env):
    root = make_repo()
    portal.reply = (404, b"<html>Not found</html>", {})
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and "cannot connect a repo with a code yet (HTTP 404)" in out["error"]


def test_other_portal_error_shows_its_code(make_repo, portal, git_env):
    root = make_repo()
    portal.error("bad_request")
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and out["error"].startswith("The Portal refused the connect (bad_request): ")


@pytest.mark.parametrize("broken", ["short", "last4", "missing", "not-json"])
def test_a_reply_that_is_not_connect_1_writes_nothing_and_never_shows_the_key(make_repo, portal, git_env,
                                                                              broken):
    root = make_repo()
    reply = portal.ok()
    if broken == "short":
        reply["key"] = portal.key[:-1]
    elif broken == "last4":
        reply["key_last4"] = "zzzz" if not portal.key.endswith("zzzz") else "yyyy"
    elif broken == "missing":
        del reply["project"]
    portal.reply = (200, b"{not json" + portal.key.encode() if broken == "not-json" else reply, {})
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key, portal.key[:-1]))
    assert code == 1 and "ask an Admin for a new one" in out["error"]
    assert not (root / ".env").exists()


# ---- stops before anything is sent ---------------------------------------------------------------------

def test_portal_not_reachable(make_repo, git_env, tmp_path):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                     # nothing listens there now
    root = make_repo(profile(f"http://127.0.0.1:{port}"))
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1
    assert out["error"] == (f"The Portal is not reachable at http://127.0.0.1:{port}. Check that it is running and "
                            "that tools.portal.url is right. Nothing was written.")
    assert not (root / ".env").exists()


def test_no_portal_url(make_repo, portal, git_env):
    root = make_repo(profile(None))
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and "The profile has no Portal address (tools.portal.url" in out["error"]
    assert portal.requests == []


def test_plain_http_to_another_host_is_refused(make_repo, portal, git_env):
    root = make_repo(profile("http://portal.example.com"))
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and "must start with https://" in out["error"]


def test_no_profile(tmp_path, git_env):
    root = tmp_path / "repo"
    root.mkdir()
    code, out, _ = run(root, git_env, "--code", "K7P-4XM")
    assert code == 1 and "No project profile" in out["error"]


@pytest.mark.parametrize("bad", ["K0P-4XM", "K7P4X", "K7P-4XMA", "K7-P4XM", "", "pk_live_abc"])
def test_a_code_that_cannot_be_one_is_not_sent(make_repo, portal, git_env, bad):
    root = make_repo()
    code, out, _ = run(root, git_env, "--code", bad)
    assert code == 1 and out["error"].startswith("This does not look like a connect code.")
    assert portal.requests == []


# ---- .env and git ----------------------------------------------------------------------------------------

def test_env_not_ignored_stops_before_the_code_is_spent(make_repo, portal, git_env):
    root = make_repo(ignore_env=False)
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 1 and out["error"].startswith(".env is not ignored by git")
    assert "the code still works" in out["error"]
    assert portal.requests == [] and not (root / ".env").exists()


def test_env_that_is_not_utf8_stops_before_the_code_is_spent(make_repo, portal, git_env):
    root = make_repo()
    bad = b"OTHER=\xff\xfe\n"
    (root / ".env").write_bytes(bad)
    code, out, _ = run(root, git_env, "--code", "K7P-4XM", keys=(portal.key,))
    assert code == 1 and out["error"].startswith(".env cannot be written (UnicodeDecodeError)")
    assert portal.requests == [] and (root / ".env").read_bytes() == bad


def test_check_project_row_says_to_ask_for_a_connect_code(make_repo, portal, git_env):
    root = make_repo()
    r = subprocess.run([sys.executable, str(SETUP), "check-project", str(root)], capture_output=True, env=git_env)
    rows = json.loads(r.stdout.decode("utf-8"))["rows"]
    [key_row] = [row for row in rows if row["tool"].startswith("Portal key")]
    assert key_row["state"] == "missing"
    assert "connect code" in key_row["fix"] and "Connect a repo" in key_row["fix"]
