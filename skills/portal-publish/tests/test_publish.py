"""Tests for publish.py (portal-publish dashboard). Stories 3.4 and 3.8: one dashboard/2 send per product.

The Portal is faked with httpx.MockTransport, the build step is stubbed, and each test runs in a temp git repo
copied from tests/publish/project/, with the BA page's data (const DATA) written by sample_data(). The sample has
two products, a "Both" Feature, topics, a loose Item, a 130-character release name, a card with 176 tickets and an
area with 9 open tickets. No real client text.
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
KEY_APP = "pk_test_9f8e7d6c5b4a39281706f5e4d3c2b1a0"
KEY_ADMIN = "pk_test_0a1b2c3d4e5f60718293a4b5c6d7e8f9"
KEY = "pk_test_1111222233334444555566667777aaaa"     # PORTAL_PUBLISH_KEY, for a repo with one product
KEYS = (KEY_APP, KEY_ADMIN, KEY)
URL = "http://portal.test"
LONG_RELEASE = ("Release 1.9.0 - " + "Application expiry; Investor preferences; Auto logout; " * 3)[:130]
EASY_PAYDAY = Path(r"C:\Acme Lending\acme-docs")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


# ---- the BA page's data ------------------------------------------------------------------------------

def tk(key: str, summary: str = "", status: str = "To Do", stage: str = "ready", who: str | None = None) -> dict:
    return {"key": key, "summary": summary or f"Ticket {key}", "status": status, "stage": stage, "who": who}


OPEN_TICKETS = [   # the Onboarding area: 9 open tickets, 2 of them being built or tested
    {"key": "APP-41", "summary": "Open one", "status": "To Do", "category": "new", "updated": "2026-10-19"},
    {"key": "APP-42", "summary": "Open two", "status": "In Progress", "category": "indeterminate",
     "updated": "2026-09-01"},
    {"key": "APP-43", "summary": "Open three", "status": "To Do", "category": "new", "updated": "2026-10-01"},
    {"key": "APP-44", "summary": "Open four", "status": "In Review", "category": "indeterminate",
     "updated": "2026-10-10"},
    {"key": "APP-45", "summary": "Open five", "status": "To Do", "category": "new", "updated": "2026-08-01"},
    {"key": "APP-46", "summary": "Open six", "status": "To Do", "category": "new", "updated": "2026-10-15"},
    {"key": "APP-47", "summary": "Open seven", "status": "To Do", "category": "new", "updated": "2026-07-01"},
    {"key": "APP-48", "summary": "Open eight", "status": "To Do", "category": "new", "updated": "2026-10-18"},
    {"key": "APP-49", "summary": "Open nine", "status": "To Do", "category": "new", "updated": "2026-06-01"},
]


def jira(name: str, project: str, **facts) -> dict:
    base = {"project": project, "id": "1", "name": name, "description": "", "done": 0, "recent": 0, "open": [],
            "lastUpdated": None, "lastDone": None, "shipped": [],
            "search": f"https://example.atlassian.net/issues/?jql=project%20%3D%20{project}"}
    return {**base, **facts}


def bubble(bid: str, label: str, prod: str, stage: str, feature: dict | None = None, tickets=(), done=None) -> dict:
    b = {"id": bid, "label": label, "prod": prod, "stageKey": stage, "doneDate": done, "children": [],
         "tickets": list(tickets)}
    if feature is not None:
        b["feature"] = feature
    return b


def card(cid: str, kind: str, prod: str, row: str, area: str, tickets=(), **extra) -> dict:
    return {"id": cid, "kind": kind, "prod": prod, "row": row, "area": area, "tickets": list(tickets),
            "stage": extra.pop("stage", "ready"), "blocked": extra.pop("blocked", False),
            "doneDate": extra.pop("doneDate", None), **extra}


def sample_data() -> dict:
    sign_up = bubble("sign-up", "Sign-up", "App", "spec", {"settled": 2, "open": ["Which employers get it first?", ""]},
                     [{**tk("APP-1", "Phone sign-up &amp; SMS", "In Progress", "dev"), "category": "indeterminate"}])
    many = [tk(f"APP-{100 + n}", who="Sample Developer" if n % 2 else None) for n in range(176)]
    return {
        "updated": "2026-10-20", "title": "Sample BA Dashboard", "products": ["App", "Admin"], "mapUrl": "",
        "epics": [
            {"id": "APP:Onboarding", "prod": "App", "label": "Onboarding", "active": True, "stage": "dev",
             "jira": jira("Onboarding", "APP", description="Sign-up &amp; first steps.", done=12,
                          open=copy.deepcopy(OPEN_TICKETS), lastDone="2026-10-12",
                          shipped=[{"key": "APP-30", "summary": "Phone check &amp; retry", "date": "2026-10-12"},
                                   {"key": "APP-31", "summary": "Done with no date", "date": None}]),
             "features": [sign_up,
                          bubble("refunds", "Refunds", "App", "ready", None, [tk("APP-60")]),
                          bubble("chat", "Chat assistant", "App", "concept")]},
            {"id": "ADM:Back office", "prod": "Admin", "label": "Back office", "active": True, "stage": "ready",
             "jira": jira("Back office", "ADM", done=2, open=[{"summary": "An older row with no key",
                                                                "status": "To Do", "category": "new"}]),
             "features": [bubble("back-office", "Back office tools", "Admin", "concept",
                                 {"settled": None, "open": []})]},
            {"id": "ADM:Onboarding", "prod": "Admin", "label": "Onboarding", "active": False, "stage": "done",
             "jira": jira("Onboarding", "ADM", done=3), "features": []},
            {"id": "APP:Quiet area", "prod": "App", "label": "Quiet area", "active": False, "stage": "concept",
             "jira": None, "features": []},
            {"id": "noarea", "prod": "Both", "label": "No area", "jira": None, "noarea": True, "active": True,
             "stage": "concept",
             "features": [bubble("identity-check", "Identity check", "App", "done", {"settled": None, "open": []},
                                 done="2026-10-01T10:00:00.000+0000"),
                          bubble("audit-log", "Audit log", "Both", "spec", {"settled": 0, "open": []})]},
            {"id": "unlinked", "prod": "Both", "label": "Not linked yet", "jira": None, "active": True,
             "loose": True, "stage": "concept",
             "features": [bubble("unlinked", "Loose items", "Both", "concept")]},
        ],
        "board": {
            "releases": {
                "App": [{"name": "1.5", "date": "2026-11-01", "released": False, "overdue": False},
                        {"name": LONG_RELEASE, "date": "2026-09-01", "released": True, "overdue": False}],
                "Admin": [{"name": "2.0", "date": "2026-10-01", "released": False, "overdue": True},
                          {"name": "1.5", "date": None, "released": True, "overdue": False}],
            },
            "cards": [
                card("c-sign-long", "feature", "App", LONG_RELEASE, "Onboarding",
                     [tk("APP-1", "Phone sign-up &amp; SMS", "In Progress", "dev", "Sample Developer")],
                     fid="sign-up", title="Sign-up", stage="dev"),
                card("c-sign-15", "feature", "App", "1.5", "Onboarding", many, fid="sign-up", title="Sign-up",
                     blocked=True),
                card("c-id", "feature", "App", "none", "No area", fid="identity-check", title="Identity check",
                     stage="done", doneDate="2026-10-01T10:00:00.000+0000"),
                card("c-audit", "feature", "Both", "none", "No area", fid="audit-log", title="Audit log",
                     stage="spec"),
                card("c-back", "feature", "Admin", "2.0", "Back office", [tk("ADM-1")], fid="back-office",
                     title="Back office tools"),
                card("c-refunds", "feature", "App", "none", "Onboarding", [tk("APP-60")], fid="refunds",
                     title="Refunds"),
                card("c-epic", "epic", "App", "1.5", "Onboarding",
                     [tk("APP-10", "Fees &amp; limits", "QA", "qa")], epic="APP-9", title="Payments &amp; refunds",
                     stage="qa"),
                card("c-other", "other", "Admin", "2.0", "Back office", [tk("ADM-5")], title="Other tickets"),
                card("c-ghost", "other", "Admin", "none", "Reports", [tk("ADM-7")], title="Other tickets"),
            ],
            "areas": {"App": ["Onboarding", "Quiet area"], "Admin": ["Back office", "Onboarding"]},
        },
    }


def write_map(root: Path, data: dict) -> None:
    page = root / publish.MAP_PAGE
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("<!doctype html>\n<html><body><script>\nconst DATA = " + json.dumps(data, ensure_ascii=False)
                    + ";\n</script></body></html>\n", encoding="utf-8")


def change_map(root: Path, change) -> None:
    data = publish.read_map(root)
    change(data)
    write_map(root, data)


# ---- the fake Portal ---------------------------------------------------------------------------------

class FakePortal:
    """Answers like the Portal: GET /status names the project each key opens; the publish endpoint answers with
    the contract's own reply fixtures, or an error envelope."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.error: tuple[int, dict] | None = None          # the publish endpoint's error
        self.status_error: tuple[int, dict] | None = None
        self.raw: tuple[int, bytes] | None = None
        self.raise_exc: Exception | None = None
        self.post_exc: Exception | None = None             # raised on POSTs only (the status call still answers)
        self.projects = {KEY_APP: "Sample App", KEY_ADMIN: "Sample Admin", KEY: "Sample Project"}
        self.accepted = ["dashboard/1", "dashboard/2", "clarification/1"]
        self.dry = read(VALID / "publish-reply-1-dashboard-2-dry-run.json")
        self.sent = read(VALID / "publish-reply-1-sent.json")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.post_exc is not None and request.method == "POST":
            raise self.post_exc
        if self.raw is not None:
            return httpx.Response(self.raw[0], content=self.raw[1], headers={"Content-Type": "text/html"})
        if request.url.path == publish.STATUS_ENDPOINT:
            if self.status_error is not None:
                return httpx.Response(self.status_error[0], json=self.status_error[1])
            key = request.headers["Authorization"].removeprefix("Bearer ")
            if key not in self.projects:
                return httpx.Response(401, json={"error": {"code": "invalid_key", "message":
                                                           ERRORS["invalid_key"]["message"], "details": []}})
            return httpx.Response(200, json={"contract": "status/1", "project_name": self.projects[key],
                                             "archived": False, "waiting": 0, "last_fetched_at": None,
                                             "accepted_contracts": self.accepted})
        if self.error is not None:
            return httpx.Response(self.error[0], json=self.error[1])
        dry = request.url.params.get("dry_run") == "1"
        return httpx.Response(200, json=self.dry if dry else self.sent)

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


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
    write_map(root, sample_data())
    git(root, "init", "-q")
    git(root, "config", "user.name", "Sample BA")
    git(root, "config", "user.email", "ba@example.com")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text(f"# Portal\nPORTAL_PUBLISH_KEY_APP={KEY_APP}\nPORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n",
                               encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def one_product(root: Path) -> None:
    """Make the sample a repo with one product (App) and PORTAL_PUBLISH_KEY only, as before Story 3.8."""
    def profile(d):
        d["products"] = [p for p in d["products"] if p["name"] == "App"]
        d["tools"]["portal"].pop("products")
    edit_yaml(root / publish.PROFILE, profile)
    change_map(root, lambda data: data.update(products=["App"]))
    (root / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\n", encoding="utf-8")


def run(capsys, root: Path, *args: str) -> tuple[int, dict, str]:
    code = publish.main([*args, "--root", str(root)])
    printed = capsys.readouterr().out
    assert not any(k in printed for k in KEYS), "a key must never be printed"
    return code, json.loads(printed.strip().splitlines()[-1]), printed


def edit_yaml(path: Path, change) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")


def payload_of(root: Path, product: str = "App") -> dict:
    prof = yaml.safe_load((root / publish.PROFILE).read_text(encoding="utf-8"))
    return publish.build_payload(root, prof, product)[0]


def saved(root: Path, product: str = "App", key_name: str = "PORTAL_PUBLISH_KEY_APP", payload=None) -> Path:
    """A payload file as `dashboard plan` writes it."""
    body = publish.encode(payload if payload is not None else payload_of(root, product))
    return publish.save_dashboard(product, f"Sample {product}", URL, key_name, body)


def by_product(plan: dict) -> dict:
    return {p["product"]: p for p in plan["products"]}


def cleanup(plan: dict) -> None:
    for p in plan.get("products") or []:
        Path(p["payload"]).unlink(missing_ok=True)


# ---- Happy path: two products, two Portal projects ---------------------------------------------------

def test_plan_shows_each_product_then_sends_each(capsys, project, portal, builds):
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0 and plan["ok"] is True, plan
    assert builds == [False]
    got = by_product(plan)
    assert list(got) == ["App", "Admin"]
    assert got["App"]["project_name"] == "Sample App" and got["Admin"]["project_name"] == "Sample Admin"
    status_app, dry_app, status_admin, dry_admin = portal.requests
    assert status_app.method == "GET" and str(status_app.url) == f"{URL}/api/v1/status"
    assert status_app.headers["Authorization"] == f"Bearer {KEY_APP}"
    assert str(dry_app.url) == f"{URL}/api/v1/publish/dashboard?dry_run=1"
    assert dry_app.headers["Authorization"] == f"Bearer {KEY_APP}"
    assert status_admin.headers["Authorization"] == dry_admin.headers["Authorization"] == f"Bearer {KEY_ADMIN}"
    assert json.loads(dry_app.content)["contract"] == "dashboard/2"
    assert json.loads(dry_app.content) != json.loads(dry_admin.content)

    shown = got["App"]["client_list"]
    assert shown.startswith('App → Portal project "Sample App"')
    assert got["Admin"]["client_list"].startswith('Admin → Portal project "Sample Admin"')
    for words in ("What the Client will read", "Areas (", "Features (", "Topics (", "Board: 6 cards "
                  "(2 feature / 2 epic / 2 other), 9 tickets", "Waiting on you (", "Next-call agenda (",
                  "Client contacts (3): Maria Lopez, Tom Baker, Priya Shah"):
        assert words in shown, words
    assert "ABC-6010" not in shown, "ticket lists are not printed"
    assert "<p" not in shown

    for product, key in (("App", KEY_APP), ("Admin", KEY_ADMIN)):
        payload_file = Path(got[product]["payload"])
        assert payload_file.exists() and project not in payload_file.parents
        code, sent, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
        assert code == 0 and sent["ok"] is True, sent
        assert sent["product"] == product and sent["project_name"] == f"Sample {product}"
        real = portal.requests[-1]
        assert str(real.url) == f"{URL}/api/v1/publish/dashboard"
        assert real.headers["Authorization"] == f"Bearer {key}"
        assert f'Sent the {product} Dashboard to Portal project "Sample {product}"' in sent["report"]
        assert portal.sent["publish_id"] in sent["report"]
        assert not payload_file.exists()
    assert portal.posts()[2].content == dry_app.content, "the dry run and the real send carry the same bytes"
    assert portal.posts()[3].content == dry_admin.content


def test_each_payload_passes_the_contract_and_holds_no_product(project):
    for product in ("App", "Admin"):
        payload = payload_of(project, product)
        assert checks.check_publish(payload) is None, product
        assert set(payload) <= {"contract", "sent_at", "sent_by", "ba_tools_version", "source_commit", "jira_base",
                                "areas", "features", "topics", "items", "releases", "cards", "client_contacts",
                                "clarification_pages"}
        assert '"prod"' not in json.dumps(payload) and "products" not in payload


def test_what_each_product_sends(project):
    app, admin = payload_of(project, "App"), payload_of(project, "Admin")
    assert [a["id"] for a in app["areas"]] == ["APP:Onboarding", "APP:Quiet area", "noarea", "unlinked"]
    assert [a["id"] for a in admin["areas"]] == ["ADM:Back office", "ADM:Onboarding", "noarea", "unlinked",
                                                 "board:Reports"]
    assert [f["id"] for f in app["features"]] == ["sign-up", "identity-check", "audit-log"]
    assert [f["id"] for f in admin["features"]] == ["audit-log"]                # back-office is client: false
    assert [t["id"] for t in app["topics"]] == ["refunds", "chat", "unlinked"]
    assert [t["id"] for t in admin["topics"]] == ["unlinked"]
    assert [c["id"] for c in app["cards"]] == ["c-sign-long", "c-sign-15", "c-id", "c-audit", "c-refunds", "c-epic"]
    assert [c["id"] for c in admin["cards"]] == ["c-audit", "c-other", "c-ghost"]
    assert sum(len(c["tickets"]) for c in app["cards"]) == 179
    assert [r["name"] for r in app["releases"]] == ["1.5", LONG_RELEASE]
    assert admin["releases"][0] == {"name": "2.0", "date": "2026-10-01", "released": False, "overdue": True}
    assert admin["releases"][1] == {"name": "1.5", "released": True, "overdue": False}       # no date: left out
    assert app["jira_base"] == admin["jira_base"] == "https://example.atlassian.net"
    assert app["client_contacts"] == admin["client_contacts"]


def test_areas(project):
    areas = {a["id"]: a for a in payload_of(project, "App")["areas"]}
    onboarding = areas["APP:Onboarding"]
    assert onboarding["name"] == "Onboarding" and onboarding["quiet"] is False and "special" not in onboarding
    jira = onboarding["jira"]
    assert jira["search"] == "https://example.atlassian.net/issues/?jql=project%20%3D%20APP"   # since 1.4.0
    assert jira["description"] == "Sign-up & first steps."                         # entity unescaped
    assert (jira["done"], jira["in_progress"], jira["open"], jira["last_done"]) == (12, 2, 9, "2026-10-12")
    assert jira["shipped"] == [{"key": "APP-30", "summary": "Phone check & retry", "date": "2026-10-12"}]
    assert areas["APP:Quiet area"]["quiet"] is True and "jira" not in areas["APP:Quiet area"]
    assert areas["noarea"]["special"] == "no_area" and areas["unlinked"]["special"] == "not_linked"
    admin = {a["id"]: a for a in payload_of(project, "Admin")["areas"]}
    assert "open_tickets" not in admin["ADM:Back office"]["jira"]                 # an older areas.json: no keys
    assert admin["ADM:Back office"]["jira"]["open"] == 1
    assert admin["board:Reports"] == {"id": "board:Reports", "name": "Reports", "quiet": False}


def test_open_tickets_in_progress_first_then_newest_five(project):
    jira = payload_of(project, "App")["areas"][0]["jira"]
    assert [t["key"] for t in jira["open_tickets"]] == ["APP-44", "APP-42", "APP-41", "APP-48", "APP-46"]
    assert [t["stage"] for t in jira["open_tickets"]] == ["dev", "dev", "ready", "ready", "ready"]
    assert jira["open_tickets"][0] == {"key": "APP-44", "summary": "Open four", "status": "In Review",
                                       "stage": "dev", "updated": "2026-10-10"}


def test_features_topics_and_items(project):
    app = payload_of(project, "App")
    sign_up = app["features"][0]
    assert sign_up["area"] == "APP:Onboarding" and sign_up["stage"] == "spec"
    assert sign_up["answered"] == {"done": 2, "total": 3}
    assert sign_up["tickets"] == [{"key": "APP-1", "summary": "Phone sign-up & SMS", "status": "In Progress",
                                   "stage": "dev"}]
    assert sign_up["summary"] == '<p class="lead">Sign up with your phone number.</p>'   # client_s replaces s
    identity = app["features"][1]
    assert identity["area"] == "noarea" and identity["done_date"] == "2026-10-01" and identity["tickets"] == []
    assert "answered" not in identity and "answered" not in app["features"][2]
    refunds = app["topics"][0]
    assert refunds == {"id": "refunds", "area": "APP:Onboarding", "title": "Refunds", "stage": "ready",
                       "tickets": [{"key": "APP-60", "summary": "Ticket APP-60", "status": "To Do",
                                    "stage": "ready"}]}
    parents = {i["title"]: i["parent"] for i in app["items"]}
    assert parents == {"Confirm the wording for sign-up": "sign-up", "Refund rules": "refunds",
                       "Which chat tool to keep": "chat", "Loose question": "unlinked",
                       "How long to keep the log": "audit-log", "Decide the limit for identity check": "identity-check"}
    first = app["items"][0]
    assert first["key"] == publish.item_key("waiting", "sign-up", "Confirm the wording for sign-up")
    assert first["who"] == "Maria Lopez then Dev team" and first["since"] == "2026-10-01"
    assert first["text"] == "<p>A short answer is fine.</p>" and first["how_to_send"] == "Reply in Slack."
    assert [i["title"] for i in payload_of(project, "Admin")["items"]] == ["How long to keep the log"]


def test_topic_item_goes_under_its_topic(project):
    chat = next(i for i in payload_of(project, "App")["items"] if i["title"] == "Which chat tool to keep")
    assert chat["parent"] == "chat" and chat["kind"] == "waiting"


def test_cards(project):
    app = {c["id"]: c for c in payload_of(project, "App")["cards"]}
    assert app["c-sign-long"]["release"] == LONG_RELEASE and len(LONG_RELEASE) == 130     # sent whole
    assert app["c-sign-long"]["tickets"][0]["assignee"] == "Sample Developer"           # who → assignee
    assert app["c-sign-15"]["feature"] == "sign-up" and app["c-sign-15"]["area"] == "APP:Onboarding"
    assert len(app["c-sign-15"]["tickets"]) == 176 and app["c-sign-15"]["blocked"] is True
    assert "assignee" not in app["c-sign-15"]["tickets"][0]
    assert app["c-id"]["release"] is None and app["c-id"]["done_date"] == "2026-10-01"
    assert app["c-epic"] == {"id": "c-epic", "kind": "epic", "area": "APP:Onboarding", "release": "1.5",
                             "title": "Payments & refunds", "stage": "qa", "blocked": False, "epic": "APP-9",
                             "tickets": [{"key": "APP-10", "summary": "Fees & limits", "status": "QA",
                                          "stage": "qa"}]}
    # The map gives a topic a feature card; dashboard/2 sends it as an "other" card in the topic's area.
    assert app["c-refunds"]["kind"] == "other" and "feature" not in app["c-refunds"]
    assert app["c-refunds"]["title"] == "Refunds" and app["c-refunds"]["area"] == "APP:Onboarding"
    admin = {c["id"]: c for c in payload_of(project, "Admin")["cards"]}
    assert admin["c-other"]["area"] == "ADM:Back office" and admin["c-ghost"]["area"] == "board:Reports"


def test_both_goes_to_both_products(project):
    for product in ("App", "Admin"):
        payload = payload_of(project, product)
        assert "audit-log" in {f["id"] for f in payload["features"]}
        assert "c-audit" in {c["id"] for c in payload["cards"]}
        assert {"noarea", "unlinked"} <= {a["id"] for a in payload["areas"]}


def test_entities_in_jira_text_are_unescaped(project):
    sent = json.dumps(payload_of(project, "App"), ensure_ascii=False)
    assert "&amp;" not in sent
    assert "Payments & refunds" in sent and "Fees & limits" in sent and "Phone sign-up & SMS" in sent


def test_release_name_over_255_stops_before_anything_is_sent(capsys, project, portal, builds):
    long = "Release 9 - " + "x" * 300

    def change(data):
        data["board"]["releases"]["Admin"][0]["name"] = long
        data["board"]["cards"][7]["row"] = long                 # c-other sits in it
    change_map(project, change)
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "The Admin Dashboard does not match the contract" in result["error"]
    assert "(/releases/0/name)" in result["error"] and "Jira → the release" in result["error"]
    assert portal.requests == [], "the App payload was fine, but nothing goes out until every product passes"


def test_card_in_another_products_release_is_left_out_with_a_warning(capsys, project, portal, builds):
    change_map(project, lambda data: data["board"]["cards"][7].update(row="1.5 (App only)"))
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0, plan
    assert any("Admin: 1 Board card(s) sit in a release of another product" in w for w in plan["warnings"])
    assert by_product(plan)["Admin"]["left_out"]["cards"] == 2              # that card and the hidden Feature's
    cleanup(plan)


def test_jira_base_falls_back_to_the_profile_then_stops(project):
    def no_jira(data):
        for e in data["epics"]:
            e["jira"] = None
    change_map(project, no_jira)
    assert payload_of(project)["jira_base"] == "https://example.atlassian.net"
    edit_yaml(project / publish.PROFILE, lambda d: d.pop("jira"))
    with pytest.raises(publish.Stop, match="no jira.site"):
        payload_of(project)


def test_build_payload_needs_a_product_when_there_are_two(project):
    with pytest.raises(publish.Stop, match="name one"):
        publish.build_payload(project, yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8")))


# ---- One product, mapping, keys ----------------------------------------------------------------------

def test_one_product_works_as_before(capsys, project, portal, builds):
    one_product(project)
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0, plan
    assert [p["product"] for p in plan["products"]] == ["App"]
    assert all(r.headers["Authorization"] == f"Bearer {KEY}" for r in portal.requests)
    payload = json.loads(portal.posts()[0].content)
    assert "audit-log" in {f["id"] for f in payload["features"]}
    code, sent, _ = run(capsys, project, "dashboard", "send", "--payload", plan["products"][0]["payload"])
    assert code == 0 and portal.posts()[-1].headers["Authorization"] == f"Bearer {KEY}"


def test_missing_mapping_names_both_products_and_the_setting(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].pop("products"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "App, Admin" in result["error"] and "tools.portal.products" in result["error"]
    assert "Run `ba-setup project`" in result["error"]
    assert portal.requests == [] and builds == []


def test_missing_mapping_for_one_product(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"]["products"].pop("Admin"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "names no key for: Admin" in result["error"]
    assert portal.requests == [] and builds == []


def test_product_option_never_falls_back_to_the_one_product_key(capsys, project, portal, builds):
    """--product picks one product of two: it still needs that product's own entry, never PORTAL_PUBLISH_KEY."""
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"]["products"].pop("Admin"))
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY={KEY}\nPORTAL_PUBLISH_KEY_APP={KEY_APP}\n", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "plan", "--product", "Admin")
    assert code == 1 and "names no key for: Admin" in result["error"]
    assert portal.requests == [] and builds == []


def test_missing_key_names_the_variable(capsys, project, portal, builds):
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY_APP={KEY_APP}\n", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert ".env has no PORTAL_PUBLISH_KEY_ADMIN (the Publish key for Admin)" in result["error"]
    assert portal.requests == [] and builds == []


def test_mapping_must_name_env_variables(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(products=["App", "Admin"]))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "tools.portal.products" in result["error"] and "must name" in result["error"]
    assert portal.requests == []


def test_a_product_in_the_map_without_a_key_stops_after_the_build(capsys, project, portal, builds):
    change_map(project, lambda data: data.update(products=["App", "Admin", "Extra"]))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "names no key for: Extra" in result["error"]
    assert portal.requests == []


def test_product_option_plans_one_product(capsys, project, portal, builds):
    code, plan, _ = run(capsys, project, "dashboard", "plan", "--product", "Admin")
    assert code == 0, plan
    assert [p["product"] for p in plan["products"]] == ["Admin"]
    assert all(r.headers["Authorization"] == f"Bearer {KEY_ADMIN}" for r in portal.requests)
    cleanup(plan)


def test_product_option_needs_only_that_products_key(capsys, project, portal, builds):
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n", encoding="utf-8")
    code, plan, _ = run(capsys, project, "dashboard", "plan", "--product", "Admin")
    assert code == 0, plan
    cleanup(plan)


@pytest.mark.parametrize("value", ["Nope", ""])
def test_product_option_unknown_or_empty(capsys, project, portal, builds, value):
    code, result, _ = run(capsys, project, "dashboard", "plan", "--product", value)
    assert code == 1
    if value:
        assert "no product called 'Nope'" in result["error"] and "App, Admin" in result["error"]
    else:
        assert "--product needs a product name" in result["error"]
    assert portal.requests == [] and builds == []


def test_ba_says_yes_to_one_and_no_to_the_other(capsys, project, portal, builds):
    _, plan, _ = run(capsys, project, "dashboard", "plan")
    got = by_product(plan)
    code, sent, _ = run(capsys, project, "dashboard", "send", "--payload", got["App"]["payload"])
    assert code == 0 and sent["product"] == "App"
    code, result, _ = run(capsys, project, "dashboard", "discard", "--payload", got["Admin"]["payload"])
    assert code == 0 and result["sent"] is None and "for Admin" in result["report"]
    real = [r for r in portal.posts() if r.url.params.get("dry_run") != "1"]
    assert len(real) == 1 and real[0].headers["Authorization"] == f"Bearer {KEY_APP}"
    assert not Path(got["Admin"]["payload"]).exists()


def test_status_refuses_the_key(capsys, project, portal, builds):
    portal.projects.pop(KEY_ADMIN)
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "The Portal refused the key in PORTAL_PUBLISH_KEY_ADMIN (invalid_key)" in result["error"]
    assert publish.invalid_key_step("PORTAL_PUBLISH_KEY_ADMIN") in result["error"]
    assert "products" not in result
    assert len(portal.posts()) == 1, "App's dry run went out (dry runs store nothing); Admin's did not"


def test_status_says_the_portal_does_not_take_dashboard_2(capsys, project, portal, builds):
    portal.accepted = ["dashboard/1", "clarification/1"]
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "does not accept dashboard/2 yet" in result["error"]
    assert portal.posts() == []


def test_status_reply_not_understood(capsys, project, portal, builds):
    portal.status_error = (200, {"contract": "status/1"})
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "The Portal's reply was not understood (HTTP 200)" in result["error"]


# ---- Two products never share a Portal project -------------------------------------------------------

def test_two_products_naming_the_same_key_variable_stop(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(
        products={"App": "PORTAL_PUBLISH_KEY_APP", "Admin": "PORTAL_PUBLISH_KEY_APP"}))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert ("gives App and Admin the same .env variable (PORTAL_PUBLISH_KEY_APP), so both would go to the same "
            "Portal project") in result["error"]
    assert "Nothing was sent" in result["error"]
    assert portal.requests == [] and builds == []


def test_two_keys_opening_the_same_portal_project_stop(capsys, project, portal, builds):
    portal.projects[KEY_ADMIN] = "Sample App"
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert ('The keys for App (PORTAL_PUBLISH_KEY_APP) and Admin (PORTAL_PUBLISH_KEY_ADMIN) both open the same '
            'Portal project, "Sample App"') in result["error"]
    assert "Nothing was sent" in result["error"] and "products" not in result
    assert not [r for r in portal.posts() if r.url.params.get("dry_run") != "1"], "no real send"


def test_send_stops_when_the_key_now_opens_another_project(capsys, project, portal):
    path = saved(project)                          # planned for "Sample App"
    portal.projects[KEY_APP] = "Someone Else"
    try:
        code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
        assert code == 1
        assert ('The key in PORTAL_PUBLISH_KEY_APP now opens Portal project "Someone Else", but `dashboard plan` '
                'showed the App Dashboard going to "Sample App"') in result["error"]
        assert "run `dashboard plan` again" in result["error"] and "Nothing was sent" in result["error"]
        assert portal.posts() == [] and path.exists(), "nothing sent; the payload file is kept"
    finally:
        path.unlink(missing_ok=True)


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


def test_env_not_ignored_stops_send_too(capsys, project, portal):
    payload_file = saved(project)
    (project / ".gitignore").write_text("", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
    assert code == 1 and ".env is not ignored" in result["error"]
    assert portal.requests == []
    assert not payload_file.exists()


# ---- Filter ------------------------------------------------------------------------------------------

def test_filter(project):
    payload = payload_of(project)
    titles = [i["title"] for i in payload["items"]]
    assert "BA to-do never sent" not in titles                         # to-do
    assert "Already answered" not in titles                            # done Item
    assert "Internal only item" not in titles                          # client: false Item
    assert "Back office question" not in titles                        # Item of a hidden Feature (and Admin's)
    admin = payload_of(project, "Admin")
    assert "back-office" not in {f["id"] for f in admin["features"]}
    assert "c-back" not in {c["id"] for c in admin["cards"]}           # the hidden Feature's card stays out
    sign_up = payload["features"][0]
    assert sign_up["open"] == ["Which employers get it first?"]       # empty string left out
    assert sign_up["clar_url"] == "https://pages.example.com/clarifications/sign-up/"
    assert "short" not in payload["features"][1]                       # empty string left out
    agenda = [i for i in payload["items"] if i["kind"] == "agenda"]
    assert len(agenda) == 1 and "text" not in agenda[0]
    assert "Sample BA Dashboard" not in json.dumps(payload)            # the page title is not sent


def test_left_out_counts_in_plan(capsys, project, portal, builds):
    _, plan, _ = run(capsys, project, "dashboard", "plan")
    got = by_product(plan)
    assert got["App"]["left_out"] == {"features": 0, "items": 3, "cards": 0}     # 2 Items + 1 to-do
    assert got["Admin"]["left_out"] == {"features": 1, "items": 1, "cards": 1}
    cleanup(plan)


# ---- Contacts ----------------------------------------------------------------------------------------

def test_contacts_from_the_profile(project):
    assert payload_of(project)["client_contacts"] == [
        {"name": "Maria Lopez", "email": "maria.lopez@example.com", "slack": "maria.lopez"},
        {"name": "Tom Baker", "email": "tom.baker@example.com"},
        {"name": "Priya Shah"}]


def test_contacts_fall_back_to_client_owners(project):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"].pop("client_contacts"))
    assert payload_of(project)["client_contacts"] == [{"name": "Maria Lopez"}, {"name": "Tom Baker"}]


def test_no_contacts_warns_once(capsys, project, portal, builds):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"].pop("client_contacts"))
    (project / publish.SLACK).unlink()
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0
    assert sum("Nothing will show under \"Waiting on you\"" in w for w in plan["warnings"]) == 1
    assert json.loads(portal.posts()[0].content)["client_contacts"] == []
    cleanup(plan)


# ---- Envelope ----------------------------------------------------------------------------------------

def test_envelope(project):
    payload = payload_of(project)
    assert payload["contract"] == "dashboard/2"
    assert payload["sent_by"] == "Sample BA"
    assert payload["ba_tools_version"] == "0.8.0"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True).stdout.strip()
    assert payload["source_commit"] == head
    assert len(payload["sent_at"]) == 24 and payload["sent_at"].endswith("Z")


def test_envelope_without_commit_or_profile_version(tmp_path):
    project = tmp_path / "no-commit"
    shutil.copytree(PROJECT, project)
    write_map(project, sample_data())
    git(project, "init", "-q")
    git(project, "config", "user.name", "Sample BA")
    edit_yaml(project / publish.PROFILE, lambda d: d.pop("ba_tools_version"))
    payload = payload_of(project)
    assert "source_commit" not in payload
    assert payload["ba_tools_version"]            # from ba-setup's tools_version()


# ---- Local check fails -------------------------------------------------------------------------------

def test_entity_in_a_title_stops(capsys, project, portal, builds):
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"][0].update(area="Sign-up &mdash; phone"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1
    assert "docs/BA/dashboard.yaml → features 'Sign-up &mdash; phone' → area: holds an HTML entity" in result["error"]
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


def test_feature_without_a_bubble_stops(capsys, project, portal, builds):
    change_map(project, lambda data: data["epics"][4]["features"].pop(0))         # identity-check
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and "has no bubble for the feature 'Identity check'" in result["error"]
    assert portal.requests == []


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
    step = publish.invalid_key_step("PORTAL_PUBLISH_KEY_APP") if code == "invalid_key" else publish.NEXT_STEP[code]
    assert step in result["error"]
    if details:
        assert "docs/BA/dashboard.yaml → features 'Sign-up with phone number' → area: too long" in result["error"]
    assert len(portal.posts()) == 1
    assert "products" not in result               # no payload file is kept after a refused dry run


def test_portal_error_on_send(capsys, project, portal):
    payload_file = saved(project)
    portal.error = (409, {"error": {"code": "project_archived", "message": ERRORS["project_archived"]["message"],
                                    "details": []}})
    rc, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(payload_file))
    assert rc == 1 and "project_archived" in result["error"]
    assert len(portal.requests) == 2 and not payload_file.exists()     # the status re-check, then the send


# ---- Not reachable -----------------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_not_reachable(capsys, project, portal, builds, exc):
    portal.raise_exc = exc
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1
    assert f"The Portal is not reachable at {URL}" in result["error"]
    assert "products" not in result


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


def test_odd_reply_with_a_dashboard_1_view(capsys, project, portal, builds):
    portal.dry = read(VALID / "publish-reply-1-dry-run.json")
    rc, result, _ = run(capsys, project, "dashboard", "plan")
    assert rc == 1 and "not a dashboard/2 view" in result["error"]


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
    cleanup(plan)
    _, plan, _ = run(capsys, project, "dashboard", "plan", "--refresh")
    assert builds == [False, True]
    assert not any("--refresh" in w for w in plan["warnings"])
    cleanup(plan)


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


# ---- Review fixes (Story 3.4) ------------------------------------------------------------------------

def test_quoted_false_hides_features_and_items(project):
    def change(d):
        d["features"][1]["client"] = " FALSE "
        d["awaiting"][0]["client"] = "false"
    edit_yaml(project / publish.DASHBOARD, change)
    payload = payload_of(project)
    assert [f["id"] for f in payload["features"]] == ["sign-up", "audit-log"]
    titles = [i["title"] for i in payload["items"]]
    assert "Confirm the wording for sign-up" not in titles
    assert "Decide the limit for identity check" not in titles     # Item of the now-hidden Feature
    assert "c-id" not in {c["id"] for c in payload["cards"]}


@pytest.mark.parametrize("url,ok", [("http://portal.example.com", False), ("http://10.0.0.5:3000", False),
                                    ("ftp://portal.test", False), ("https://portal.example.com", True),
                                    ("http://localhost:3000", True), ("http://127.0.0.1:3000", True),
                                    ("http://portal.localhost", True), ("http://portal.test", True)])
def test_plain_http_only_to_local_hosts(capsys, project, portal, builds, url, ok):
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(url=url))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    if ok:
        assert code == 0, result
        cleanup(result)
    else:
        assert code == 1 and "must start with https://" in result["error"]
        assert portal.requests == [] and builds == []


def test_env_with_byte_order_mark(capsys, project, portal, builds):
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY_APP={KEY_APP}\nPORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n",
                                  encoding="utf-8-sig")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0, result
    assert portal.requests[0].headers["Authorization"] == f"Bearer {KEY_APP}"
    cleanup(result)


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
    assert sign_up["answered"] == {"done": 2, "total": 3}
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


@pytest.mark.parametrize("body", [b"this is not json", b'{"contract": "dashboard/1"}'])
def test_send_a_file_plan_did_not_write(capsys, project, portal, body):
    path = publish.write_payload(body)
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "is not a payload" in result["error"]
    assert portal.requests == [] and not path.exists()


def test_send_payload_edited_to_break_the_contract(capsys, project, portal):
    payload = payload_of(project)
    payload["features"][0]["owner"] = "Maria Lopez"
    path = saved(project, payload=payload)
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "The App Dashboard does not match the contract" in result["error"]
    assert portal.requests == [] and not path.exists()


def test_send_after_the_portal_address_changed(capsys, project, portal):
    path = saved(project)
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(url="https://portal.example.com"))
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and "Run `dashboard plan` again" in result["error"]
    assert portal.requests == [] and not path.exists()


def test_send_without_that_products_key(capsys, project, portal):
    path = saved(project, "Admin", "PORTAL_PUBLISH_KEY_ADMIN")
    (project / ".env").write_text(f"PORTAL_PUBLISH_KEY_APP={KEY_APP}\n", encoding="utf-8")
    code, result, _ = run(capsys, project, "dashboard", "send", "--payload", str(path))
    assert code == 1 and ".env has no PORTAL_PUBLISH_KEY_ADMIN" in result["error"]
    assert portal.requests == []


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("dropped")])
def test_real_send_without_a_reply_may_have_arrived(capsys, project, portal, exc):
    path = saved(project)
    portal.post_exc = exc
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
        for f in (old, new):
            f.unlink(missing_ok=True)
        cleanup(plan)


def test_max_bytes_matches_the_portal():
    assert publish.MAX_BYTES == 5 * 1024 * 1024


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
    """The real dashboard.py build and map/build.py, then one payload per product from the page they wrote."""
    (project / publish.MAP_PAGE).unlink()
    publish.run_build(project, False)
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    data = publish.read_map(project)
    assert publish.map_products(data) == ["App", "Admin"]
    for product in ("App", "Admin"):
        payload = publish.build_payload(project, prof, product, data)[0]
        assert checks.check_publish(payload) is None, product
        assert payload["jira_base"] == "https://example.atlassian.net"           # no Jira files: the profile's site
    app = publish.build_payload(project, prof, "App", data)[0]
    by_id = {f["id"]: f for f in app["features"]}
    assert set(by_id) == {"sign-up", "identity-check", "audit-log"}
    assert by_id["sign-up"]["stage"] == "spec" and by_id["sign-up"]["area"] == "noarea"
    assert by_id["identity-check"]["stage"] == "dev"
    assert {t["id"] for t in app["topics"]} == {"refunds", "chat", "unlinked"}


# ---- The real project (read only; skipped where the folder is not on this computer) ------------------

@pytest.mark.skipif(not (EASY_PAYDAY / publish.MAP_PAGE).exists(), reason="the Acme Lending folder is not here")
def test_real_project_each_product_passes_the_contract():
    """A dry build_payload per product on the real Acme Lending folder: reads files, writes nothing, sends nothing."""
    prof = yaml.safe_load((EASY_PAYDAY / publish.PROFILE).read_text(encoding="utf-8"))
    data = publish.read_map(EASY_PAYDAY)
    products = publish.map_products(data)
    assert len(products) == 2
    tickets = 0
    for product in products:
        payload, _, left_out, _ = publish.build_payload(EASY_PAYDAY, prof, product, data, "2026-10-28T00:00:00.000Z")
        assert checks.check_publish(payload) is None, product
        assert len(publish.encode(payload)) < publish.MAX_BYTES
        mine = [c for c in data["board"]["cards"] if c["prod"] in (product, "Both")]
        assert len(payload["cards"]) == len(mine) - left_out["cards"]
        tickets += sum(len(c["tickets"]) for c in payload["cards"])
    all_tickets = sum(len(c["tickets"]) for c in data["board"]["cards"])
    assert all_tickets - 5 <= tickets <= all_tickets


# ---- Story 4.10: each product's Dashboard send lists its Clarification pages --------------------------
# The sample has six YAMLs in docs/BA/clarifications/: sign-up (App), audit-log (Both), back-office (Admin, a
# hidden Feature), loose-page (no Feature links it), draft-page (no store_key) and renamed (its slug is not its
# file name).

CLAR = "docs/BA/clarifications"


def page_yaml(root: Path, name: str, body: str) -> None:
    (root / CLAR / name).write_text(body, encoding="utf-8")


def test_each_product_sends_its_pages(capsys, project, portal, builds):
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    try:
        assert code == 0, plan
        app, admin = (json.loads(r.content) for r in portal.posts())
        assert app["clarification_pages"] == ["audit-log", "loose-page", "sign-up-decisions"]
        assert admin["clarification_pages"] == ["audit-log", "back-office"]
        assert checks.check_publish(app) is None and checks.check_publish(admin) is None
        assert any("these Clarification pages" in w and "first product, App: loose-page" in w
                   for w in plan["warnings"])
        assert not any("draft-page" in w or "other-name" in w for w in plan["warnings"]), "skipped quietly"
        assert all(p["pages_removed"] == [] for p in plan["products"])
        assert "will be removed" not in by_product(plan)["App"]["client_list"], "no line when none is removed"
    finally:
        cleanup(plan)


def test_pages_removed_are_shown_before_the_yes(capsys, project, portal, builds):
    portal.dry = read(VALID / "publish-reply-1-dashboard-2-pages-removed-dry-run.json")
    portal.sent = read(VALID / "publish-reply-1-dashboard-2-pages-removed.json")
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code == 0, plan
    got = by_product(plan)
    try:
        line = ('These pages will be removed from the Portal project "Sample Admin": Onboarding questions '
                '(old-onboarding-questions), Employer search: who can be found (employer-search)')
        assert got["Admin"]["client_list"].endswith(line)
        assert [p["slug"] for p in got["Admin"]["pages_removed"]] == ["old-onboarding-questions", "employer-search"]
        assert portal.posts() and all("dry_run=1" in str(r.url) for r in portal.posts()), "nothing sent yet"
        code, sent, _ = run(capsys, project, "dashboard", "send", "--payload", got["Admin"]["payload"])
        assert code == 0, sent
        assert ('It removed 2 page(s) from Portal project "Sample Admin", because the repo no longer sends them '
                'with Admin: Onboarding questions (old-onboarding-questions)') in sent["report"]
        assert len(sent["pages_removed"]) == 2
    finally:
        cleanup(plan)


def test_no_page_has_a_store_key_sends_an_empty_list_with_a_warning(capsys, project, portal, builds):
    for f in (project / CLAR).glob("*.yaml"):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        doc.pop("store_key", None)
        f.write_text(yaml.safe_dump(doc), encoding="utf-8")
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    try:
        assert code == 0, plan
        assert [json.loads(r.content)["clarification_pages"] for r in portal.posts()] == [[], []]
        for product in ("App", "Admin"):
            assert any(w.startswith(f"No Clarification page in {CLAR}/ goes with {product}") and
                       f"remove every page it has in {product}'s Portal project" in w for w in plan["warnings"])
    finally:
        cleanup(plan)


def test_same_slug_in_slug_yaml_and_decisions_yaml_uses_decisions_with_a_warning(project):
    """<slug>.yaml and <slug>-decisions.yaml with one slug: -decisions is the page, as `page plan` picks it."""
    page_yaml(project, "loose-page.yaml", "slug: loose-page\nstore_key: loose-page-v9\nname: Older copy\n")
    pages, warnings = publish.page_index(project)
    loose = [p for p in pages if p["slug"] == "loose-page"]
    assert len(loose) == 1 and loose[0]["file"] == f"{CLAR}/loose-page-decisions.yaml"
    assert any(w.startswith(f"Two page YAMLs have the slug 'loose-page': {CLAR}/loose-page-decisions.yaml and "
                            f"{CLAR}/loose-page.yaml") for w in warnings)


def test_same_slug_twice_still_sends(capsys, project, portal, builds):
    page_yaml(project, "loose-page.yaml", "slug: loose-page\nstore_key: loose-page-v9\nname: Older copy\n")
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    try:
        assert code == 0, plan
        assert "loose-page" in json.loads(portal.posts()[0].content)["clarification_pages"]
    finally:
        cleanup(plan)


def test_yaml_that_does_not_parse_is_read_by_its_top_lines(project):
    page_yaml(project, "broken-decisions.yaml", "slug: broken\nstore_key: 'broken-v1'\n"
                                                "url: https://pages.example.com/clarifications/audit-log/\n"
                                                "name: [not closed\n")
    pages, _ = publish.page_index(project)
    broken = next(p for p in pages if p["slug"] == "broken")
    assert broken["store_key"] == "broken-v1" and broken["url"].endswith("/audit-log/")
    found, _, _ = publish.page_products(project, ["App", "Admin"], pages)
    assert found["broken"] == ["App", "Admin"], "linked by the Audit log Feature, prod Both"


def test_yaml_with_no_readable_slug_stops(capsys, project, portal, builds):
    page_yaml(project, "mystery.yaml", "name: [not closed\n")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and f"{CLAR}/mystery.yaml does not read as YAML" in result["error"]
    assert "Nothing was sent" in result["error"] and portal.requests == []


def test_bad_slug_is_skipped_with_a_warning(project):
    page_yaml(project, "Bad_Slug.yaml", "slug: Bad_Slug\nstore_key: bad-v1\n")
    pages, warnings = publish.page_index(project)
    assert "Bad_Slug" not in {p["slug"] for p in pages}
    assert any("Bad_Slug" in w and "not a page slug" in w for w in warnings)


def test_a_page_linked_only_by_an_unknown_prod_stops(capsys, project, portal, builds):
    """A misspelled prod must not move a page to the first product (or remove it from the right one)."""
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"].append(
        {"area": "Typo feature", "prod": "Admn", "s": "x",
         "clar": {"url": "https://pages.example.com/clarifications/loose-page/"}}))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and portal.requests == []
    assert ("The page loose-page (docs/BA/clarifications/loose-page-decisions.yaml) is linked only by Features "
            "whose prod is not a product with a Portal project (App, Admin): 'Typo feature' (prod 'Admn')"
            in result["error"])


def test_an_unknown_prod_beside_a_known_one_is_ignored_with_a_warning(project):
    pages = [{"slug": "x", "store_key": "x-v1", "url": "https://pages.example.com/x/", "file": "x.yaml"}]
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"].extend([
        {"area": "Gone product feature", "prod": "Extra", "s": "x", "clar": {"url": "https://pages.example.com/x/"}},
        {"area": "Admin feature", "prod": "Admin", "s": "x", "clar": {"url": "https://pages.example.com/x/"}}]))
    found, unlinked, warnings = publish.page_products(project, ["App", "Admin"], pages)
    assert found == {"x": ["Admin"]} and unlinked == []
    assert any("'Gone product feature' (prod 'Extra')" in w and "ignored" in w for w in warnings)


@pytest.mark.parametrize("page_url,feature_url", [("https://pages.example.com/x", "https://pages.example.com/x/"),
                                                  ("https://pages.example.com/x/", " https://pages.example.com/x ")])
def test_links_match_as_the_portal_matches_them(project, page_url, feature_url):
    """Both sides trimmed and a trailing / dropped, as the Portal compares clar_url with the page url."""
    pages = [{"slug": "x", "store_key": "x-v1", "url": page_url, "file": "x.yaml"}]
    edit_yaml(project / publish.DASHBOARD, lambda d: d["features"].append(
        {"area": "Admin feature", "prod": "Admin", "s": "x", "clar": {"url": feature_url}}))
    found, unlinked, _ = publish.page_products(project, ["App", "Admin"], pages)
    assert found == {"x": ["Admin"]} and unlinked == []


def test_top_lines_drop_comments_and_a_byte_order_mark():
    raw = "\ufeffslug: 'x'   # the page slug\nstore_key: \"x-v1\" # round key\nurl: https://p.example.com/x # link\n"
    assert publish.top_lines(raw) == {"slug": "x", "store_key": "x-v1", "url": "https://p.example.com/x"}


def test_unparsable_yaml_whose_slug_is_not_its_file_name_stops(capsys, project, portal, builds):
    page_yaml(project, "mismatch-decisions.yaml", "slug: something-else\nstore_key: x-v1\nname: [not closed\n")
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and portal.requests == []
    assert (f"{CLAR}/mismatch-decisions.yaml does not read as YAML, and its `slug:` line ('something-else') does "
            "not match its file name") in result["error"]


def test_a_yaml_that_is_not_utf8_stops(capsys, project, portal, builds):
    (project / CLAR / "latin-decisions.yaml").write_bytes("slug: latin\nname: caf\u00e9\n".encode("latin-1"))
    code, result, _ = run(capsys, project, "dashboard", "plan")
    assert code == 1 and portal.requests == []
    assert f"{CLAR}/latin-decisions.yaml is not UTF-8 text" in result["error"]


def test_no_dashboard_yaml_sends_every_page_with_the_first_product(project):
    (project / publish.DASHBOARD).unlink()
    pages, _ = publish.page_index(project)
    found, unlinked, warnings = publish.page_products(project, ["App", "Admin"], pages)
    assert set(found) == {"audit-log", "back-office", "loose-page", "sign-up-decisions"}
    assert all(v == ["App"] for v in found.values()) and unlinked == [] and warnings == []


def test_one_product_sends_every_page(capsys, project, portal, builds):
    one_product(project)
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    try:
        assert code == 0, plan
        sent = json.loads(portal.posts()[0].content)
        assert sent["clarification_pages"] == ["audit-log", "back-office", "loose-page", "sign-up-decisions"]
        assert not any("first product" in w for w in plan["warnings"])
    finally:
        cleanup(plan)


def test_pages_follow_the_profile_order_not_the_map_order(project):
    """The first product in tools.portal.products takes the unlinked pages."""
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(
        products={"Admin": "PORTAL_PUBLISH_KEY_ADMIN", "App": "PORTAL_PUBLISH_KEY_APP"}))
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    pages, _ = publish.dashboard_pages(project, prof, ["App", "Admin"], "Admin")
    assert "loose-page" in pages


@pytest.mark.skipif(not (EASY_PAYDAY / publish.MAP_PAGE).exists(), reason="the Acme Lending folder is not here")
def test_real_project_dashboard_plan_lists_17_and_6_pages(capsys, tmp_path, portal, builds):
    """A copy of the Acme Lending folder (read only) with two mapped keys, against the fake Portal."""
    root = tmp_path / "easy-payday"
    for rel in (publish.PROFILE, publish.DASHBOARD, publish.SLACK, publish.MAP_PAGE):
        if (EASY_PAYDAY / rel).exists():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(EASY_PAYDAY / rel, root / rel)
    (root / CLAR).mkdir(parents=True, exist_ok=True)
    for f in (EASY_PAYDAY / CLAR).glob("*.yaml"):
        shutil.copyfile(f, root / CLAR / f.name)
    edit_yaml(root / publish.PROFILE, lambda d: d.setdefault("tools", {}).update(portal={
        "url": URL, "products": {"AcmeLending": "PORTAL_PUBLISH_KEY_APP",
                                 "Bond Portal": "PORTAL_PUBLISH_KEY_ADMIN"}}))
    # the real project sends Timelines (tools.dashboard.timelines); this test checks the Dashboard send
    edit_yaml(root / publish.PROFILE, lambda d: (d["tools"].get("dashboard") or {}).pop("timelines", None))
    git(root, "init", "-q")
    git(root, "config", "user.name", "Sample BA")
    git(root, "config", "user.email", "ba@example.com")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text(f"PORTAL_PUBLISH_KEY_APP={KEY_APP}\nPORTAL_PUBLISH_KEY_ADMIN={KEY_ADMIN}\n",
                               encoding="utf-8")
    code, plan, _ = run(capsys, root, "dashboard", "plan")
    try:
        assert code == 0, plan
        easy, investor = (json.loads(r.content) for r in portal.posts())
        assert checks.check_publish(easy) is None and checks.check_publish(investor) is None
        assert len(easy["clarification_pages"]) == 17 and len(investor["clarification_pages"]) == 6
        assert "security-log-decisions" in easy["clarification_pages"]
        assert "security-log-decisions" in investor["clarification_pages"]
        unlinked = next(w for w in plan["warnings"] if "these Clarification pages" in w)
        assert unlinked.count("-decisions") == 3
    finally:
        cleanup(plan)


# ---- Contract 1.4.0: hot, stage_why, area_how, open ticket updated (Stories 3.11, 4.11) ----------------

TEMPLATE = publish.SKILLS / "ba-dashboard" / "map" / "template.html"


def why_bubbles() -> list[dict]:
    """Bubbles that walk every branch of the BA page's whyText(f)."""
    def t(*stages):
        return [{"key": f"APP-{i}", "stage": s} for i, s in enumerate(stages)]
    feature = {"settled": 2, "open": []}
    return [
        {"stageKey": "done", "tickets": t("done", "done", "done"), "answered": None, "specStatus": None},
        {"stageKey": "done", "tickets": t("done"), "answered": 1, "specStatus": "filed"},
        {"stageKey": "dev", "tickets": t("dev", "done", "dev", "qa"), "answered": None, "specStatus": None},
        {"stageKey": "qa", "tickets": t("qa"), "answered": 0.5, "specStatus": None},
        {"stageKey": "ready", "tickets": [], "answered": None, "specStatus": None},
        {"stageKey": "dev", "tickets": [], "answered": None, "specStatus": None, "feature": feature},
        {"stageKey": "spec", "tickets": [], "answered": None, "specStatus": None},
        {"stageKey": "spec", "tickets": t("done", "done"), "answered": 2 / 3, "specStatus": "draft"},
        {"stageKey": "spec", "tickets": t("ready"), "answered": 0.125, "specStatus": None},
        {"stageKey": "spec", "tickets": t("done", "ready"), "answered": 0.005, "specStatus": "in-review"},
        {"stageKey": "concept", "tickets": [], "answered": None, "specStatus": None},
        {"stageKey": "concept", "tickets": [], "answered": None, "specStatus": None, "feature": feature},
        {"stageKey": "concept", "tickets": [], "answered": 0.335, "specStatus": None, "feature": feature},
    ]


def test_stage_why_lines():
    lines = [publish.stage_why(b) for b in why_bubbles()]
    assert lines == [
        "Done: all 3 tickets Done",
        "Done: all 1 ticket Done",
        "In dev, its slowest open ticket. Tickets: 1 Done, 1 In QA, 2 In dev",
        "In QA, its slowest open ticket. Tickets: 1 In QA",
        "Ready for dev, no tickets linked yet",
        "In dev, no tickets linked yet",
        "Spec & design: not approved yet",
        "Spec & design: 67% of questions answered, spec is draft, earlier tickets all Done",
        "Spec & design: 13% of questions answered",
        "Spec & design: 1% of questions answered, spec is in-review",
        "Concept: only a name so far",
        "Concept: concept or idea, no spec yet",
        "Concept: concept or idea, no spec yet, 34% of questions answered",
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_stage_why_matches_the_ba_pages_own_code(tmp_path):
    """Runs whyText(f) from map/template.html in node on the same bubbles: the Portal gets the BA page's line."""
    html_text = TEMPLATE.read_text(encoding="utf-8")

    def grab(start: str, end: str) -> str:
        at = html_text.index(start)
        return html_text[at:html_text.index(end, at) + len(end)]

    js = "\n".join([
        grab("const STATUS = {", "};"), grab("const ORDER = [", "];"),
        grab("function mix(stages)", "}"), grab("const plural = (n, w) =>", ";"),
        grab("function whyText(f) {", "\n}"),
        f"const bubbles = {json.dumps(why_bubbles())};",
        "process.stdout.write(JSON.stringify(bubbles.map(whyText)));",
    ])
    script = tmp_path / "why.js"
    script.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(r.stdout) == [publish.stage_why(b) for b in why_bubbles()]


def test_stage_why_is_left_out_when_the_page_lacks_its_data():
    b = why_bubbles()[2]
    for field in ("answered", "specStatus", "tickets", "stageKey"):
        assert publish.stage_why({k: v for k, v in b.items() if k != field}) == "", field
    assert publish.stage_why({**b, "stageKey": "blocked"}) == ""


def test_feature_sends_stage_why_and_area_how_when_the_page_has_them(project):
    def add(data):
        sign_up = data["epics"][0]["features"][0]
        sign_up.update(answered=2 / 3, specStatus="draft", areaHow="from its tickets")
        data["epics"][4]["features"][0].update(areaHow="x" * 201)               # identity-check: too long
    change_map(project, add)
    app = {f["id"]: f for f in payload_of(project, "App")["features"]}
    assert app["sign-up"]["stage_why"] == "Spec & design: 67% of questions answered, spec is draft"
    assert app["sign-up"]["area_how"] == "from its tickets"
    assert "stage_why" not in app["identity-check"] and "area_how" not in app["identity-check"]
    assert "stage_why" not in app["audit-log"] and "area_how" not in app["audit-log"]   # an older page: left out
    assert checks.check_publish(payload_of(project, "App")) is None


def test_items_send_hot(project):
    def mark(d):
        d["awaiting"][4]["hot"] = True                                           # Refund rules
    edit_yaml(project / publish.DASHBOARD, mark)
    hot = {i["title"]: i["hot"] for i in payload_of(project, "App")["items"]}
    assert hot["Refund rules"] is True
    assert {t for t, h in hot.items() if h} == {"Refund rules"}
    assert checks.check_publish(payload_of(project, "App")) is None


def test_open_tickets_send_updated_only_when_it_is_a_real_date(project):
    def odd(data):
        opens = data["epics"][0]["jira"]["open"]
        opens[3]["updated"] = "2026-02-30"                                       # APP-44: no such day
        opens[1]["updated"] = "2026-09-01T10:00:00.000+0000"                     # APP-42: not UTC Z
        opens[0]["updated"] = "2026-10-19T08:15:00.000Z"                         # APP-41: a UTC time
        del opens[7]["updated"]                                                  # APP-48: none
    change_map(project, odd)
    tickets = {t["key"]: t for t in payload_of(project, "App")["areas"][0]["jira"]["open_tickets"]}
    assert "updated" not in tickets["APP-44"] and "updated" not in tickets["APP-42"]
    assert tickets["APP-41"]["updated"] == "2026-10-19T08:15:00.000Z"
    assert tickets["APP-46"]["updated"] == "2026-10-15"
    assert checks.check_publish(payload_of(project, "App")) is None


def test_real_build_sends_stage_why_and_area_how(project):
    """build.py writes answered, specStatus and areaHow on every bubble, so every Feature gets both lines."""
    (project / publish.MAP_PAGE).unlink()
    publish.run_build(project, False)
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    data = publish.read_map(project)
    app = publish.build_payload(project, prof, "App", data)[0]
    assert checks.check_publish(app) is None
    by_id = {f["id"]: f for f in app["features"]}
    assert all(f["stage_why"] and f["area_how"] for f in app["features"])
    assert by_id["sign-up"]["area_how"] == "no tickets and no area set"
    assert by_id["identity-check"]["stage_why"] == "In dev, no tickets linked yet"


# ---- timeline plan / send / discard (contract 1.6.0) ---------------------------------------------------

TL_SMALL = VALID / "timeline-1-small.json"
APP_TIMELINE = """product:
  name: Sample App
  dashboard: App
  tracker: none
start: 2026-05-01
groups:
  - name: Getting in
    areas: [Onboarding]
"""
ADMIN_TIMELINE = APP_TIMELINE.replace("Sample App", "Sample Admin").replace("dashboard: App", "dashboard: Admin")
SIGN_UP_URL = "https://pages.example.com/clarifications/sign-up/"


def ba_build() -> dict:
    """A Timeline build as build.py --json writes it for the BA page: the small timeline/1 fixture turned back
    into the page's data (no envelope or Portal fields; clar artifact links; pages, dashboardUrl, decided urls;
    nulls)."""
    doc = read(TL_SMALL)
    for k in ("contract", "sent_at", "sent_by", "ba_tools_version", "source_commit", "client_contacts",
              "clarification_pages", "suggestion_status"):
        doc.pop(k)
    rows = [f for g in doc["groups"] for a in g["areas"] for f in a["features"]]
    for i, f in enumerate(rows):
        page = f.pop("page", None)
        f["clar"] = None
        f.setdefault("clarLabel", None)
        f.setdefault("doneDate", None)
        if page and i == 0:
            f["clar"] = SIGN_UP_URL.rstrip("/")             # matched with or without the trailing /
        elif page:
            f["clar"] = "https://claude.ai/artifact/NotAPortalPage0001"
    for p in doc["pins"]:
        for d in p.get("decided") or []:
            d["url"] = "https://claude.ai/artifact/SomePage0000000001"
    doc["pages"] = [{"slug": "sign-up-decisions", "url": SIGN_UP_URL}]
    doc["dashboardUrl"] = "https://claude.ai/artifact/TheBaDashboard00001"
    return doc


@pytest.fixture
def timelines(project, monkeypatch):
    """The sample repo with a Timeline data file per product; the build is stubbed with ba_build()."""
    folder = project / publish.TIMELINE_DIR
    (folder / "admin").mkdir(parents=True)
    (folder / "app-timeline.yaml").write_text(APP_TIMELINE, encoding="utf-8")
    (folder / "admin" / "admin-timeline.yaml").write_text(ADMIN_TIMELINE, encoding="utf-8")
    (folder / "notes.yaml").write_text("just: notes\n", encoding="utf-8")
    calls: list[Path] = []
    monkeypatch.setattr(publish, "run_timeline_build", lambda root, f: calls.append(f) or ba_build())
    return calls


@pytest.fixture
def tl_portal(portal):
    portal.accepted = ["dashboard/1", "dashboard/2", "timeline/1", "clarification/1"]
    portal.dry = read(VALID / "publish-reply-1-timeline-1-dry-run.json")
    portal.sent = read(VALID / "publish-reply-1-timeline-1-sent.json")
    return portal


def test_timeline_files_are_found_by_product(project, timelines):
    found = publish.timeline_files(project)
    assert {p: f.relative_to(project).as_posix() for p, f in found.items()} == {
        "App": "docs/BA/timeline/app-timeline.yaml", "Admin": "docs/BA/timeline/admin/admin-timeline.yaml"}


def test_two_timeline_files_for_one_product_stop(capsys, project, timelines, tl_portal):
    (project / publish.TIMELINE_DIR / "other-timeline.yaml").write_text(APP_TIMELINE, encoding="utf-8")
    code, out, _ = run(capsys, project, "timeline", "plan")
    assert code == 1 and "Two Timeline data files are for App" in out["error"]
    assert tl_portal.requests == []


def test_timeline_payload_turns_the_ba_page_data_into_timeline_1(project, timelines):
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    payload, warnings = publish.timeline_payload(project, prof, "App", ba_build(), ["App", "Admin"],
                                                 "2026-11-06T10:00:00.000Z")
    assert checks.check_publish(payload) is None
    assert payload["contract"] == "timeline/1" and payload["sent_by"] == "Sample BA"
    assert payload["clarification_pages"] == ["audit-log", "loose-page", "sign-up-decisions"]
    assert [c["name"] for c in payload["client_contacts"]] == ["Maria Lopez", "Tom Baker", "Priya Shah"]
    for gone in ("pages", "dashboardUrl"):
        assert gone not in payload
    rows = [f for _, f in checks.timeline_rows(payload)]
    assert rows[0]["page"] == "sign-up-decisions" and rows[0]["clarLabel"].startswith("Clarification page")
    assert all("clar" not in f for f in rows)
    others = [f for f in rows[1:] if "page" in f or "clarLabel" in f]
    assert others == [], "an artifact link with no Portal page gives no page button"
    assert any("NotAPortalPage0001" in w for w in warnings)
    assert all("url" not in d for p in payload["pins"] for d in p.get("decided") or [])
    assert "null" not in json.dumps(payload)
    keys = [t["key"] for f in rows for t in f.get("todos") or []]
    assert keys == [t["key"] for f in checks.timeline_rows(read(TL_SMALL)) for t in f[1].get("todos") or []], \
        "to-do keys are sent as the build has them"


def test_timeline_payload_keeps_figma_links_and_row_kinds(project, timelines):
    """Contract 1.10.0: kind, asked, figma and figmaWhere go in as the build has them."""
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    payload, warnings = publish.timeline_payload(project, prof, "App", ba_build(), ["App", "Admin"])
    assert checks.check_publish(payload) is None
    rows = [f for _, f in checks.timeline_rows(payload)]
    assert {f["kind"] for f in rows} == {"build", "new", "bug"}
    assert rows[0]["figma"].startswith("https://www.figma.com/") and rows[0]["figmaWhere"]
    assert rows[0]["asked"]
    assert any("figma" in q for f in rows for q in f.get("requests") or [])
    assert not any("Figma links" in w for w in warnings)


def test_timeline_payload_leaves_out_a_link_that_is_not_figma(project, timelines):
    """Contract 1.10.0: a figma that is not a https://www.figma.com/ link is left out with its figmaWhere, with a
    warning, so the send still passes."""
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    build = ba_build()
    rows = [f for g in build["groups"] for a in g["areas"] for f in a["features"]]
    rows[0]["figma"] = "https://example.com/not-figma"
    q = next(q for f in rows for q in f.get("requests") or [] if "figma" in q)
    q["figma"] = "javascript:alert(1)"
    payload, warnings = publish.timeline_payload(project, prof, "App", build, ["App", "Admin"])
    assert checks.check_publish(payload) is None
    sent = [f for _, f in checks.timeline_rows(payload)]
    assert "figma" not in sent[0] and "figmaWhere" not in sent[0]
    assert not any("figma" in r for f in sent for r in f.get("requests") or [])
    warn = next(w for w in warnings if "Figma links" in w)
    assert "https://example.com/not-figma" in warn and "javascript:alert(1)" in warn


def test_timeline_plan_dry_runs_each_product_then_sends(capsys, project, timelines, tl_portal):
    code, plan, _ = run(capsys, project, "timeline", "plan")
    assert code == 0 and plan["ok"] is True, plan
    assert [f.relative_to(project).as_posix() for f in timelines] == [
        "docs/BA/timeline/app-timeline.yaml", "docs/BA/timeline/admin/admin-timeline.yaml"]
    got = by_product(plan)
    assert list(got) == ["App", "Admin"]
    status, dry = tl_portal.requests[:2]
    assert str(dry.url) == f"{URL}/api/v1/publish/dashboard?dry_run=1"
    assert json.loads(dry.content)["contract"] == "timeline/1"
    shown = got["App"]["client_list"]
    for words in ('App → Portal project "Sample App"', "new dashboard is on its way", "Rows by stage:",
                  "BA to-do (", "Waiting (", "Next-call agenda (", "Pins (7)", "Client contacts (2)"):
        assert words in shown, words
    # contract 1.9.0: the Coming up list, one line per item
    for words in ("Coming up (3)", "- Switch off the old chat on the website — deadline, 2026-12-17 · needs ",
                  "- New agreement — every customer signs it — planned, after ", "planned, no date yet"):
        assert words in shown, words
    payload_file = Path(got["App"]["payload"])
    assert read_saved_kind(payload_file) == "timeline"
    code, sent, _ = run(capsys, project, "timeline", "send", "--payload", str(payload_file))
    assert code == 0 and sent["ok"] is True and sent["sent"] == "Timeline", sent
    assert 'Sent the App Timeline to Portal project "Sample App"' in sent["report"]
    assert tl_portal.posts()[-1].content == dry.content, "the dry run and the real send carry the same bytes"
    assert str(tl_portal.posts()[-1].url) == f"{URL}/api/v1/publish/dashboard"
    assert not payload_file.exists()
    code, gone, _ = run(capsys, project, "timeline", "discard", "--payload", got["Admin"]["payload"])
    assert code == 0 and gone["sent"] is None and "for Admin" in gone["report"]


def test_timeline_upcoming_problem_names_the_item():
    doc = read(VALID / "timeline-1-small.json")
    doc["upcoming"][1]["after"] = "no-such-feature"
    lines = publish.timeline_problem_lines(checks.check_publish(doc)["details"], doc)
    assert lines == ["the Timeline data file in docs/BA/timeline/ → upcoming: → the item 'New agreement — every customer "
                     "signs it' (new-agreement) → after: names a feature \"no-such-feature\" that is "
                     "not in this Publish. (/upcoming/1/after)"]


def read_saved_kind(path: Path) -> str | None:
    return publish.payload_kind(path)


def test_timeline_plan_for_one_product(capsys, project, timelines, tl_portal):
    code, plan, _ = run(capsys, project, "timeline", "plan", "--product", "Admin")
    try:
        assert code == 0 and [p["product"] for p in plan["products"]] == ["Admin"], plan
        assert len(timelines) == 1
    finally:
        cleanup(plan)
    code, out, _ = run(capsys, project, "timeline", "plan", "--product", "Nope")
    assert code == 1 and "There is no Timeline for 'Nope'" in out["error"]


def test_timeline_plan_stops_on_a_portal_without_timeline(capsys, project, timelines, portal):
    code, out, _ = run(capsys, project, "timeline", "plan")
    assert code == 1 and "does not accept timeline/1 yet" in out["error"]
    assert portal.posts() == []


def test_timeline_plan_stops_on_a_broken_build_before_sending(capsys, project, timelines, tl_portal, monkeypatch):
    def broken(root, f):
        b = ba_build()
        b["groups"][0]["areas"][0]["features"][1]["id"] = b["groups"][0]["areas"][0]["features"][0]["id"]
        return b
    monkeypatch.setattr(publish, "run_timeline_build", broken)
    code, out, _ = run(capsys, project, "timeline", "plan")
    assert code == 1 and "does not match the contract" in out["error"]
    assert "the Timeline build → the row" in out["error"] and "is used twice" in out["error"]
    assert tl_portal.requests == []


def test_timeline_plan_without_a_data_file_stops(capsys, project, tl_portal):
    code, out, _ = run(capsys, project, "timeline", "plan")
    assert code == 1 and "No Timeline data file" in out["error"]


def test_timeline_and_dashboard_payloads_are_not_swapped(capsys, project, timelines, tl_portal):
    code, plan, _ = run(capsys, project, "timeline", "plan", "--product", "App")
    path = plan["products"][0]["payload"]
    try:
        code, out, _ = run(capsys, project, "dashboard", "send", "--payload", path)
        assert code == 1 and "is a timeline payload" in out["error"] and Path(path).exists()
    finally:
        cleanup(plan)


def test_run_timeline_build_reads_the_json_and_deletes_it(project, monkeypatch, tmp_path):
    script = tmp_path / "build.py"
    script.write_text("import json, sys\n"
                      "out = sys.argv[sys.argv.index('--json') + 1]\n"
                      "open(out, 'w', encoding='utf-8').write(json.dumps({'groups': [], 'seen': sys.argv[1]}))\n",
                      encoding="utf-8")
    monkeypatch.setattr(publish, "TIMELINE_PY", script)
    data_file = project / "docs" / "BA" / "timeline" / "x-timeline.yaml"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("groups: []\n", encoding="utf-8")
    assert publish.run_timeline_build(project, data_file) == {"groups": [], "seen": str(data_file)}
    assert list(Path(tempfile.gettempdir()).glob("portal-timeline-build-*.json")) == []
    script.write_text("import sys\nsys.exit('the tracker cache is missing')\n", encoding="utf-8")
    with pytest.raises(publish.Stop, match="the tracker cache is missing"):
        publish.run_timeline_build(project, data_file)


REAL_TIMELINES = [
    (EASY_PAYDAY, "AcmeLending", "docs/BA/timeline/epd-timeline.html"),
    (EASY_PAYDAY, "Bond Portal", "docs/BA/timeline/bond-portal/ip-timeline.html"),
    (Path(r"C:\Projects\nwe"), "NWE", "docs/BA/timeline/nwe-timeline.html"),
]


@pytest.mark.parametrize("repo,product,page", REAL_TIMELINES, ids=["easy-payday", "bond-portal", "nwe"])
def test_real_timeline_builds_pass_the_contract(repo, product, page):
    """The three real Timeline builds (the DATA of their built pages, read only) turn into valid timeline/1 sends
    under 5 MB."""
    if not (repo / page).exists():
        pytest.skip(f"{repo / page} is not on this machine")
    text = (repo / page).read_text(encoding="utf-8")
    at = text.index("const DATA = ") + len("const DATA = ")
    build, _ = json.JSONDecoder().raw_decode(text, at)
    prof = yaml.safe_load((repo / publish.PROFILE).read_text(encoding="utf-8"))
    found = publish.timeline_files(repo)
    assert product in found
    products = publish.portal_products(repo, prof, found)
    payload, _ = publish.timeline_payload(repo, prof, product, build, products, "2026-11-06T10:00:00.000Z")
    assert checks.check_publish(payload) is None
    assert len(publish.encode(payload)) < publish.MAX_BYTES
    linked = sum(1 for f in build_rows(build) if f.get("clar"))
    assert sum(1 for _, f in checks.timeline_rows(payload) if "page" in f) <= linked


def build_rows(build: dict) -> list[dict]:
    return [f for g in build["groups"] for a in g["areas"] for f in a["features"]]


def tl_saved(root: Path, product: str = "App", key_name: str = "PORTAL_PUBLISH_KEY_APP") -> Path:
    """A payload file as `timeline plan` writes it."""
    prof = yaml.safe_load((root / publish.PROFILE).read_text(encoding="utf-8"))
    payload, _ = publish.timeline_payload(root, prof, product, ba_build(), ["App", "Admin"])
    return publish.save_timeline(product, f"Sample {product}", URL, key_name, publish.encode(payload))


def test_timeline_pages_go_with_the_same_product_as_in_a_dashboard_send(project, monkeypatch):
    """Only Admin has a Timeline: a page no Feature links still goes with App (the first product), as in
    `dashboard plan`, and not with Admin."""
    folder = project / publish.TIMELINE_DIR / "admin"
    folder.mkdir(parents=True)
    (folder / "admin-timeline.yaml").write_text(ADMIN_TIMELINE, encoding="utf-8")
    prof = yaml.safe_load((project / publish.PROFILE).read_text(encoding="utf-8"))
    found = publish.timeline_files(project)
    assert list(found) == ["Admin"]
    products = publish.portal_products(project, prof, found)
    assert products == ["App", "Admin"]
    payload, _ = publish.timeline_payload(project, prof, "Admin", ba_build(), products)
    assert "loose-page" not in payload["clarification_pages"]
    assert payload["clarification_pages"] == publish.build_payload(project, prof, "Admin")[0]["clarification_pages"]


def test_dashboard_plan_warns_that_it_replaces_a_timeline(capsys, project, portal, builds, timelines):
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    try:
        assert code == 0, plan
        said = [w for w in plan["warnings"] if "replaces" in w]
        assert len(said) == 2 and all("`timeline plan`" in w and "Map and Board back" in w for w in said)
        assert "App has a Timeline (docs/BA/timeline/app-timeline.yaml)" in said[0]
    finally:
        cleanup(plan)


def test_dashboard_plan_stops_when_the_timelines_are_the_dashboard(capsys, project, portal, builds, timelines):
    edit_yaml(project / publish.PROFILE, lambda d: d.setdefault("tools", {}).setdefault("dashboard", {}).update(
        timelines={"App": {"data": "docs/BA/timeline/app-timeline.yaml", "url": "https://claude.ai/artifact/x"}}))
    code, plan, _ = run(capsys, project, "dashboard", "plan")
    assert code != 0 and "`timeline plan`" in plan["error"] and "App" in plan["error"], plan
    assert not portal.posts()


def test_no_nulls_drops_null_fields_and_null_list_entries():
    assert publish.no_nulls({"a": None, "b": [1, None, {"c": None, "d": [None]}], "e": "x"}) == \
        {"b": [1, {"d": []}], "e": "x"}


def test_timeline_send_stops_when_the_key_now_opens_another_project(capsys, project, tl_portal):
    path = tl_saved(project)
    tl_portal.projects[KEY_APP] = "Someone Else"
    try:
        code, result, _ = run(capsys, project, "timeline", "send", "--payload", str(path))
        assert code == 1
        assert ('The key in PORTAL_PUBLISH_KEY_APP now opens Portal project "Someone Else", but `timeline plan` '
                'showed the App Timeline going to "Sample App"') in result["error"]
        assert "run `timeline plan`" in result["error"] and "Nothing was sent" in result["error"]
        assert tl_portal.posts() == [] and path.exists(), "nothing sent; the payload file is kept"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("exc", [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("dropped")])
def test_timeline_real_send_without_a_reply_may_have_arrived(capsys, project, tl_portal, exc):
    path = tl_saved(project)
    tl_portal.post_exc = exc
    try:
        code, result, _ = run(capsys, project, "timeline", "send", "--payload", str(path))
        assert code == 1
        assert "may have arrived" in result["error"] and "run `timeline send` again" in result["error"]
        assert "Nothing was sent" not in result["error"]
        assert path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_timeline_send_after_the_portal_address_changed(capsys, project, tl_portal):
    path = tl_saved(project)
    edit_yaml(project / publish.PROFILE, lambda d: d["tools"]["portal"].update(url="https://portal.example.com"))
    code, result, _ = run(capsys, project, "timeline", "send", "--payload", str(path))
    assert code == 1 and "Run `timeline plan` again" in result["error"]
    assert tl_portal.requests == [] and not path.exists()


# ---- decisions on Client suggestions (contract 1.8.0) --------------------------------------------------

SUG_A = "019a5a10-0b00-7c00-8a00-000000000001"
SUG_B = "019a5a10-0b00-7c00-8a00-000000000002"


def test_timeline_plan_sends_the_products_decisions(capsys, project, timelines, tl_portal):
    (project / publish.TIMELINE_DIR / "suggestions.yaml").write_text(
        f"- id: {SUG_A}\n  status: accepted\n  reason: Planned for the next release.\n"
        f"- id: {SUG_B.upper()}\n  status: Declined\n  reason: 'Out of scope: not for the pilot.'\n",
        encoding="utf-8")
    code, plan, _ = run(capsys, project, "timeline", "plan")
    try:
        assert code == 0, plan
        dry = [json.loads(r.content) for r in tl_portal.posts() if "dry_run=1" in str(r.url)]
        app, admin = dry
        assert app["suggestion_status"] == [
            {"id": SUG_A, "status": "accepted", "reason": "Planned for the next release."},
            {"id": SUG_B, "status": "declined", "reason": "Out of scope: not for the pilot."}]
        assert "suggestion_status" not in admin, "the Admin product's folder has no decisions file"
        shown = by_product(plan)["App"]["client_list"]
        assert "Decisions on Client suggestions (2)" in shown
        assert f"- {SUG_A}: Accepted — Planned for the next release." in shown
    finally:
        cleanup(plan)


@pytest.mark.parametrize("text, words", [
    (f"- id: {SUG_A}\n  status: maybe\n", "decision 1: the status \"maybe\" must be accepted or declined"),
    ("- id: suggestion-1\n  status: accepted\n", "the id \"suggestion-1\" is not a suggestion id"),
    (f"- id: {SUG_A}\n  status: accepted\n- id: {SUG_A}\n  status: declined\n", "decision 2 decides the same"),
    (f"- id: {SUG_A}\n  status: accepted\n  why: x\n", "a field a decision does not take: why"),
    (f"id: {SUG_A}\n", "must be a list of decisions"),
    ("- [unclosed\n", "could not be read"),
])
def test_a_bad_decision_stops_timeline_plan_before_anything_is_sent(capsys, project, timelines, tl_portal, text, words):
    (project / publish.TIMELINE_DIR / "suggestions.yaml").write_text(text, encoding="utf-8")
    code, out, _ = run(capsys, project, "timeline", "plan")
    assert code == 1 and words in out["error"], out
    assert "docs/BA/timeline/suggestions.yaml" in out["error"] and "Nothing was sent" in out["error"]
    assert tl_portal.posts() == []


def test_decisions_file_rules(project):
    data = project / publish.TIMELINE_DIR / "app-timeline.yaml"
    data.parent.mkdir(parents=True, exist_ok=True)
    assert publish.suggestion_status(project, data) is None, "no file: no suggestion_status"
    (data.parent / "suggestions.yaml").write_text("", encoding="utf-8")
    assert publish.suggestion_status(project, data) == [], "an empty file clears every decision"
    (data.parent / "suggestions.yaml").write_text(f"- id: {SUG_A}\n  status: declined\n", encoding="utf-8")
    assert publish.suggestion_status(project, data) == [{"id": SUG_A, "status": "declined", "reason": ""}]
