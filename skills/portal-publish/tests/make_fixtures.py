"""Writes contract/fixtures/ — run with `uv run python tests/make_fixtures.py` after changing it.

The Dashboard data is synthetic (no client data), sized like Acme Lending: 18 Features, 148 Items.
Each invalid case is the small base file with one thing broken, plus expected.json.

dashboard/2 (contract 1.2.0): a small file, and a real-size one that is the upper bound of Acme Lending in one
send — 48 areas (5 open tickets each), 18 Features, 10 topics, 70 Items, 60 releases, 436 cards (29 Feature,
290 epic, 117 other) holding 2,042 tickets, a 4,598-character summary and a 130-character release name. All text
is made up: no client text and no email address. Its invalid cases (named `v2-…`) break the small file.
Contract 1.3.0 adds a small file with the optional `clarification_pages` list, three `v2-…` cases that break
it, and Dashboard replies that carry `pages_removed`.
Contract 1.4.0 adds a small file with the optional 1.4.0 fields (Item `hot`, Feature `stage_why` and `area_how`,
open ticket `updated`) and `v2-…` cases that break them; `answers/2` batches (Answers plus the Client's updates on
Items) and the `reserve-request/1` body, with broken cases of both.
Contract 1.5.0 adds the `connect-request/1` body (a one-time connect code and a repo name) and its `connect/1`
reply (a new key for the code's project), with broken cases of both. The key is made up.
Contract 1.6.0 adds `timeline/1` (the BA's Timeline data, sent to the Dashboard endpoint): a small file holding
every field the real builds use, a real-size one shaped like Acme Lending's real build (made-up text), `tl1-…` cases
that break the small one, the replies to a Timeline send, and an `answers/2` batch with an update on a `todo`.
Contract 1.7.0 adds a screen's optional `figma` link (the Open in Figma button) to both pages, to the page replies'
Client view, and `figma-…` cases that break it (check figma_link).
Contract 1.8.0 adds Client suggestions: `answers/3` batches (`answers/2` plus the suggestions sent on the Portal
Timeline) with `answers3-…` cases that break them, and the optional `suggestion_status` of `timeline/1` (the BA's
Accepted or Declined, in the small file) with `tl1-suggestion-…` cases.

Pages: the clarification-page skill's example-probate-decisions.yaml converted to clarification/1, and a
synthetic page of Merchants V7 size (6 Questions, 18 options, 4 screens). A page's invalid case is the
Merchants-size page with one thing broken; its expected.json says "kind": "clarification", and its folder may
hold parts.json (the screenshot part names sent with it; without it, the page's own file names are the parts).
Broken replies and requests are invalid cases too; their expected.json names the contract they are checked
against and has no code.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote as url_quote

FIXTURES = Path(__file__).resolve().parent.parent / "contract" / "fixtures"
PROBATE = (Path(__file__).resolve().parents[2] / "clarification-page" / "assets"
           / "example-probate-decisions.yaml")

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


def item_key2(kind: str, parent: str, title: str) -> str:
    """dashboard/2's Item key: the parent is part of it, so same-title Items under two parents differ."""
    return hashlib.sha1(f"{kind}|{parent}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


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
    d = small(); d["contract"] = "dashboard/3"  # dashboard/2 is accepted since contract 1.2.0
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


# ---- dashboard/2 ---------------------------------------------------------------------------------------

JIRA_BASE = "https://example.atlassian.net"
WORDS = ["account", "batch", "billing", "calendar", "consent", "export", "import", "invoice", "ledger", "limit",
         "login", "message", "payout", "profile", "report", "reminder", "review", "schedule", "search", "status",
         "summary", "template", "transfer", "upload", "wallet", "widget"]
STATUSES = [("To Do", "ready"), ("In Progress", "dev"), ("In Review", "qa"), ("Done", "done")]
ASSIGNEES = ["Sample Developer", "Sample Tester", "Sample Designer"]


def words(n: int, count: int) -> str:
    return " ".join(WORDS[(n * 7 + i * 3) % len(WORDS)] for i in range(count))


def jira_key(n: int) -> str:
    return f"ABC-{1000 + n}"


def ticket(n: int, done: bool = False) -> dict:
    status, stage = STATUSES[3] if done else STATUSES[n % 3]
    t = {"key": jira_key(n), "summary": f"{words(n, 4).capitalize()} ({n})", "status": status, "stage": stage}
    if n % 3 != 2:
        t["assignee"] = ASSIGNEES[n % len(ASSIGNEES)]
    return t


def area2(n: int, special: str | None = None) -> dict:
    if special:
        a = {"id": special.replace("_", ""), "name": "No area" if special == "no_area" else "Not linked",
             "quiet": False, "special": special}
    else:
        a = {"id": f"ABC:Area {n + 1}", "name": f"{words(n, 2).title()} {n + 1}", "quiet": n % 3 == 2}
    base = 5000 + n * 40
    a["jira"] = {
        "done": 10 + n, "in_progress": n % 4, "open": 5 + n % 3,
        "shipped": [{"key": jira_key(base + j), "summary": f"Shipped {words(n + j, 3)}",
                     "date": f"2026-{1 + (n + j) % 9:02d}-{1 + j:02d}"} for j in range(n % 4)],
        "open_tickets": [{"key": jira_key(base + 10 + j), "summary": f"Open {words(n + j, 3)}",
                          "status": "In Progress" if j < 2 else "To Do", "stage": "dev" if j < 2 else "ready"}
                         for j in range(5)],
    }
    if n % 2 == 0:
        a["jira"]["description"] = f"The {words(n, 2)} part of the product."
    if n % 4 != 3:
        a["jira"]["last_done"] = f"2026-10-{1 + n % 27:02d}"
    return a


def dashboard2(n_areas: int, n_features: int, n_topics: int, n_items: int, n_releases: int,
               card_tickets: list[int], kinds: tuple[int, int, int]) -> dict:
    """A synthetic dashboard/2. card_tickets gives each card's ticket count; kinds = (feature, epic, other) cards."""
    areas = [area2(i) for i in range(n_areas - 2)] + [area2(0, "no_area"), area2(0, "not_linked")]
    ids = [a["id"] for a in areas]
    releases = []
    for i in range(n_releases):
        r = {"name": f"Release {i // 10 + 1}.{i % 10} - {words(i, 3)}", "released": i < n_releases * 2 // 3,
             "overdue": i == n_releases * 2 // 3}
        if i % 5 != 4:
            r["date"] = f"2026-{1 + i % 12:02d}-{1 + i % 28:02d}"
        releases.append(r)
    names = [r["name"] for r in releases]
    tick = iter(range(100000))

    feats = []
    for i in range(n_features):
        title, short, _ = FEATURES[i % len(FEATURES)]
        stage = STAGES[i % len(STAGES)]
        f = {"id": slug(title) if i < len(FEATURES) else f"{slug(title)[:30]}-{i}", "area": ids[i % len(ids)],
             "title": title,
             "summary": f"<p class=\"lead\">{title} — what it does for the employee.</p>"
                        f"<p>Status: <strong>{stage}</strong>. Next step agreed on the last call.</p>",
             "stage": stage, "tickets": [ticket(next(tick), stage == "done") for _ in range(i % 3)]}
        if short:
            f["short"] = short
        if i % 3 == 0:
            f["open"] = [f"Which employers get {title.lower()} first?", "Is the copy final in every language?"]
        if i % 2 == 0:
            f["answered"] = {"done": i % 5, "total": 5}
        if stage == "done":
            f["done_date"] = f"2026-10-{(i % 20) + 1:02d}"
        if i % 4 == 1:
            f["clar_url"] = f"https://pages.example.com/clarifications/{slug(title)}/"
        feats.append(f)
    topics = [{"id": f"topic-{i + 1}", "area": ids[(i * 5) % len(ids)], "title": f"{words(i, 2).capitalize()} work",
               "stage": STAGES[(i + 2) % len(STAGES)], "tickets": [ticket(next(tick)) for _ in range(i % 2 + 1)]}
              for i in range(n_topics)]
    parents = [f["id"] for f in feats] + [t["id"] for t in topics]
    items = []
    for i in range(n_items):
        kind = "waiting" if i % 3 else "agenda"
        title = f"{ASKS[i % len(ASKS)]} {words(i, 2)} (#{i + 1})"
        parent = parents[i % len(parents)]
        it = {"key": item_key2(kind, parent, title), "kind": kind, "parent": parent,
              "who": PEOPLE[i % len(PEOPLE)] + (" then Dev team" if i % 7 == 0 else ""),
              "since": f"2026-{9 + i % 2:02d}-{(i % 28) + 1:02d}", "title": title}
        if i % 2 == 0:
            it["text"] = "<p>We need this before the next build. <em>A short answer is fine.</em></p>"
        if kind == "waiting" and i % 4 == 1:
            it["how_to_send"] = "Reply in the project Slack channel."
        items.append(it)

    n_feature, n_epic, _ = kinds
    cards = []
    for i, count in enumerate(card_tickets):
        kind = "feature" if i < n_feature else "epic" if i < n_feature + n_epic else "other"
        release = None if i % 6 == 5 or not names else names[i % len(names)]
        stage = "done" if release is not None and i % 4 == 0 else STAGES[i % 5]
        card = {"id": f"c{i:05d}", "kind": kind, "area": ids[i % len(ids)], "release": release}
        if kind == "feature":
            feat = feats[i % len(feats)]
            card.update(title=feat["title"], feature=feat["id"], area=feat["area"])
        elif kind == "epic":
            card.update(title=f"Epic: {words(i, 3)} ({i})", epic=jira_key(90000 + i))
        else:
            card.update(title="Other tickets")
        card.update(stage=stage, blocked=i % 17 == 3)
        if stage == "done":
            card["done_date"] = f"2026-{1 + i % 10:02d}-{1 + i % 28:02d}"
        card["tickets"] = [ticket(next(tick), stage == "done") for _ in range(count)]
        cards.append(card)
    return {
        "contract": "dashboard/2",
        "sent_at": "2026-10-28T09:30:00.000Z",
        "sent_by": "Sample BA",
        "ba_tools_version": "0.9.0",
        "source_commit": "4be1f0c9a2d7e3b5f6a8c1d0e9f7a6b5c4d3e2f1",
        "jira_base": JIRA_BASE,
        "areas": areas,
        "features": feats,
        "topics": topics,
        "items": items,
        "releases": releases,
        "cards": cards,
        "client_contacts": [{"name": "Maria Lopez", "slack": "maria.lopez"}, {"name": "Tom Baker"},
                            {"name": "Priya Shah", "slack": "U02ABCD1234"}],
    }


# The real-size file: Acme Lending's upper bound in one send (Story 3.7).
REAL_CARDS = (29, 290, 117)
REAL_TICKETS = 2042
LONG_SUMMARY = 4598
LONG_RELEASE = 130


def real_card_tickets() -> list[int]:
    """436 ticket counts that add up to 2,042, the first card holding 176 (the largest real card)."""
    counts = [176] + [1 + (i % 8) for i in range(sum(REAL_CARDS) - 1)]
    i = 1
    while sum(counts) != REAL_TICKETS:
        step = 1 if sum(counts) < REAL_TICKETS else -1
        if counts[i] + step >= 1:
            counts[i] += step
        i = i % (len(counts) - 1) + 1
    return counts


def real_size2() -> dict:
    d = dashboard2(48, 18, 10, 70, 60, real_card_tickets(), REAL_CARDS)
    lead = "<p class=\"lead\">A long summary, as long as the longest real one.</p>"
    para = "<p>" + " ".join(WORDS) + ".</p>"
    body = lead
    while len(body) + len(para) <= LONG_SUMMARY - 7:
        body += para
    body += "<p>" + "x" * (LONG_SUMMARY - len(body) - 7) + "</p>"
    d["features"][0]["summary"] = body
    old = d["releases"][1]["name"]
    new = (old + " - " + " ".join(WORDS))[:LONG_RELEASE]
    d["releases"][1]["name"] = new
    for card in d["cards"]:
        if card["release"] == old:
            card["release"] = new
    return d


def small2() -> dict:
    return dashboard2(4, 4, 2, 8, 3, [2, 1, 3, 1, 2, 0], (2, 2, 2))


PAGE_SLUGS = ["probate-decisions", "payouts", "sign-up-with-phone-number"]


def with_pages() -> dict:
    """The small dashboard/2 with the 1.3.0 page list: the slugs of the project's Clarification pages."""
    d = small2()
    d["clarification_pages"] = list(PAGE_SLUGS)
    return d


WHY = ["Concept: concept or idea, no spec yet, 40% of questions answered", "Spec & design: spec is draft",
       "Ready for dev, its slowest open ticket. Tickets: 1 Ready for dev", "In dev, no tickets linked yet"]
HOW = ["from its tickets", "set on the dashboard", "no tickets and no area set"]


def with_1_4_fields() -> dict:
    """The small dashboard/2 with the optional 1.4.0 fields: Item hot, Feature stage_why and area_how, open ticket
    updated (a date, or a UTC time), area Jira search link."""
    d = small2()
    for i, it in enumerate(d["items"]):
        if i % 3 != 2:
            it["hot"] = i % 3 == 0
    for i, f in enumerate(d["features"]):
        f["stage_why"] = WHY[i % len(WHY)]
        if i % 4 != 3:
            f["area_how"] = HOW[i % len(HOW)]
    for a in d["areas"]:
        if "jira" in a:
            a["jira"]["search"] = "https://example.atlassian.net/issues/?jql=" + url_quote(f'component = "{a["id"]}"', safe="")
        for j, t in enumerate(a.get("jira", {}).get("open_tickets", [])):
            if j % 3 == 0:
                t["updated"] = f"2026-10-{20 - j:02d}"
            elif j % 3 == 1:
                t["updated"] = f"2026-10-{20 - j:02d}T08:15:00.000Z"
    return d


def v2_invalid_cases() -> dict[str, tuple[dict, dict]]:
    cases: dict[str, tuple[dict, dict]] = {}

    def case(name, doc, code, check, path):
        cases[name] = (doc, {"code": code, "check": check, "path": path})

    d = small2(); d["areas"][1]["id"] = d["areas"][0]["id"]
    for f in d["features"] + d["topics"] + d["cards"]:  # nothing names the lost id
        if f["area"] == small2()["areas"][1]["id"]:
            f["area"] = d["areas"][0]["id"]
    case("v2-duplicate-area-id", d, "contract_invalid", "unique_area_id", "/areas/1/id")
    def rename(doc, old, new):
        """Point every Item parent and card Feature that named `old` at `new`, so only one check fails."""
        for it in doc["items"]:
            if it["parent"] == old:
                it["parent"] = new
        for card in doc["cards"]:
            if card.get("feature") == old:
                card["feature"] = new

    d = small2(); rename(d, d["features"][2]["id"], d["features"][1]["id"])
    d["features"][2]["id"] = d["features"][1]["id"]
    case("v2-duplicate-feature-id", d, "contract_invalid", "unique_feature_id", "/features/2/id")
    d = small2(); rename(d, d["topics"][1]["id"], d["topics"][0]["id"])
    d["topics"][1]["id"] = d["topics"][0]["id"]
    case("v2-duplicate-topic-id", d, "contract_invalid", "unique_topic_id", "/topics/1/id")
    d = small2(); rename(d, d["topics"][0]["id"], d["features"][0]["id"])
    d["topics"][0]["id"] = d["features"][0]["id"]
    case("v2-topic-id-is-a-feature-id", d, "contract_invalid", "unique_topic_id", "/topics/0/id")
    d = small2(); d["items"][3]["key"] = d["items"][1]["key"]
    case("v2-duplicate-item-key", d, "contract_invalid", "unique_item_key", "/items/3/key")
    d = small2(); d["cards"][4]["id"] = d["cards"][2]["id"]
    case("v2-duplicate-card-id", d, "contract_invalid", "unique_card_id", "/cards/4/id")
    d = small2(); d["cards"][2]["tickets"][2]["key"] = d["cards"][2]["tickets"][0]["key"]
    case("v2-duplicate-ticket-in-card", d, "contract_invalid", "unique_ticket_in_list", "/cards/2/tickets/2/key")
    d = small2(); d["cards"][3]["area"] = "ABC:No such area"
    case("v2-unknown-card-area", d, "contract_invalid", "known_area", "/cards/3/area")
    d = small2(); d["features"][1]["area"] = "ABC:No such area"
    case("v2-unknown-feature-area", d, "contract_invalid", "known_area", "/features/1/area")
    d = small2(); d["items"][2]["parent"] = "no-such-feature"
    case("v2-unknown-parent", d, "contract_invalid", "known_parent", "/items/2/parent")
    d = small2(); d["cards"][0]["feature"] = "no-such-feature"
    case("v2-unknown-card-feature", d, "contract_invalid", "known_card_feature", "/cards/0/feature")
    d = small2(); d["cards"][1]["release"] = "Release 9.9 - not sent"
    case("v2-unknown-release", d, "contract_invalid", "known_release", "/cards/1/release")
    d = small2(); d["features"][1]["title"] = "Sign-up &mdash; phone number"
    case("v2-html-entity", d, "contract_invalid", "no_html_entities", "/features/1/title")
    d = small2(); d["topics"][1]["area"] = "ABC:No such area"
    case("v2-unknown-topic-area", d, "contract_invalid", "known_area", "/topics/1/area")
    d = small2(); d["releases"][2]["name"] = d["releases"][0]["name"]
    for card in d["cards"]:  # nothing names the lost release
        if card["release"] == small2()["releases"][2]["name"]:
            card["release"] = d["releases"][0]["name"]
    case("v2-duplicate-release-name", d, "contract_invalid", "unique_release_name", "/releases/2/name")
    d = small2(); d["areas"][1]["special"] = "no_area"
    case("v2-duplicate-special", d, "contract_invalid", "unique_special", "/areas/2/special")
    d = small2(); d["features"][2]["tickets"][1]["key"] = d["features"][2]["tickets"][0]["key"]
    case("v2-duplicate-ticket-in-feature", d, "contract_invalid", "unique_ticket_in_list",
         "/features/2/tickets/1/key")
    d = small2(); d["areas"][0]["jira"]["open_tickets"][3]["key"] = d["areas"][0]["jira"]["open_tickets"][1]["key"]
    case("v2-duplicate-open-ticket", d, "contract_invalid", "unique_ticket_in_list",
         "/areas/0/jira/open_tickets/3/key")
    d = small2(); del d["cards"][0]["feature"]
    case("v2-feature-card-without-feature", d, "contract_invalid", "card_kind_fields", "/cards/0/feature")
    d = small2(); d["cards"][2]["feature"] = d["features"][0]["id"]
    case("v2-epic-card-with-feature", d, "contract_invalid", "card_kind_fields", "/cards/2/feature")
    d = small2(); d["cards"][4]["epic"] = "ABC-77"
    case("v2-other-card-with-epic", d, "contract_invalid", "card_kind_fields", "/cards/4/epic")
    d = small2(); d["features"][0]["answered"] = {"done": 6, "total": 5}
    case("v2-answered-over-total", d, "contract_invalid", "answered_in_range", "/features/0/answered/done")
    d = small2(); d["jira_base"] = "javascript:alert(1)"
    case("v2-jira-base-javascript", d, "contract_invalid", "schema", "/jira_base")
    d = small2(); d["jira_base"] = "http://example.atlassian.net"
    case("v2-jira-base-http", d, "contract_invalid", "schema", "/jira_base")
    d = small2(); d["products"] = ["AcmeLending", "Bond Portal"]
    case("v2-products-field", d, "contract_invalid", "schema", "/products")
    d = small2(); d["cards"][0]["prod"] = "AcmeLending"
    case("v2-prod-field", d, "contract_invalid", "schema", "/cards/0/prod")
    d = small2(); del d["jira_base"]
    case("v2-missing-jira-base", d, "contract_invalid", "schema", "/jira_base")
    d = small2(); d["releases"][0]["name"] = "R" * 256  # the schema fails first, so known_release does not run
    case("v2-release-name-too-long", d, "contract_invalid", "schema", "/releases/0/name")
    d = small2(); d["cards"][0]["tickets"][0]["summary"] = "S" * 256
    case("v2-ticket-summary-too-long", d, "contract_invalid", "schema", "/cards/0/tickets/0/summary")
    d = small2(); d["features"][0]["summary"] = "<p>" + "s" * 20000 + "</p>"
    case("v2-feature-summary-too-long", d, "contract_invalid", "schema", "/features/0/summary")
    d = small2(); d["areas"][0]["jira"]["open_tickets"] *= 5
    case("v2-too-many-open-tickets", d, "contract_invalid", "schema", "/areas/0/jira/open_tickets")
    d = small2(); d["cards"][1]["tickets"][0]["key"] = "abc-12"
    case("v2-bad-ticket-key", d, "contract_invalid", "schema", "/cards/1/tickets/0/key")
    d = small2(); d["cards"][0]["kind"] = "story"
    case("v2-bad-card-kind", d, "contract_invalid", "schema", "/cards/0/kind")
    d = small2(); d["contract"] = "dashboard/3"
    case("v2-version-not-accepted", d, "contract_version_not_accepted", "contract_version", "/contract")
    d = with_pages(); d["clarification_pages"].append(PAGE_SLUGS[0])
    case("v2-duplicate-page-slug", d, "contract_invalid", "unique_page_slug", "/clarification_pages/3")
    d = with_pages(); d["clarification_pages"][1] = "Payouts"
    case("v2-bad-page-slug", d, "contract_invalid", "schema", "/clarification_pages/1")
    d = with_pages(); d["clarification_pages"] = [f"page-{i}" for i in range(1001)]
    case("v2-too-many-pages", d, "contract_invalid", "schema", "/clarification_pages")
    # the optional 1.4.0 fields
    d = with_1_4_fields(); d["items"][0]["hot"] = "yes"
    case("v2-hot-not-yes-no", d, "contract_invalid", "schema", "/items/0/hot")
    d = with_1_4_fields(); d["features"][0]["stage_why"] = "W" * 401
    case("v2-stage-why-too-long", d, "contract_invalid", "schema", "/features/0/stage_why")
    d = with_1_4_fields(); d["features"][1]["area_how"] = ""
    case("v2-area-how-empty", d, "contract_invalid", "schema", "/features/1/area_how")
    d = with_1_4_fields(); d["areas"][0]["jira"]["open_tickets"][0]["updated"] = "2026-10-20T08:15:00+0000"
    case("v2-ticket-updated-not-utc", d, "contract_invalid", "schema", "/areas/0/jira/open_tickets/0/updated")
    return cases


def client_view2(doc: dict) -> dict:
    """The Portal's ClientDashboard2 of a dashboard/2 send, for the reply fixture: everything but the envelope,
    the contacts and clar_url, plus the derived flags. (The Portal builds the real one; this is an example.)"""
    contacts = {c["name"].lower() for c in doc["client_contacts"]}
    features = []
    for f in doc["features"]:
        out = {k: v for k, v in f.items() if k != "clar_url"}
        out.update(hiddenByDoneFilter=False, page=None)
        features.append(out)
    items = [{**it, "waitingOnYou": it["kind"] == "waiting" and it["who"].split(" then ")[0].lower() in contacts,
              "onAgenda": it["kind"] == "agenda"} for it in doc["items"]]
    cards = [{**c, "hiddenByDoneFilter": False} for c in doc["cards"]]
    return {"jira_base": doc["jira_base"], "areas": doc["areas"], "features": features, "topics": doc["topics"],
            "items": items, "releases": doc["releases"], "cards": cards}


# ---- timeline/1 (contract 1.6.0) ---------------------------------------------------------------------

TL_STAGES = ["concept", "spec", "ready", "dev", "qa", "done"]
TL_PIN_KINDS = ["call", "email", "comments", "doc", "page", "idea"]
TL_REQUEST_KINDS = ["sub-feature", "change", "improvement", "bug"]
TL_PAGES = ["sign-up-questions", "advance-limits", "payday-repayment"]
# The shape of Acme Lending's real Timeline build (6 Nov 2026): 7 groups holding 28 areas, 336 rows (features and
# older Jira stories) with 13 changes and bugs, 98 to-dos, 333 work items, 58 pins, 26 releases, 16 pages of which
# 14 are linked from a feature; the longest desc is 1,076 characters and the longest to-do text 1,994. All text
# here is made up.
EPD_AREAS = [[21, 13], [91, 2, 35, 18, 13], [24, 14, 9], [7, 5], [1, 3, 5], [2, 8, 0, 13, 3, 9, 14, 2], [4, 1, 13, 5, 1]]
EPD_REQUESTS, EPD_TODOS, EPD_WORK, EPD_PINS, EPD_RELEASES, EPD_PAGES, EPD_LINKED = 13, 98, 333, 58, 26, 16, 14
EPD_LONG_DESC, EPD_LONG_TODO = 1076, 1994


def day(n: int) -> str:
    """A date between 1 May and 6 Nov 2026."""
    d = 1 + n % 189
    months = [(5, 31), (6, 30), (7, 31), (8, 31), (9, 30), (10, 31), (11, 6)]
    for m, length in months:
        if d <= length:
            return f"2026-{m:02d}-{d:02d}"
        d -= length
    return "2026-11-06"


def tl_stages(n: int, upto: int) -> list[dict]:
    return [{"stage": TL_STAGES[j], "from": day(n + j * 9)} for j in range(upto + 1)]


def tl_work(n: int, done: bool) -> dict:
    w = {"id": jira_key(n), "title": f"{words(n, 4).capitalize()} ({n})", "status": "Done" if done else "To Do"}
    if done:
        w["done"] = day(n + 40)
    return w


def tl_todo(n: int, kind: str, feature: str) -> dict:
    title = f"{ASKS[n % len(ASKS)]} {feature.lower()} ({n})"
    return {"key": item_key(kind, title), "id": f"{kind[0].upper()}{n}", "kind": kind, "title": title,
            "who": PEOPLE[n % len(PEOPLE)] if kind != "todo" else "Sample BA", "since": day(n * 5),
            "age": n % 30, "status": ["open", "hot", "old"][n % 3], "prod": "Sample",
            "s": f"{words(n, 6).capitalize()}.", "l": f"{words(n + 1, 8).capitalize()}.\n- {words(n + 2, 4)}."}


def tl_feature(n: int, pins: list[str], page: str | None = None) -> dict:
    stage = n % 6
    f = {"id": f"row-{n}", "label": f"{words(n, 3).capitalize()} {n}", "stage": TL_STAGES[stage],
         "stages": tl_stages(n, stage), "since": day(n), "origin": ["dashboard", "spec", "old-work"][n % 3],
         "basis": ["tracker", "recorded", "code", "none"][n % 4], "desc": f"{words(n, 12).capitalize()}." if n % 2 else "",
         "work": [tl_work(n * 10 + j, j == 0) for j in range(n % 3)], "guess": n % 5 == 4,
         "who": [PEOPLE[n % len(PEOPLE)].split(" ")[0]], "tags": [f"6.{n % 5}"]}
    if n % 7 == 1 and f["work"]:
        f["work"][0]["url"] = f"https://github.com/example/docs/blob/main/stories/story-{n}.md"
    if TL_STAGES[stage] == "done":
        f["doneDate"] = f["stages"][-1]["from"]
    if not f["desc"]:
        f["about"] = [f"{words(n + j, 7).capitalize()}." for j in range(2)]
    if f["origin"] == "old-work":
        f["originNote"] = "A Jira story from before 1 May 2026."
    if f["basis"] == "tracker":
        f["basisNote"] = "From the Jira history of its tickets."
    if page:
        f["page"] = page
        f["clarLabel"] = "Clarification page — V2, 3 questions"
    if n % 4 == 0 and pins:
        f["askedIn"], f["askedBy"] = pins[n % len(pins)], "Maria"
    return f


def tl_pin(n: int) -> dict:
    kind = TL_PIN_KINDS[n % len(TL_PIN_KINDS)]
    date = day(n * 3)
    p = {"id": f"{date}-{kind}", "date": date, "kind": kind,
         "title": {"call": "Client call", "email": "Email · " + words(n, 2), "comments": "Slack · 2 messages",
                   "doc": "Document · " + words(n, 2), "page": "Answers on 1 clarification page",
                   "idea": "Suggestion · " + words(n, 2)}[kind]}
    if kind == "call":
        p.update(people=["Maria", "Tom"], staff=2, minutes=45 + n % 30,
                 summary=[f"{words(n + j, 9).capitalize()}." for j in range(3)],
                 owes=[{"who": "Maria → Sample BA", "text": f"{words(n, 5).capitalize()}."}])
    if kind == "email":
        p.update(people=["Priya"], subject=f"Re: {words(n, 3)}")
    if kind == "page":
        p["decided"] = [{"title": f"{words(n, 6).capitalize()}.", "page": "Sign-up questions",
                         "how": "on the client Portal"}]
    if kind == "doc":
        p["ref"] = f"doc-{n}"
    return p


def timeline(features_by_area: list[list[int]], n_requests: int, n_todos: int, n_work: int, n_pins: int,
             n_releases: int, pages: list[str], linked: int) -> dict:
    pins = [tl_pin(n) for n in range(n_pins)]
    pin_ids = [p["id"] for p in pins]
    groups, n, linked_left, work_left = [], 0, linked, n_work
    for g, areas in enumerate(features_by_area):
        group = {"name": f"{words(g, 2).capitalize()} group", "areas": []}
        for a, size in enumerate(areas):
            area = {"name": f"{words(g * 10 + a, 2).title()} {g}.{a}", "features": []}
            if (g + a) % 2 == 0:
                area["link"] = {"label": "See all in Jira", "url": "https://example.atlassian.net/issues/?jql="
                                + url_quote(f'component = "{area["name"]}"', safe="")}
            for _ in range(size):
                page = pages[(n // 3) % len(pages)] if linked_left > 0 and n % 3 == 0 else None
                if page:
                    linked_left -= 1
                f = tl_feature(n, pin_ids, page)
                work_left -= len(f["work"])
                area["features"].append(f)
                n += 1
            group["areas"].append(area)
        groups.append(group)
    rows = [f for g in groups for a in g["areas"] for f in a["features"]]
    i = 0
    while work_left < 0:                               # trim, then top up, to the work-item count
        f = next(f for f in reversed(rows) if f["work"])
        f["work"].pop()
        work_left += 1
    while work_left > 0:
        rows[i % len(rows)]["work"].append(tl_work(9000 + i, False))
        work_left -= 1
        i += 1
    for j in range(n_requests):
        f = rows[(j * 7) % len(rows)]
        q = {"id": f"req-{j}", "kind": TL_REQUEST_KINDS[j % 4], "title": f"{words(j, 5).capitalize()} ({j})",
             "stages": tl_stages(j, j % 6), "work": [tl_work(7000 + j, j % 6 == 5)] if j % 2 else []}
        if j % 3 == 0:
            q.update(askedIn=pin_ids[j % len(pin_ids)], askedBy="Tom", asked=f"{words(j, 6).capitalize()}?")
        if j % 4 == 3:
            q.update(note=f"QA bug BUG-{j:03d} · High · found {day(j)}", guess=True)
        if j % 5 == 1:
            q.update(about=[f"{words(j, 6).capitalize()}."], tags=["7.0"], self=rows[0]["id"])
        if j % 7 == 5 and q["work"]:
            q["work"][0]["url"] = f"https://github.com/example/docs/blob/main/stories/request-{j}.md"
        if j % 6 == 2:
            q["merged"] = day(j + 60)
        if j % 6 == 4:
            q["splitOff"] = f"later-{j}"
        f.setdefault("requests", []).append(q)
    for j in range(n_todos):
        f = rows[(j * 5) % len(rows)]
        f.setdefault("todos", []).append(tl_todo(j, ["waiting", "agenda", "todo"][j % 3], f["label"]))
    for f in rows[:3]:
        f["openQ"] = [f"{words(len(f['label']), 7).capitalize()}?"]
    rows[1]["changes"] = rows[0]["id"]
    rows[2]["startedBefore"] = "2026-03-02"
    return {
        "contract": "timeline/1", "sent_at": "2026-11-06T10:00:00.000Z", "sent_by": "Sample BA",
        "ba_tools_version": "0.9.0", "source_commit": "0123456789abcdef0123456789abcdef01234567",
        "product": {"name": "Sample", "tagWord": "Release", "tracker": "jira",
                    "workLink": "https://example.atlassian.net/browse/", "ba": "Sample",
                    "footer": "the BA dashboard, the timeline data file, Jira and the intake files."},
        "today": "2026-11-06", "start": "2026-05-01", "from": "2026-03-02", "built": "06 Nov 2026, 10:00",
        "groups": groups, "pins": pins,
        "releases": [{"name": f"6.{j}", "date": day(j * 7)} for j in range(n_releases)],
        "client_contacts": [{"name": "Maria Lopez", "email": "maria@example.com"},
                            {"name": "Tom Baker", "slack": "tom.baker"}],
        "clarification_pages": list(pages),
    }


# The suggestions of the answers/3 fixtures; the small timeline/1 decides two of them (contract 1.8.0).
SUGGESTION_IDS = ["019a5a10-0b00-7c00-8a00-000000000001", "019a5a10-0b00-7c00-8a00-000000000002",
                  "019a5a10-0b00-7c00-8a00-000000000003"]


def timeline_small() -> dict:
    """The small timeline/1: every field the real builds use, at least once, and every stage (design on a row,
    live on a request). Since 1.8.0 it decides two suggestions (suggestion_status)."""
    d = timeline([[3, 2], [4]], 7, 9, 6, 7, 3, TL_PAGES, 2)
    d["suggestion_status"] = [
        {"id": SUGGESTION_IDS[0], "status": "accepted", "reason": "Planned for the next release."},
        {"id": SUGGESTION_IDS[1], "status": "declined", "reason": "Out of scope for the pilot."},
    ]
    rows = tl_rows(d)
    rows[1]["stages"] = [{"stage": "concept", "from": day(1)}, {"stage": "design", "from": day(10)}]
    rows[1]["stage"] = "design"
    q = next(q for f in rows for q in f.get("requests", []) if q["stages"][-1]["stage"] == "done")
    q["stages"].append({"stage": "live", "from": day(150)})
    return d


def timeline_real_size() -> dict:
    """Acme Lending's real Timeline build, in shape and size, with made-up text."""
    d = timeline(EPD_AREAS, EPD_REQUESTS, EPD_TODOS, EPD_WORK, EPD_PINS, EPD_RELEASES,
                 [f"page-{j + 1}" for j in range(EPD_PAGES)], EPD_LINKED)
    rows = [f for g in d["groups"] for a in g["areas"] for f in a["features"]]
    long_desc = (" ".join(WORDS) + ". ") * 20
    rows[1]["desc"] = long_desc[:EPD_LONG_DESC]
    rows[1].pop("about", None)
    todo = next(t for f in rows for t in f.get("todos", []))
    todo["s"] = (" ".join(WORDS) + ".\n") * 30
    todo["s"] = todo["s"][:EPD_LONG_TODO]
    return d


def tl_rows(doc: dict) -> list[dict]:
    return [f for g in doc["groups"] for a in g["areas"] for f in a["features"]]


def tl_invalid_cases() -> dict[str, tuple[dict, dict]]:
    """Each breaks the small timeline/1 in one place."""
    cases: dict[str, tuple[dict, dict]] = {}

    def case(name, doc, code, check, path):
        cases[name] = (doc, {"code": code, "check": check, "path": path})

    f0 = "/groups/0/areas/0/features/0"
    d = timeline_small(); d["contract"] = "timeline/2"
    case("tl1-version-not-accepted", d, "contract_version_not_accepted", "contract_version", "/contract")
    d = timeline_small(); tl_rows(d)[0]["clar"] = "https://claude.ai/artifact/AbCdEf0123456789"
    case("tl1-artifact-link-left-in", d, "contract_invalid", "schema", f0 + "/clar")
    d = timeline_small(); d["pages"] = []
    case("tl1-pages-left-in", d, "contract_invalid", "schema", "/pages")
    d = timeline_small(); d["dashboardUrl"] = "https://claude.ai/artifact/AbCdEf0123456789"
    case("tl1-dashboard-url-left-in", d, "contract_invalid", "schema", "/dashboardUrl")
    d = timeline_small(); i = next(i for i, p in enumerate(d["pins"]) if p.get("decided"))
    d["pins"][i]["decided"][0]["url"] = "https://claude.ai/artifact/AbCdEf0123456789"
    case("tl1-decided-url-left-in", d, "contract_invalid", "schema", f"/pins/{i}/decided/0/url")
    d = timeline_small(); tl_rows(d)[1]["work"][0]["url"] = "http://example.com/story.md"
    case("tl1-work-url-http", d, "contract_invalid", "schema", "/groups/0/areas/0/features/1/work/0/url")
    d = timeline_small(); d["groups"][0]["areas"][0]["link"]["url"] = "javascript:alert(1)"
    case("tl1-area-link-javascript", d, "contract_invalid", "schema", "/groups/0/areas/0/link/url")
    d = timeline_small(); d["product"]["workLink"] = "http://example.atlassian.net/browse/"
    case("tl1-work-link-http", d, "contract_invalid", "schema", "/product/workLink")
    d = timeline_small(); del d["product"]
    case("tl1-missing-product", d, "contract_invalid", "schema", "/product")
    d = timeline_small(); tl_rows(d)[0]["doneDate"] = None
    case("tl1-null-field", d, "contract_invalid", "schema", f0 + "/doneDate")
    d = timeline_small(); tl_rows(d)[0]["stage"] = "shipped"
    case("tl1-bad-stage", d, "contract_invalid", "schema", f0 + "/stage")
    d = timeline_small(); tl_rows(d)[0]["since"] = "2026-13-01"
    case("tl1-bad-date", d, "contract_invalid", "schema", f0 + "/since")
    d = timeline_small(); tl_rows(d)[0]["todos"][0]["key"] = "ABCDEF012345"
    case("tl1-bad-todo-key", d, "contract_invalid", "schema", f0 + "/todos/0/key")
    d = timeline_small(); tl_rows(d)[0]["todos"][0]["kind"] = "topic"
    case("tl1-bad-todo-kind", d, "contract_invalid", "schema", f0 + "/todos/0/kind")
    d = timeline_small(); tl_rows(d)[0]["page"] = "Sign-Up"
    case("tl1-bad-page-slug", d, "contract_invalid", "schema", f0 + "/page")
    d = timeline_small(); tl_rows(d)[0]["todos"][0]["title"] = "T" * 501
    case("tl1-todo-title-too-long", d, "contract_invalid", "schema", f0 + "/todos/0/title")
    d = timeline_small(); rows = tl_rows(d); rows[3]["id"] = rows[0]["id"]
    case("tl1-duplicate-feature-id", d, "contract_invalid", "unique_feature_id", "/groups/0/areas/1/features/0/id")
    d = timeline_small(); rows = tl_rows(d); rows[5]["todos"] = [copy.deepcopy(rows[0]["todos"][0])]
    case("tl1-duplicate-todo-key", d, "contract_invalid", "unique_item_key", "/groups/1/areas/0/features/0/todos/0/key")
    d = timeline_small(); d["pins"][2]["id"] = d["pins"][0]["id"]
    case("tl1-duplicate-pin-id", d, "contract_invalid", "unique_pin_id", "/pins/2/id")
    d = timeline_small(); d["clarification_pages"].append(d["clarification_pages"][0])
    case("tl1-duplicate-page-slug", d, "contract_invalid", "unique_page_slug", "/clarification_pages/3")
    d = timeline_small(); tl_rows(d)[0]["askedIn"] = "2026-01-01-call"
    case("tl1-unknown-pin", d, "contract_invalid", "known_pin", f0 + "/askedIn")
    d = timeline_small(); q = next(q for f in tl_rows(d) for q in f.get("requests", []) if q.get("askedIn"))
    q["askedIn"] = "2026-01-01-call"
    path = next(f"/groups/{g}/areas/{a}/features/{i}/requests/{j}/askedIn"
                for g, gr in enumerate(d["groups"]) for a, ar in enumerate(gr["areas"])
                for i, f in enumerate(ar["features"]) for j, x in enumerate(f.get("requests", [])) if x is q)
    case("tl1-unknown-request-pin", d, "contract_invalid", "known_pin", path)
    d = timeline_small(); d["clarification_pages"].remove(tl_rows(d)[0]["page"])
    case("tl1-unknown-page", d, "contract_invalid", "known_page", f0 + "/page")
    d = timeline_small(); tl_rows(d)[0]["label"] = "Fees &amp; limits"
    case("tl1-html-entity", d, "contract_invalid", "no_html_entities", f0 + "/label")
    # suggestion_status (contract 1.8.0)
    d = timeline_small(); d["suggestion_status"][0]["status"] = "maybe"
    case("tl1-suggestion-bad-status", d, "contract_invalid", "schema", "/suggestion_status/0/status")
    d = timeline_small(); d["suggestion_status"][1]["id"] = "suggestion-2"
    case("tl1-suggestion-bad-id", d, "contract_invalid", "schema", "/suggestion_status/1/id")
    d = timeline_small(); del d["suggestion_status"][0]["reason"]
    case("tl1-suggestion-missing-reason", d, "contract_invalid", "schema", "/suggestion_status/0/reason")
    return cases


def client_timeline(doc: dict) -> dict:
    """The Portal's ClientTimeline1 of a timeline/1 send: the send without the envelope, client_contacts and
    clarification_pages."""
    drop = {"contract", "sent_at", "sent_by", "ba_tools_version", "source_commit", "client_contacts",
            "clarification_pages"}
    return {k: v for k, v in doc.items() if k not in drop}


def timeline_counts(doc: dict) -> dict:
    rows = tl_rows(doc)
    return {"features": len(rows) + sum(len(f.get("requests", [])) for f in rows),
            "items": sum(len(f.get("todos", [])) for f in rows), "client_contacts": len(doc["client_contacts"]),
            "areas": sum(len(g["areas"]) for g in doc["groups"]), "pins": len(doc["pins"])}


# ---- pages (clarification/1) -------------------------------------------------------------------------

def page_envelope() -> dict:
    return {
        "contract": "clarification/1",
        "sent_at": "2026-10-27T10:15:00.000Z",
        "sent_by": "Sample BA",
        "ba_tools_version": "0.9.0",
        "source_commit": "9c1e7a3b5d2f4e6a8b0c1d3e5f7a9b2c4d6e8f01",
    }


def convert_page(cfg: dict) -> dict:
    """A clarification YAML as clarification/1, the way Story 4.3's skill will send it: never-sent fields
    dropped (data-contract §10), description beats standfirst, name beats title, screen src → bare file.
    Since 1.7.0 a screen carries its Figma link: a design screen's from design.figma_file and its node, a Question
    screen's own figma value (as the clarification-page generator does)."""
    def text(value) -> str:
        return str(value).strip()

    def put(out: dict, key: str, value) -> None:
        if value not in (None, "", []):
            out[key] = text(value) if isinstance(value, str) else value

    page = page_envelope()
    page["slug"] = cfg["slug"]
    page["store_key"] = cfg["store_key"]
    url = cfg.get("url")
    if url and "<" in url:  # the example holds a placeholder, not a real link
        url = "https://claude.ai/artifact/5b3f1c2e-8d4a-4e6f-9a1b-probate-example"
    put(page, "url", url)
    page["name"] = text(cfg.get("name") or cfg["title"])
    page["round"] = text(cfg["round"])
    put(page, "description", cfg.get("description") or cfg.get("standfirst"))
    put(page, "problem", cfg.get("problem"))
    put(page, "solution", cfg.get("solution"))

    src = cfg.get("design") or {}
    file_key = src.get("figma_file")
    design: dict = {}
    for key in ("label", "more_label", "summary", "detail"):
        put(design, key, src.get(key))
    screens = []
    for s in src.get("screens") or []:
        screen = {"file": PurePosixPath(s["src"]).name}
        put(screen, "cap", s.get("cap"))
        if s.get("hero"):
            screen["hero"] = True
        if s.get("node") and file_key:
            screen["figma"] = f"https://www.figma.com/design/{file_key}/?node-id={str(s['node']).replace(':', '-')}"
        screens.append(screen)
    if screens:
        design["screens"] = screens
    page["design"] = design

    decisions = []
    for d in cfg.get("decisions") or []:
        out = {"id": text(d["id"])}
        put(out, "date", str(d["date"]) if d.get("date") else None)
        for key in ("who", "how", "title", "detail"):
            put(out, key, d.get(key))
        decisions.append(out)
    if decisions:
        page["decisions"] = decisions

    questions = []
    for q in cfg.get("questions") or []:
        out = {"id": text(q["id"])}
        for key in ("section", "title", "meta", "body", "body2", "snag"):
            put(out, key, q.get(key))
        if q.get("quote"):
            quote = {"text": text(q["quote"]["text"])}
            put(quote, "cite", q["quote"].get("cite"))
            out["quote"] = quote
        for key in ("note", "note_placeholder"):
            put(out, key, q.get(key))
        options = []
        for o in q["options"]:
            opt = {"v": text(o["v"]), "t": text(o["t"])}
            put(opt, "d", o.get("d"))
            if o.get("rec"):
                opt["rec"] = True
            options.append(opt)
        out["options"] = options
        qscreens = []
        for s in q.get("screens") or []:
            screen = {"file": PurePosixPath(s["src"]).name}
            put(screen, "cap", s.get("cap"))
            put(screen, "figma", s.get("figma"))
            qscreens.append(screen)
        if qscreens:
            out["screens"] = qscreens
        questions.append(out)
    page["questions"] = questions
    return page


def probate() -> dict:
    import yaml

    return convert_page(yaml.safe_load(PROBATE.read_text(encoding="utf-8")))


MERCHANT_QUESTIONS = [
    ("payout-day", "A — When money moves", "Which day of the week should merchants be paid?",
     [("monday", "Every Monday"), ("friday", "Every Friday"), ("daily", "Every working day")]),
    ("minimum-payout", "A — When money moves", "Should small balances wait until they reach a minimum?",
     [("no-minimum", "No minimum, pay whatever is there"), ("ten", "Wait until there is at least 10"),
      ("fifty", "Wait until there is at least 50")]),
    ("failed-payout", "B — When something goes wrong", "What happens when a payout bounces?",
     [("retry", "Retry the next day, three times"), ("hold", "Hold it and tell the merchant"),
      ("support", "Hand it to support straight away")]),
    ("refund-source", "B — When something goes wrong", "Where does a refund come from when the balance is empty?",
     [("next-payout", "Take it from the next payout"), ("card", "Charge the merchant's card"),
      ("invoice", "Send the merchant an invoice")]),
    ("statement", "C — What merchants see", "How often should merchants get a statement?",
     [("weekly", "Weekly, with each payout"), ("monthly", "Monthly"), ("on-request", "Only when they ask")]),
    ("currency", "C — What merchants see", "Which currency do statements show?",
     [("merchant", "The merchant's own currency"), ("customer", "The customer's currency, line by line"),
      ("both", "Both, side by side")]),
]


def merchant_question(n: int, qid: str, section: str, title: str, options) -> dict:
    q = {
        "id": qid,
        "section": section,
        "title": title,
        "meta": "Decides — what the payout screens show",
        "body": f"<p class=\"lead\">Question {n + 1} of six.</p><p>We need one answer here before the next "
                "build. <strong>A short answer is fine.</strong></p>",
        "options": [{"v": v, "t": t, "d": f"If you choose this, {t.lower()}."} for v, t in options],
        "note": "Anything else we should know?",
        "note_placeholder": "Optional — a sentence is plenty",
    }
    if n != 5:
        q["options"][0]["rec"] = True
    if n == 1:
        q["quote"] = {"text": "Small merchants watch every payment, so a missing one feels like a lost one.",
                      "cite": "Sample merchant, on the October call"}
    if n == 3:
        q["body2"] = "<p>Refunds today are handled by hand.</p>"
        q["snag"] = "<p><strong>The snag:</strong> an empty balance cannot fund a refund.</p>"
    if n == 2:
        q["screens"] = [{"file": "failed-payout-banner.png", "cap": "The banner a merchant sees after a bounce.",
                         "figma": "https://www.figma.com/design/SaMpLeFiLeKey0001/?node-id=40-12"}]
    if n == 4:
        q["screens"] = [{"file": "statement-email.png", "cap": "The statement email."}]
    return q


def merchants() -> dict:
    """A synthetic page the size of Merchants V7: 6 Questions, 18 options, 4 screens."""
    return {
        **page_envelope(),
        "slug": "merchant-payouts",
        "store_key": "merchant-payouts-v7",
        "url": "https://pages.example.com/clarifications/merchant-payouts/",
        "name": "Merchant payouts",
        "round": "Round V7 · sent 20 Oct 2026 by Sample BA · replaces V6",
        "description": "<p>How and when merchants get their money. <strong>Six questions</strong> are left.</p>",
        "problem": "<p>Merchants are paid by hand once a month, and they cannot see what is coming.</p>",
        "solution": "<p>Payouts run on a schedule, and each one comes with a statement.</p>",
        "design": {
            "label": "What this feature is",
            "more_label": "More screens and detail",
            "summary": "<p>A payout schedule, a balance the merchant can see, and a statement with each payout.</p>",
            "detail": "<p>Four screens are drawn. The questions below are the only things still open.</p>",
            "screens": [
                {"file": "payouts-overview.png", "cap": "The payouts page a merchant sees.", "hero": True,
                 "figma": "https://www.figma.com/design/SaMpLeFiLeKey0001/?node-id=12-345"},
                {"file": "payout-schedule.png", "cap": "Choosing the payout day."},
            ],
        },
        "decisions": [
            {"id": "bank-only", "date": "2026-10-13", "who": "Sample Client", "how": "on the client call",
             "title": "Payouts go only to a bank account", "detail": "No cards or wallets in the first release."},
            {"id": "s2", "title": "Merchants cannot change the payout day themselves"},
        ],
        "questions": [merchant_question(n, *q) for n, q in enumerate(MERCHANT_QUESTIONS)],
    }


def page_files(doc: dict) -> list[str]:
    """The page's screenshot file names in page order: the parts a correct send carries."""
    names = [s["file"] for s in doc.get("design", {}).get("screens", [])]
    for q in doc.get("questions", []):
        names += [s["file"] for s in q.get("screens", [])]
    return names


def filler_question(n: int) -> dict:
    return {"id": f"extra-{n}", "title": f"Extra question {n}", "body": "<p>Filler.</p>",
            "options": [{"v": "yes", "t": "Yes"}, {"v": "no", "t": "No"}]}


def page_invalid_cases() -> dict[str, tuple[dict, dict, list[str] | None]]:
    cases: dict[str, tuple[dict, dict, list[str] | None]] = {}

    def case(name, doc, code, check, path, parts=None):
        cases[name] = (doc, {"code": code, "check": check, "path": path}, parts)

    d = merchants(); d["questions"] += [filler_question(i) for i in range(45)]
    case("page-too-many-questions", d, "contract_invalid", "schema", "/questions")
    d = merchants()
    d["design"]["screens"] = [{"file": f"design-{i:02d}.png"} for i in range(25)]
    d["questions"][0]["screens"] = [{"file": f"payout-day-{i}.png"} for i in range(4)]
    case("page-too-many-screenshots", d, "contract_invalid", "max_screenshots", "/questions/4/screens/0")
    d = merchants(); d["questions"][0]["options"] = []
    case("question-no-options", d, "contract_invalid", "schema", "/questions/0/options")
    d = merchants(); d["questions"][5]["options"] = [{"v": f"o{i}", "t": f"Option {i}"} for i in range(21)]
    case("question-too-many-options", d, "contract_invalid", "schema", "/questions/5/options")
    d = merchants(); d["slug"] = "Merchant-payouts"
    case("slug-capital", d, "contract_invalid", "schema", "/slug")
    d = merchants(); d["slug"] = "merchant payouts"
    case("slug-space", d, "contract_invalid", "schema", "/slug")
    d = merchants(); d["slug"] = "merchant-payouts\n"
    case("slug-trailing-newline", d, "contract_invalid", "schema", "/slug")
    d = merchants(); d["slug"] = "m" * 81
    case("slug-too-long", d, "contract_invalid", "schema", "/slug")
    d = merchants(); d["name"] = "N" * 121
    case("page-name-too-long", d, "contract_invalid", "schema", "/name")
    d = merchants(); d["design"]["summary"] = "<p>" + "S" * 700 + "</p>"
    case("design-summary-too-long", d, "contract_invalid", "schema", "/design/summary")
    d = merchants(); d["questions"][0]["title"] = "Q" * 301
    case("question-title-too-long", d, "contract_invalid", "schema", "/questions/0/title")
    d = merchants(); d["questions"][2]["options"][1]["t"] = "T" * 201
    case("option-text-too-long", d, "contract_invalid", "schema", "/questions/2/options/1/t")
    d = merchants(); del d["questions"][1]["body"]
    case("question-missing-body", d, "contract_invalid", "schema", "/questions/1/body")
    d = merchants(); d["spec"] = "docs/BA/specs/merchant-payouts.md"
    case("page-unknown-field", d, "contract_invalid", "schema", "/spec")
    d = merchants(); d["design"]["screens"][0]["node"] = "123:456"
    case("screen-unknown-field", d, "contract_invalid", "schema", "/design/screens/0/node")
    d = merchants(); d["questions"][3]["id"] = d["questions"][1]["id"]
    case("duplicate-question-id", d, "contract_invalid", "unique_question_id", "/questions/3/id")
    d = merchants(); d["questions"][2]["options"][2]["v"] = d["questions"][2]["options"][0]["v"]
    case("duplicate-option-v", d, "contract_invalid", "unique_option_v", "/questions/2/options/2/v")
    d = merchants(); d["questions"][0]["options"][1]["rec"] = True
    case("two-recommended", d, "contract_invalid", "one_rec_max", "/questions/0/options/1/rec")
    d = merchants(); d["design"]["screens"][1]["file"] = "screens/payout-schedule.png"
    case("file-with-folder", d, "contract_invalid", "bare_file_names", "/design/screens/1/file")
    d = merchants(); d["questions"][4]["screens"][0]["file"] = d["design"]["screens"][0]["file"]
    case("duplicate-file-name", d, "contract_invalid", "bare_file_names", "/questions/4/screens/0/file")
    d = merchants()
    case("screen-without-part", d, "screenshot_mismatch", "screens_match_parts", "/design/screens/1/file",
         [f for f in page_files(d) if f != "payout-schedule.png"])
    d = merchants()
    case("part-without-screen", d, "screenshot_mismatch", "screens_match_parts", "",
         page_files(d) + ["old-screen.png"])
    d = merchants(); d["questions"][0]["title"] = "Which payout day &mdash; Monday or Friday?"
    case("page-html-entity", d, "contract_invalid", "no_html_entities", "/questions/0/title")
    d = merchants(); d["questions"][1]["options"][0]["d"] = "Pay &amp; forget"
    case("page-entity-in-option", d, "contract_invalid", "no_html_entities", "/questions/1/options/0/d")
    d = merchants(); d["contract"] = "clarification/2"
    case("page-version-not-accepted", d, "contract_version_not_accepted", "contract_version", "/contract")
    d = merchants()
    case("part-sent-twice", d, "screenshot_mismatch", "screens_match_parts", "",
         page_files(d) + ["statement-email.png"])
    for name, value, path in [
        ("file-dot", ".", "/design/screens/1/file"),
        ("file-dotdot", "..", "/design/screens/1/file"),
        ("file-control-char", "payout\tschedule.png", "/design/screens/1/file"),
        ("file-colon", "c:payout-schedule.png", "/design/screens/1/file"),
        ("file-named-publish", "publish", "/design/screens/1/file"),
        ("file-case-duplicate", "Payouts-Overview.png", "/design/screens/1/file"),
    ]:
        d = merchants(); d["design"]["screens"][1]["file"] = value
        case(name, d, "contract_invalid", "bare_file_names", path)
    d = merchants(); d["design"]["screens"][1]["hero"] = True
    case("two-heroes", d, "contract_invalid", "one_hero_max", "/design/screens/1/hero")
    d = merchants(); d["decisions"][1]["id"] = d["decisions"][0]["id"]
    case("duplicate-decision-id", d, "contract_invalid", "unique_decision_id", "/decisions/1/id")
    # a screen's Figma link (contract 1.7.0)
    for name, where, value in [
        ("figma-http", ("design", 0), "http://www.figma.com/design/SaMpLeFiLeKey0001/?node-id=12-345"),
        ("figma-other-host", ("question", 2), "https://figma.example.com/design/SaMpLeFiLeKey0001/"),
        ("figma-no-www", ("design", 0), "https://figma.com/design/SaMpLeFiLeKey0001/?node-id=12-345"),
        ("figma-javascript", ("question", 2), "javascript:alert(1)//https://www.figma.com/"),
        ("figma-with-space", ("design", 1), "https://www.figma.com/design/SaMpLe FiLe/"),
        ("figma-html-entity", ("design", 0),
         "https://www.figma.com/design/SaMpLeFiLeKey0001/?node-id=12-345&amp;t=x"),
        ("figma-no-break-space", ("question", 2), "https://www.figma.com/design/SaMpLe\u00a0FiLe/"),
        ("figma-ideographic-space", ("design", 1), "https://www.figma.com/design/SaMpLe\u3000FiLe/"),
    ]:
        d = merchants()
        if where[0] == "design":
            d["design"]["screens"][where[1]]["figma"] = value
            path = f"/design/screens/{where[1]}/figma"
        else:
            d["questions"][where[1]]["screens"][0]["figma"] = value
            path = f"/questions/{where[1]}/screens/0/figma"
        case(name, d, "contract_invalid", "figma_link", path)
    d = merchants(); d["design"]["screens"][0]["figma"] = ""
    case("figma-empty", d, "contract_invalid", "schema", "/design/screens/0/figma")
    for name, value in [("slug-leading-hyphen", "-merchant-payouts"), ("slug-trailing-hyphen", "merchant-payouts-"),
                        ("slug-double-hyphen", "merchant--payouts"), ("slug-only-hyphens", "---")]:
        d = merchants(); d["slug"] = value
        case(name, d, "contract_invalid", "schema", "/slug")
    return cases


def reply_invalid_cases() -> dict[str, tuple[str, dict, str]]:
    """Broken replies and requests: name -> (contract, document, path the case was written for)."""
    r = replies()
    sent, dry = r["publish-reply-1-page-sent.json"], r["publish-reply-1-page-dry-run.json"]
    dash = r["publish-reply-1-sent.json"]
    batch, empty = r["answers-1-batch.json"], r["answers-1-nothing-to-fetch.json"]
    ack_req = r["ack-request-1.json"]
    cases: dict[str, tuple[str, dict, str]] = {}

    def case(name, contract, doc, path):
        cases[name] = (contract, doc, path)

    case("reply-page-sent-with-client-view", "publish-reply/1",
         {**sent, "client_view": dry["client_view"]}, "/client_view")
    case("reply-page-sent-without-publish-id", "publish-reply/1", {**sent, "publish_id": None}, "/publish_id")
    case("reply-page-dry-run-without-client-view", "publish-reply/1",
         {k: v for k, v in dry.items() if k != "client_view"}, "/client_view")
    case("reply-page-with-contact-names", "publish-reply/1",
         {**dry, "client_contact_names": []}, "/client_contact_names")
    case("reply-page-with-dashboard-counts", "publish-reply/1", {**sent, "counts": dash["counts"]}, "/counts/features")
    case("reply-dashboard-with-round", "publish-reply/1", {**dash, "round": sent["round"]}, "/round")
    removed = r["publish-reply-1-dashboard-2-pages-removed.json"]
    case("reply-pages-removed-without-title", "publish-reply/1",
         {**removed, "pages_removed": [{"slug": "payouts"}]}, "/pages_removed/0/title")
    case("reply-page-with-pages-removed", "publish-reply/1",
         {**sent, "pages_removed": removed["pages_removed"]}, "/pages_removed")
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["file"] = "payouts-overview.png"
    case("reply-page-screen-file-name", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/file")
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["media"] = "/media/../../etc/passwd"
    case("reply-page-media-not-a-uuid", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/media")
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["figma"] = "https://example.com/x"
    case("reply-page-figma-not-figma", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/figma")
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["media"] = "/media/" + "-" * 36
    case("reply-page-media-only-hyphens", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/media")
    case("answers-no-batch-with-answers", "answers/1", {**empty, "answers": batch["answers"]}, "/answers")
    case("answers-no-batch-with-hold", "answers/1",
         {**empty, "reserved_until": batch["reserved_until"]}, "/reserved_until")
    case("answers-batch-without-answers", "answers/1", {**batch, "answers": []}, "/answers")
    case("answers-batch-without-hold", "answers/1", {**batch, "reserved_until": None}, "/reserved_until")
    a = copy.deepcopy(batch); a["answers"][0]["note"] = "n" * 5001
    case("answers-note-too-long", "answers/1", a, "/answers/0/note")
    a = copy.deepcopy(batch); del a["answers"][0]["replaces"]
    case("answers-missing-replaces", "answers/1", a, "/answers/0/replaces")
    a = copy.deepcopy(batch); a["answers"][1]["note"] = None
    case("answers-no-option-no-note", "answers/1", a, "/answers/1")
    a = copy.deepcopy(batch); a["answers"][0]["replaces"]["option"] = None
    case("answers-replaces-no-option-no-note", "answers/1", a, "/answers/0/replaces")
    case("ack-request-with-contract", "ack-request/1", {**ack_req, "contract": "ack-request/1"}, "/contract")
    case("ack-request-bad-batch-id", "ack-request/1",
         {"batch_id": "not-a-uuid-not-a-uuid-not-a-uuid-xxxx"}, "/batch_id")
    case("ack-request-empty", "ack-request/1", {}, "/batch_id")
    # answers/2 and reserve-request/1 (contract 1.4.0)
    b2, e2 = r["answers-2-batch.json"], r["answers-2-nothing-to-fetch.json"]
    case("answers2-missing-updates", "answers/2", {k: v for k, v in b2.items() if k != "updates"}, "/updates")
    case("answers2-no-batch-with-updates", "answers/2", {**e2, "updates": b2["updates"]}, "/updates")
    case("answers2-batch-with-nothing", "answers/2", {**b2, "answers": [], "updates": []}, "")
    a = copy.deepcopy(b2); a["updates"][0]["item"]["key"] = "ABCDEF012345"
    case("answers2-update-bad-item-key", "answers/2", a, "/updates/0/item/key")
    a = copy.deepcopy(b2); a["updates"][0]["item"]["kind"] = "topic"
    case("answers2-update-unknown-kind", "answers/2", a, "/updates/0/item/kind")
    a = copy.deepcopy(b2); a["updates"][1]["note"] = "n" * 2001
    case("answers2-update-note-too-long", "answers/2", a, "/updates/1/note")
    a = copy.deepcopy(b2); a["updates"][1]["note"] = ""
    case("answers2-update-empty-note", "answers/2", a, "/updates/1/note")
    a = copy.deepcopy(b2); del a["updates"][0]["resolved"]
    case("answers2-update-missing-resolved", "answers/2", a, "/updates/0/resolved")
    case("answers2-sent-as-answers1", "answers/1", b2, "/contract")
    # answers/3 (contract 1.8.0): answers/2 plus the Client's suggestions
    b3, e3 = r["answers-3-batch.json"], r["answers-3-nothing-to-fetch.json"]
    case("answers3-missing-suggestions", "answers/3", {k: v for k, v in b3.items() if k != "suggestions"},
         "/suggestions")
    case("answers3-no-batch-with-suggestions", "answers/3", {**e3, "suggestions": b3["suggestions"]}, "/suggestions")
    case("answers3-batch-with-nothing", "answers/3", {**b3, "answers": [], "updates": [], "suggestions": []}, "")
    a = copy.deepcopy(b3); a["suggestions"][0]["type"] = "wish"
    case("answers3-suggestion-bad-type", "answers/3", a, "/suggestions/0/type")
    a = copy.deepcopy(b3); a["suggestions"][0]["title"] = "T" * 121
    case("answers3-suggestion-title-too-long", "answers/3", a, "/suggestions/0/title")
    a = copy.deepcopy(b3); a["suggestions"][1]["link"] = "http://example.com/sheet"
    case("answers3-suggestion-link-http", "answers/3", a, "/suggestions/1/link")
    a = copy.deepcopy(b3); a["suggestions"][1]["urgency"] = "urgent"
    case("answers3-suggestion-bad-urgency", "answers/3", a, "/suggestions/1/urgency")
    a = copy.deepcopy(b3); del a["suggestions"][0]["area"]
    case("answers3-suggestion-missing-area", "answers/3", a, "/suggestions/0/area")
    case("answers3-sent-as-answers2", "answers/2", b3, "/contract")
    req = r["reserve-request-1.json"]
    case("reserve-request-empty", "reserve-request/1", {}, "/accept")
    case("reserve-request-empty-accept", "reserve-request/1", {"accept": []}, "/accept")
    case("reserve-request-accept-twice", "reserve-request/1", {"accept": ["answers/2", "answers/2"]}, "/accept")
    case("reserve-request-with-contract", "reserve-request/1", {**req, "contract": "reserve-request/1"}, "/contract")
    # connect-request/1 and connect/1 (contract 1.5.0)
    creq, con = r["connect-request-1.json"], r["connect-1.json"]
    case("connect-request-with-contract", "connect-request/1", {**creq, "contract": "connect-request/1"}, "/contract")
    case("connect-request-missing-code", "connect-request/1", {"label": creq["label"]}, "/code")
    case("connect-request-code-look-alike", "connect-request/1", {**creq, "code": "K0P-4XM"}, "/code")
    case("connect-request-code-too-long", "connect-request/1", {**creq, "code": "K7P-4XMA"}, "/code")
    case("connect-request-code-dash-in-wrong-place", "connect-request/1", {**creq, "code": "K7-P4XM"}, "/code")
    case("connect-request-code-trailing-newline", "connect-request/1", {**creq, "code": "K7P4XM\n"}, "/code")
    case("connect-request-empty-label", "connect-request/1", {**creq, "label": ""}, "/label")
    case("connect-request-label-too-long", "connect-request/1", {**creq, "label": "x" * 101}, "/label")
    case("connect-missing-key", "connect/1", {k: v for k, v in con.items() if k != "key"}, "/key")
    case("connect-key-too-short", "connect/1", {**con, "key": con["key"][:-1]}, "/key")
    case("connect-key-not-base64url", "connect/1", {**con, "key": "+" + con["key"][1:]}, "/key")
    case("connect-last4-too-long", "connect/1", {**con, "key_last4": con["key"][-5:]}, "/key_last4")
    case("connect-project-bad-id", "connect/1",
         {**con, "project": {**con["project"], "id": "not-a-uuid-not-a-uuid-not-a-uuid-xxxx"}}, "/project/id")
    case("connect-project-empty-name", "connect/1", {**con, "project": {**con["project"], "name": ""}},
         "/project/name")
    case("connect-unknown-field", "connect/1", {**con, "key_hash": "abc"}, "/key_hash")
    return cases


def reply_expected(name: str, contract: str, doc: dict, path: str) -> dict:
    """A reply or request case: the contract it is checked against, and every (check, path) pair."""
    import checks

    found = checks.check_reply(doc, contract)
    assert found, f"{name}: passes, but should fail"
    pairs = sorted({(d["check"], d["path"]) for d in found})
    assert ("schema", path) in pairs, f"{name}: {pairs}"
    return {"contract": contract, "details": [{"check": c, "path": p} for c, p in pairs]}


def page_client_view(doc: dict, media: str | None = None) -> dict:
    """ClientRound (AD-4) as the Portal builds it on a dry run: client and id fields only, screens as
    { media, cap, figma } with the hero first. The Portal builds the real one; this only makes a sample reply."""
    def screen(s):
        out = {"media": media}
        for key in ("cap", "figma"):
            if key in s:
                out[key] = s[key]
        return out

    design_src = doc["design"]
    screens = sorted(design_src.get("screens", []), key=lambda s: not s.get("hero"))
    design = {k: design_src[k] for k in ("label", "more_label", "summary", "detail") if k in design_src}
    design["screens"] = [screen(s) for s in screens]
    view = {k: doc[k] for k in ("slug", "name", "round", "description", "problem", "solution") if k in doc}
    view["design"] = design
    view["decisions"] = [{k: v for k, v in d.items() if k != "id"} for d in doc.get("decisions", [])]
    questions = []
    for q in doc["questions"]:
        out = {k: copy.deepcopy(v) for k, v in q.items() if k != "screens"}
        out["screens"] = [screen(s) for s in q.get("screens", [])]
        questions.append(out)
    view["questions"] = questions
    return view


# ---- results and replies -----------------------------------------------------------------------------

def expected_result(name: str, doc: dict, stated: dict, kind: str = "dashboard",
                    parts: list[str] | None = None) -> dict:
    """Every (check, path) pair the check gives, sorted. Both runners compare this set exactly.
    The pair the case was written for must be among them, with the stated code."""
    import checks  # the skill folder is on sys.path (see main guard)

    if kind == "clarification":
        result = checks.check_publish(doc, kind, page_files(doc) if parts is None else parts)
    else:
        result = checks.check_publish(doc)
    assert result is not None, f"{name}: passes, but should fail"
    assert result["code"] == stated["code"], f"{name}: {result['code']}"
    pairs = sorted({(d["check"], d["path"]) for d in result["details"]})
    assert (stated["check"], stated["path"]) in pairs, f"{name}: {pairs}"
    out = {"code": result["code"], "details": [{"check": c, "path": p} for c, p in pairs]}
    return {"kind": kind, **out} if kind != "dashboard" else out


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
    dump(FIXTURES / "valid" / "dashboard-2-small.json", small2())
    dump(FIXTURES / "valid" / "dashboard-2-real-size.json", real_size2())
    dump(FIXTURES / "valid" / "dashboard-2-with-pages.json", with_pages())
    dump(FIXTURES / "valid" / "dashboard-2-with-1-4-fields.json", with_1_4_fields())
    for name, (doc, stated) in v2_invalid_cases().items():
        dump(FIXTURES / "invalid" / name / "input.json", doc)
        dump(FIXTURES / "invalid" / name / "expected.json", expected_result(name, doc, stated))
    dump(FIXTURES / "valid" / "timeline-1-small.json", timeline_small())
    dump(FIXTURES / "valid" / "timeline-1-real-size.json", timeline_real_size())
    for name, (doc, stated) in tl_invalid_cases().items():
        dump(FIXTURES / "invalid" / name / "input.json", doc)
        dump(FIXTURES / "invalid" / name / "expected.json", expected_result(name, doc, stated))
    dump(FIXTURES / "valid" / "clarification-1-probate.json", probate())
    dump(FIXTURES / "valid" / "clarification-1-merchants-v7-size.json", merchants())
    for name, (doc, stated, parts) in page_invalid_cases().items():
        dump(FIXTURES / "invalid" / name / "input.json", doc)
        dump(FIXTURES / "invalid" / name / "expected.json",
             expected_result(name, doc, stated, "clarification", parts))
        if parts is not None:
            dump(FIXTURES / "invalid" / name / "parts.json", parts)
    for name, data in replies().items():
        dump(FIXTURES / "valid" / name, data)
    for name, (contract, doc, path) in reply_invalid_cases().items():
        dump(FIXTURES / "invalid" / name / "input.json", doc)
        dump(FIXTURES / "invalid" / name / "expected.json", reply_expected(name, contract, doc, path))


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
    page = merchants()
    page_sent = {
        "contract": "publish-reply/1",
        "publish_id": "019a2b10-7e2c-7a35-8c4d-5e6f7a8b9c0d",
        "received_at": "2026-10-27T10:15:02.480Z",
        "kind": "page",
        "counts": {"questions": 6, "screenshots": 4},
        "round": {"key": page["store_key"], "label": page["round"], "new": True},
        "dry_run": False,
    }
    page_dry = {**page_sent, "publish_id": None, "dry_run": True,
                "client_view": page_client_view(page)}
    person = {"name": "Sample Client", "email": "sample.client@example.com"}
    page_ref = {"slug": page["slug"], "title": page["name"]}
    round_ref = {"key": page["store_key"], "label": page["round"], "published_at": "2026-10-20T08:00:00.000Z"}
    answers = {
        "contract": "answers/1",
        "batch_id": "019a2c44-1b2d-7c3e-9f40-a1b2c3d4e5f6",
        "reserved_until": "2026-10-27T11:10:00.000Z",
        "last_fetched_at": "2026-10-24T16:42:05.120Z",
        "answers": [
            {
                "id": "019a2b90-0a1b-7c2d-8e3f-405162738495",
                "sent_at": "2026-10-26T14:03:11.000Z",
                "person": person,
                "page": page_ref,
                "round": round_ref,
                "question": {"id": "payout-day", "title": MERCHANT_QUESTIONS[0][2], "position": 1},
                "option": {"v": "friday", "text": "Every Friday"},
                "note": "Friday suits our cash flow better.",
                "replaces": {
                    "id": "019a2a01-9f8e-7d6c-8b5a-493827161504",
                    "sent_at": "2026-10-22T09:12:40.000Z",
                    "person_name": "Sample Client",
                    "option": {"v": "monday", "text": "Every Monday"},
                    "note": None,
                },
            },
            {
                "id": "019a2b91-1c2d-7e3f-9a4b-5c6d7e8f9a0b",
                "sent_at": "2026-10-26T14:03:11.000Z",
                "person": {"name": "Second Person", "email": "second.person@example.com"},
                "page": page_ref,
                "round": round_ref,
                "question": {"id": "statement", "title": MERCHANT_QUESTIONS[4][2], "position": 5},
                "option": None,
                "note": "We need to ask our accountant first.",
                "replaces": None,
            },
        ],
    }
    answers_empty = {
        "contract": "answers/1", "batch_id": None, "reserved_until": None,
        "last_fetched_at": "2026-10-27T11:00:31.007Z", "answers": [],
    }
    ack = {
        "contract": "ack/1", "batch_id": answers["batch_id"], "handed_out": 2,
        "confirmed_at": "2026-10-27T11:00:31.007Z",
    }
    # connect/1: a made-up key (43 characters of base64url), never a real one.
    fake_key = "sample-connect-key-not-real-" + "0123456789abcde"
    connect = {"contract": "connect/1",
               "project": {"id": "019a2a6e-1b2c-7d3e-8f40-a1b2c3d4e5f6", "name": "Sample Project"},
               "key": fake_key, "key_last4": fake_key[-4:]}
    # answers/2: the Client's saves on Items. Keys are the BA page's: sha1("<kind>|<title>").
    other = {"name": "Second Person", "email": "second.person@example.com"}
    wait_t, agenda_t = "Send the employer list for the pilot", "Agree the fee for early repayment"
    updates = [
        {"id": "019a2b95-0a00-7c00-8a00-000000000001", "sent_at": "2026-10-26T15:00:00.000Z", "person": person,
         "item": {"key": item_key("waiting", wait_t), "kind": "waiting", "title": wait_t},
         "note": "We sent the list to Sample BA by email.", "resolved": False},
        {"id": "019a2b95-0a00-7c00-8a00-000000000002", "sent_at": "2026-10-26T16:30:00.000Z", "person": other,
         "item": {"key": item_key("agenda", agenda_t), "kind": "agenda", "title": agenda_t},
         "note": "Our board agreed: the fee stays at 50.\nWe can talk about it on the call.", "resolved": False},
        {"id": "019a2b95-0a00-7c00-8a00-000000000003", "sent_at": "2026-10-26T17:45:00.000Z", "person": person,
         "item": {"key": item_key("waiting", wait_t), "kind": "waiting", "title": wait_t},
         "note": None, "resolved": True},
    ]
    answers2 = {**answers, "contract": "answers/2", "updates": updates}
    updates_only = {**answers2, "batch_id": "019a2c45-2c3d-7d4e-8f50-b1c2d3e4f5a6", "answers": [],
                    "updates": updates[1:2]}
    doc2 = small2()
    dry2 = {**base, "publish_id": None, "dry_run": True, "counts": {
        "features": len(doc2["features"]), "items": len(doc2["items"]),
        "client_contacts": len(doc2["client_contacts"]), "areas": len(doc2["areas"]),
        "topics": len(doc2["topics"]), "cards": len(doc2["cards"]),
        "tickets": sum(len(c["tickets"]) for c in doc2["cards"]),
    }, "client_view": client_view2(doc2), "client_contact_names": [c["name"] for c in doc2["client_contacts"]]}
    removed = [{"slug": "old-onboarding-questions", "title": "Onboarding questions"},
               {"slug": "employer-search", "title": "Employer search: who can be found"}]
    dry_pages = {**dry2, "pages_removed": removed}
    sent_pages = {**base, "counts": dry2["counts"], "pages_removed": removed}
    tl = timeline_small()
    tl_dry = {**base, "publish_id": None, "dry_run": True, "counts": timeline_counts(tl),
              "client_view": client_timeline(tl), "client_contact_names": [c["name"] for c in tl["client_contacts"]],
              "pages_removed": removed[:1]}
    tl_sent = {**base, "counts": timeline_counts(tl), "pages_removed": []}
    todo_t = "Write the collections note for the pilot"
    todo_update = {**updates_only, "updates": [{
        "id": "019a2b95-0a00-7c00-8a00-000000000004", "sent_at": "2026-11-06T09:00:00.000Z", "person": person,
        "item": {"key": item_key("todo", todo_t), "kind": "todo", "title": todo_t},
        "note": "We would like to read it before the call.", "resolved": False}]}
    # answers/3 (contract 1.8.0): the Client's suggestions from the Portal Timeline.
    suggestions = [
        {"id": SUGGESTION_IDS[0], "sent_at": "2026-11-06T12:00:00.000Z", "person": person, "type": "change",
         "feature": "sign-up-with-phone-number", "feature_name": "Sign-up with phone number", "area": "Onboarding", "title": "Let people sign up with email too",
         "what": "Some staff have no work phone.\nThey cannot finish sign-up today.", "urgency": "soon",
         "link": None},
        {"id": SUGGESTION_IDS[1], "sent_at": "2026-11-06T12:30:00.000Z", "person": other, "type": "feature",
         "feature": None, "feature_name": None, "area": "Back office", "title": "A monthly report of advances by employer",
         "what": "", "urgency": "nice", "link": "https://example.com/sheets/report-sample"},
        {"id": SUGGESTION_IDS[2], "sent_at": "2026-11-06T13:15:00.000Z", "person": person, "type": "problem",
         "feature": "advance-request", "feature_name": "Advance request", "area": "Loans", "title": "The fee shows twice on the confirm screen",
         "what": "Seen on Android.", "urgency": "blocking", "link": None},
    ]
    answers3 = {**answers2, "contract": "answers/3", "batch_id": "019a5a20-3d4e-7e5f-8a60-c1d2e3f4a5b6",
                "suggestions": suggestions}
    return {
        "answers-3-batch.json": answers3,
        "answers-3-suggestions-only.json": {**answers3, "answers": [], "updates": [], "suggestions": suggestions[1:2]},
        "answers-3-nothing-to-fetch.json": {**answers_empty, "contract": "answers/3", "updates": [],
                                            "suggestions": []},
        "publish-reply-1-sent.json": base,
        "publish-reply-1-timeline-1-dry-run.json": tl_dry,
        "publish-reply-1-timeline-1-sent.json": tl_sent,
        "answers-2-todo-update.json": todo_update,
        "publish-reply-1-dashboard-2-pages-removed-dry-run.json": dry_pages,
        "publish-reply-1-dashboard-2-pages-removed.json": sent_pages,
        "publish-reply-1-dry-run.json": dry,
        "publish-reply-1-dashboard-2-dry-run.json": dry2,
        "status-1.json": status,
        "publish-reply-1-page-sent.json": page_sent,
        "publish-reply-1-page-dry-run.json": page_dry,
        "answers-1-batch.json": answers,
        "answers-1-nothing-to-fetch.json": answers_empty,
        "answers-2-batch.json": answers2,
        "answers-2-updates-only.json": updates_only,
        "answers-2-nothing-to-fetch.json": {**answers_empty, "contract": "answers/2", "updates": []},
        "reserve-request-1.json": {"accept": ["answers/1", "answers/2"]},
        "reserve-request-1-answers-3.json": {"accept": ["answers/1", "answers/2", "answers/3"]},
        "ack-request-1.json": {"batch_id": answers["batch_id"]},
        "ack-1.json": ack,
        "connect-request-1.json": {"code": "K7P-4XM", "label": "acme-docs · Sample BA"},
        "connect-request-1-no-dash-lower-case.json": {"code": "k7p4xm", "label": "acme-docs"},
        "connect-1.json": connect,
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
