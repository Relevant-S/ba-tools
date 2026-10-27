"""Writes contract/fixtures/ — run with `uv run python tests/make_fixtures.py` after changing it.

The Dashboard data is synthetic (no client data), sized like Acme Lending: 18 Features, 148 Items.
Each invalid case is the small base file with one thing broken, plus expected.json.

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
    dropped (data-contract §10), description beats standfirst, name beats title, screen src → bare file."""
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
    design: dict = {}
    for key in ("label", "more_label", "summary", "detail"):
        put(design, key, src.get(key))
    screens = []
    for s in src.get("screens") or []:
        screen = {"file": PurePosixPath(s["src"]).name}
        put(screen, "cap", s.get("cap"))
        if s.get("hero"):
            screen["hero"] = True
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
        q["screens"] = [{"file": "failed-payout-banner.png", "cap": "The banner a merchant sees after a bounce."}]
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
                {"file": "payouts-overview.png", "cap": "The payouts page a merchant sees.", "hero": True},
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
    d = merchants(); d["design"]["screens"][0]["figma"] = "123:456"
    case("screen-unknown-field", d, "contract_invalid", "schema", "/design/screens/0/figma")
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
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["file"] = "payouts-overview.png"
    case("reply-page-screen-file-name", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/file")
    view = copy.deepcopy(dry["client_view"]); view["design"]["screens"][0]["media"] = "/media/../../etc/passwd"
    case("reply-page-media-not-a-uuid", "publish-reply/1", {**dry, "client_view": view},
         "/client_view/design/screens/0/media")
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
    { media, cap } with the hero first. The Portal builds the real one; this only makes a sample reply."""
    def screen(s):
        out = {"media": media}
        if "cap" in s:
            out["cap"] = s["cap"]
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
    return {
        "publish-reply-1-sent.json": base,
        "publish-reply-1-dry-run.json": dry,
        "status-1.json": status,
        "publish-reply-1-page-sent.json": page_sent,
        "publish-reply-1-page-dry-run.json": page_dry,
        "answers-1-batch.json": answers,
        "answers-1-nothing-to-fetch.json": answers_empty,
        "ack-request-1.json": {"batch_id": answers["batch_id"]},
        "ack-1.json": ack,
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
