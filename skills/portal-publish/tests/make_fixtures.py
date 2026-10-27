"""Writes contract/fixtures/ — run with `uv run python tests/make_fixtures.py` after changing it.

The data is synthetic (no client data), sized like Acme Lending: 18 Features, 148 Items.
Each invalid case is the small base file with one thing broken, plus expected.json.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "contract" / "fixtures"

AREAS = ["Onboarding", "Loans", "Repayments", "Payroll sync", "Notifications", "Back office"]
STAGES = ["concept", "spec", "ready", "dev", "qa", "done"]
RELEASES = [("1.4", True), ("1.5", False), ("1.6", False)]
FEATURES = [
    ("Sign-up with phone number", "Sign-up", "Onboarding"),
    ("Identity check", "ID check", "Onboarding"),
    ("Employer search", None, "Onboarding"),
    ("Advance request", "Advance", "Loans"),
    ("Advance limits by salary band", "Limits", "Loans"),
    ("Fee preview before confirming", "Fee preview", "Loans"),
    ("Early repayment", None, "Repayments"),
    ("Repayment on payday", "Payday repay", "Repayments"),
    ("Failed repayment retries", "Retries", "Repayments"),
    ("Payroll file import", "Payroll import", "Payroll sync"),
    ("Payroll provider connections", None, "Payroll sync"),
    ("Deduction report for employers", "Deductions", "Payroll sync"),
    ("Push notifications", "Push", "Notifications"),
    ("Email receipts", None, "Notifications"),
    ("SMS reminders before payday", "SMS", "Notifications"),
    ("Admin user search", "User search", "Back office"),
    ("Refunds and write-offs", "Refunds", "Back office"),
    ("Monthly finance export", "Finance export", "Back office"),
]
PEOPLE = ["Maria Lopez", "Tom Baker", "Priya Shah", "Dev team", "Anna", "Jonas Berg"]
ASKS = [
    "Confirm the wording for", "Send the sample file for", "Approve the screen for",
    "Decide the limit for", "Share the test account for", "Review the flow for",
    "Agree the copy for", "Check the numbers in",
]


def slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:40]


def item_key(kind: str, title: str) -> str:
    return hashlib.sha1(f"{kind}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


def feature(n: int, title: str, short: str | None, area: str) -> dict:
    stage = STAGES[n % len(STAGES)]
    f = {
        "id": slug(title),
        "title": title,
        "summary": f"<p class=\"lead\">{title} — what it does for the employee.</p>"
                   f"<p>Status: <strong>{stage}</strong>. Next step agreed on the last call.</p>",
        "stage": stage,
        "map_area": area,
    }
    if short:
        f["short"] = short
    if n % 3 == 0:
        f["open"] = [f"Which employers get {title.lower()} first?", "Is the copy final in every language?"]
    if n % 4 == 1:
        f["clar_url"] = f"https://pages.example.com/clarifications/{slug(title)}/"
    if stage != "concept":
        f["releases"] = [RELEASES[n % len(RELEASES)][0]]
    if stage == "done":
        f["done_date"] = f"2026-10-{(n % 20) + 1:02d}"
    return f


def item(n: int, features: list[dict]) -> dict:
    kind = "waiting" if n % 3 else "agenda"
    feat = features[n % len(features)]
    title = f"{ASKS[n % len(ASKS)]} {feat['title'].lower()} (#{n + 1})"
    it = {
        "key": item_key(kind, title),
        "kind": kind,
        "who": PEOPLE[n % len(PEOPLE)] + (" then Dev team" if n % 7 == 0 else ""),
        "since": f"2026-{9 + n % 2:02d}-{(n % 28) + 1:02d}",
        "title": title,
    }
    if n % 10 != 9:
        it["feature"] = feat["id"]
    if n % 2 == 0:
        it["text"] = "<p>We need this before the next build. <em>A short answer is fine.</em></p>"
    if kind == "waiting" and n % 4 == 1:
        it["how_to_send"] = "Reply in the project Slack channel or by email to the BA."
    return it


def dashboard(n_features: int = 18, n_items: int = 148) -> dict:
    feats = [feature(i, *FEATURES[i % len(FEATURES)]) for i in range(n_features)]
    if n_features > len(FEATURES):  # keep ids unique when the list repeats
        for i, f in enumerate(feats):
            f["id"] = f"{f['id'][:34]}-{i}"
    return {
        "contract": "dashboard/1",
        "sent_at": "2026-10-27T09:30:00.000Z",
        "sent_by": "Sample BA",
        "ba_tools_version": "0.8.0",
        "source_commit": "4be1f0c9a2d7e3b5f6a8c1d0e9f7a6b5c4d3e2f1",
        "features": feats,
        "items": [item(i, feats) for i in range(n_items)],
        "areas": AREAS,
        "release_rows": [{"name": n, "released": r} for n, r in RELEASES],
        "client_contacts": [
            {"name": "Maria Lopez", "email": "maria.lopez@example.com", "slack": "maria.lopez"},
            {"name": "Tom Baker", "email": "tom.baker@example.com"},
            {"name": "Priya Shah", "slack": "U02ABCD1234"},
        ],
    }


def small() -> dict:
    return dashboard(4, 10)


def invalid_cases() -> dict[str, tuple[dict, dict]]:
    cases: dict[str, tuple[dict, dict]] = {}

    def case(name, doc, code, check, path):
        cases[name] = (doc, {"code": code, "check": check, "path": path})

    d = small(); d["features"][0]["owner"] = "Sample BA"
    case("unknown-field-feature", d, "contract_invalid", "schema", "/features/0/owner")
    d = small(); d["next_call"] = "2026-11-03"
    case("unknown-field-top", d, "contract_invalid", "schema", "/next_call")
    d = small(); del d["features"][1]["title"]
    case("missing-feature-title", d, "contract_invalid", "schema", "/features/1/title")
    d = small(); del d["sent_by"]
    case("missing-sent-by", d, "contract_invalid", "schema", "/sent_by")
    d = dashboard(301, 10)
    case("too-many-features", d, "contract_invalid", "schema", "/features")
    d = dashboard(4, 1001)
    case("too-many-items", d, "contract_invalid", "schema", "/items")
    d = small(); d["client_contacts"] = [{"name": f"Contact {i}"} for i in range(201)]
    case("too-many-contacts", d, "contract_invalid", "schema", "/client_contacts")
    d = small(); d["features"][0]["title"] = "A" * 201
    case("feature-title-too-long", d, "contract_invalid", "schema", "/features/0/title")
    d = small(); d["items"][0]["title"] = "B" * 301
    case("item-title-too-long", d, "contract_invalid", "schema", "/items/0/title")
    d = small(); d["features"][2]["stage"] = "testing"
    case("bad-stage", d, "contract_invalid", "schema", "/features/2/stage")
    d = small(); d["items"][3]["since"] = "27/10/2026"
    case("bad-date", d, "contract_invalid", "schema", "/items/3/since")
    d = small(); d["features"][0]["done_date"] = "2026-02-30"
    case("impossible-date", d, "contract_invalid", "schema", "/features/0/done_date")
    d = small(); d["client_contacts"][0]["email"] = "maria.lopez"
    case("bad-email", d, "contract_invalid", "schema", "/client_contacts/0/email")
    d = small(); d["sent_at"] = "2026-10-27T09:30:00Z"
    case("bad-time", d, "contract_invalid", "schema", "/sent_at")
    d = small(); d["features"][3]["id"] = d["features"][1]["id"]
    case("duplicate-feature-id", d, "contract_invalid", "unique_feature_id", "/features/3/id")
    d = small(); d["items"][5]["key"] = d["items"][2]["key"]
    case("duplicate-item-key", d, "contract_invalid", "unique_item_key", "/items/5/key")
    d = small(); d["features"][0]["title"] = "Sign-up &mdash; phone number"
    case("html-entity", d, "contract_invalid", "no_html_entities", "/features/0/title")
    d = small(); d["contract"] = "dashboard/2"
    case("version-not-accepted", d, "contract_version_not_accepted", "contract_version", "/contract")
    d = small(); d["client_contacts"][0]["email"] = "maria@localhost"
    case("email-no-dot-domain", d, "contract_invalid", "schema", "/client_contacts/0/email")
    d = small(); d["sent_at"] = "2026-12-31T23:59:60.000Z"
    case("leap-second", d, "contract_invalid", "schema", "/sent_at")
    d = small(); d["features"][1]["clar_url"] = "pages.example.com/x"
    case("bad-uri", d, "contract_invalid", "schema", "/features/1/clar_url")
    d = small(); d["contract"] = 1
    case("contract-not-text", d, "contract_invalid", "schema", "/contract")
    d = small(); d["items"][0]["key"] = d["items"][0]["key"].upper().replace("0", "A")[:12].ljust(12, "A")
    case("bad-item-key", d, "contract_invalid", "schema", "/items/0/key")
    d = small(); d["features"][0]["title"] = ""
    case("empty-required-text", d, "contract_invalid", "schema", "/features/0/title")
    d = small(); d["features"][0]["open"] = ["Which employers first?", "Is the copy final &hellip;"]
    case("entity-in-list", d, "contract_invalid", "no_html_entities", "/features/0/open/1")
    return cases


def expected_result(name: str, doc: dict, stated: dict) -> dict:
    """Every (check, path) pair the check gives, sorted. Both runners compare this set exactly.
    The pair the case was written for must be among them, with the stated code."""
    import checks  # the skill folder is on sys.path (see main guard)

    result = checks.check_publish(doc)
    assert result is not None, f"{name}: passes, but should fail"
    assert result["code"] == stated["code"], f"{name}: {result['code']}"
    pairs = sorted({(d["check"], d["path"]) for d in result["details"]})
    assert (stated["check"], stated["path"]) in pairs, f"{name}: {pairs}"
    return {"code": result["code"], "details": [{"check": c, "path": p} for c, p in pairs]}


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    for sub in ("valid", "invalid"):
        shutil.rmtree(FIXTURES / sub, ignore_errors=True)
    dump(FIXTURES / "valid" / "dashboard-1-easy-payday-size.json", dashboard())
    dump(FIXTURES / "valid" / "dashboard-1-small.json", small())
    for name, (doc, stated) in invalid_cases().items():
        dump(FIXTURES / "invalid" / name / "input.json", doc)
        dump(FIXTURES / "invalid" / name / "expected.json", expected_result(name, doc, stated))
    for name, data in replies().items():
        dump(FIXTURES / "valid" / name, data)


def replies() -> dict[str, dict]:
    base = {
        "contract": "publish-reply/1",
        "publish_id": "019a2a6e-5c3b-7d41-9f0e-2b6c8d4a1e70",
        "received_at": "2026-10-27T09:30:01.250Z",
        "kind": "dashboard",
        "counts": {"features": 18, "items": 148, "client_contacts": 3},
        "dry_run": False,
    }
    dry = {**base, "publish_id": None, "dry_run": True, "client_view": {
        "areas": ["Onboarding", "Loans"],
        "release_rows": [{"name": "1.5", "released": False}],
        "features": [{
            "id": "sign-up-with-phone-number", "title": "Sign-up with phone number", "short": "Sign-up",
            "summary": "<p class=\"lead\">Sign-up with phone number.</p>", "open": ["Which employers first?"],
            "stage": "spec", "map_area": "Onboarding", "releases": ["1.5"],
            "hiddenByDoneFilter": False, "page": None,
        }],
        "items": [{
            "key": "3f2a9c0d1e4b", "feature": "sign-up-with-phone-number",
            "title": "Confirm the wording for sign-up", "text": "<p>Short answer is fine.</p>",
            "how_to_send": "Reply in Slack.", "waitingOnYou": True, "onAgenda": False,
        }],
    }, "client_contact_names": ["Maria Lopez", "Tom Baker", "Priya Shah"]}
    status = {
        "contract": "status/1", "project_name": "Sample Project", "archived": False,
        "waiting": 0, "last_fetched_at": None, "accepted_contracts": ["dashboard/1"],
    }
    return {
        "publish-reply-1-sent.json": base,
        "publish-reply-1-dry-run.json": dry,
        "status-1.json": status,
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
