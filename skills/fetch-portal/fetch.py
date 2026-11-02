"""fetch-portal — bring the Client's Answers from the Relevant Clients Portal into docs/BA/intake/, and the Client's
updates on dashboard items into docs/BA/portal-updates/. Prints one JSON line.

    uv run --project <skills>/fetch-portal python <skills>/fetch-portal/fetch.py [--root <project>]

Run from the project root, or pass --root. What it does, in order:
  1. Leftover .tmp files from an earlier run (docs/BA/intake/portal-<batch_id>-<slug>.md.tmp, and
     docs/BA/portal-updates/portal-<batch_id>-<product>.json.tmp): ack that batch.
     200 → rename to the real name; batch_expired or batch_unknown → delete; no reply → keep them and stop.
  2. Reserve a batch: POST /api/v1/answers/reserve with {"accept": ["answers/1", "answers/2"]}. The Portal replies
     answers/2 (Answers plus the Client's updates: notes and Resolved ticks on Waiting and agenda items), or
     answers/1 (an older Portal: Answers only). Nothing new → say so, write nothing.
  3. Write one file per Clarification page under a .tmp name, and one updates file per product when there are
     updates, then a marker portal-<batch_id>.complete once every file is on disk, then ack:
     POST /api/v1/answers/ack (3 tries). A leftover batch with no marker was cut off mid-write: its .tmp files are
     deleted, never acked, and its Answers and updates come again after the hold.
  4. On 200, rename each to docs/BA/intake/YYYY-MM-DD-HHMM-portal-<slug>.md, and the updates file to
     docs/BA/portal-updates/YYYY-MM-DD-HHMM-<product>.json (-2, -3 … if taken).

The updates file is in the shape of the BA page's own `resolutions` store, one entry per item:
{key, kind, title, resolved, notes: [{at, text, by}], updatedAt}, notes oldest first. ba-dashboard's
"sync the mind map" (map/sync.py) takes it as it is.

Settings: tools.portal.url in docs/BA/specs/.ba-profile.yml; the Publish key in .env at the repo root, which git
must ignore: PORTAL_PUBLISH_KEY in a repo with one product. A repo with two or more products has one Portal project
per product: tools.portal.products names each product's .env variable, and the steps above run for every product, in
that order, each with its own key. One product's failure does not stop the others. Keys are never printed. The
settings are read by portal-publish's targets.py (one copy for both skills). Every reply is checked against the
portal-publish contract (answers/1 or answers/2, ack/1); a reply that fails stops that product's run: nothing
written, no ack.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent
CHECKS_PY = SKILLS / "portal-publish" / "checks.py"
TARGETS_PY = SKILLS / "portal-publish" / "targets.py"

PROFILE = "docs/BA/specs/.ba-profile.yml"
INTAKE = "docs/BA/intake"
UPDATES = "docs/BA/portal-updates"
ACCEPT = ["answers/1", "answers/2"]   # the batch versions this fetcher reads (reserve-request/1)
RESERVE = "/api/v1/answers/reserve"
ACK = "/api/v1/answers/ack"
STATUS = "/api/v1/status"
TIMEOUT = 30.0
ACK_TRIES = 3
ACK_WAITS = (2.0, 5.0)            # seconds before the 2nd and the 3rd ack try
SETUP_HINT = "Run `ba-setup project`"
KEY_PLACE = "Admin → Projects → the Project → Publishing"
DEFAULT_KEY = "PORTAL_PUBLISH_KEY"
KEY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
key_name = DEFAULT_KEY            # the .env variable of the product being fetched; run() sets it, messages name it
TMP_NAME = re.compile(r"^portal-([0-9a-fA-F-]{36})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md\.tmp$")
DONE_NAME = re.compile(r"^portal-([0-9a-fA-F-]{36})\.complete$")
UPD_TMP_NAME = re.compile(r"^portal-([0-9a-fA-F-]{36})-([a-z0-9]+(?:-[a-z0-9]+)*)\.json\.tmp$")
HOLD = "about 10 minutes"
update_counts: dict[Path, int] = {}   # an updates file -> how many Client saves it holds (for the summary)


class Stop(Exception):
    """Stop the run. The message is shown to the BA as it is. `files`: intake files already written this run."""

    files: list[str] = []


class NoReply(Stop):
    """The Portal did not answer (connect error, timeout, or a 5xx on every ack try)."""


def load_module(path: Path, name: str):
    """A module from the sibling portal-publish folder: one copy, never a copy here."""
    if not path.exists():
        raise Stop(f"fetch-portal needs the portal-publish skill next to it ({path} is missing). "
                   "Install ba-tools again. Nothing was written.")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_checks():
    """portal-publish's checks.py: the contract's checks."""
    return load_module(CHECKS_PY, "portal_publish_checks")


def load_targets():
    """portal-publish's targets.py: the Portal address, and each product's .env variable and key."""
    return load_module(TARGETS_PY, "portal_publish_targets")


checks = None    # loaded in main(), so a missing portal-publish gives a plain stop message
targets = None   # the same, loaded on first use


def tg():
    global targets
    if targets is None:
        targets = load_targets()
    return targets


# ---------------------------------------------------------------- output and arguments

def out(obj: dict) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))


def arg(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


# ---------------------------------------------------------------- settings (portal-publish's targets.py)

def check_url(url: str) -> None:
    """The key travels in the request: plain http:// only to this computer or a .localhost / .test name."""
    t = tg()
    try:
        t.check_url(url)
    except t.TargetError as e:
        raise Stop(f"{e} Nothing was written.") from None


def settings(root: Path) -> tuple[str, dict, list, dict]:
    """The Portal address, the profile, the targets [(product, .env variable, key)] in tools.portal.products
    order, and the values in .env. Stops before anything is asked of the Portal."""
    t = tg()
    try:
        url, prof, env = t.settings(root)
        return url, prof, t.portal_targets(root, prof, env), env
    except t.TargetError as e:
        raise Stop(f"{e} Nothing was written.") from None


# ---------------------------------------------------------------- times

def utc(stamp: str | None) -> str:
    """'2026-10-26T14:03:11.000Z' → '2026-10-26 14:03 UTC'."""
    s = str(stamp or "")
    return f"{s[:10]} {s[11:16]} UTC" if len(s) >= 16 else f"{s} UTC"


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- the Portal

def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def sleep(seconds: float) -> None:
    time.sleep(seconds)


def portal_error(r: httpx.Response, doc) -> tuple[str, str]:
    """The error code and the Portal's message; ('', '') when the reply is not the error envelope."""
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict) or not err.get("code"):
        return "", ""
    return str(err["code"]), str(err.get("message") or "").strip()


def refused(url: str, r: httpx.Response, doc, step: str) -> Stop:
    tail = ("Nothing was written." if step in ("reserve", "status check") else
            f"Any .tmp files stay in {INTAKE}/ (triage skips them); the next run finishes them.")
    code, msg = portal_error(r, doc)
    if not code:
        return Stop(f"The Portal's reply to the {step} was not understood (HTTP {r.status_code}). It may be an older "
                    f"Portal. {tail}")
    if code == "invalid_key":
        return Stop(f"This key is not valid for this Project. The key in .env ({key_name}) is not this "
                    f"Project's Publish key. Ask an Admin for it ({KEY_PLACE} → Regenerate key), put it in .env, "
                    f"and run again. {tail}")
    return Stop(f"The Portal refused the {step} ({code}): {msg or 'no message'}. {tail}")


def call(url: str, key: str, path: str, body: bytes | None):
    """POST to the Portal. Returns (response, parsed JSON or None). Raises NoReply when nothing comes back."""
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        with http_client() as client:
            r = client.post(url + path, content=body or b"", headers=headers)
    except httpx.InvalidURL:
        raise Stop(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it. "
                   "Nothing was written.") from None
    except httpx.RequestError:
        raise NoReply(f"The Portal is not reachable at {url}. Check that it is running and that tools.portal.url "
                      "is right.") from None
    try:
        doc = r.json()
    except ValueError:
        doc = None
    return r, doc


def reserve(url: str, key: str) -> dict:
    """Reserve a batch, saying this fetcher reads answers/1 and answers/2. An older Portal replies answers/1: its
    batch gets an empty `updates` list here, so the rest of the run treats both the same."""
    body = {"accept": ACCEPT}
    if checks.check_reply(body, "reserve-request/1"):
        raise Stop("fetch-portal's reserve request does not match the portal-publish contract (reserve-request/1). "
                   "Install ba-tools again. Nothing was written.")
    try:
        r, doc = call(url, key, RESERVE, json.dumps(body).encode("utf-8"))
    except NoReply as e:
        raise Stop(f"{e} Nothing was written. If the Portal had already set Answers aside for this fetch, they "
                   f"come again after the hold ({HOLD}).") from None
    if r.status_code != 200:
        raise refused(url, r, doc, "reserve")
    contract = doc.get("contract") if isinstance(doc, dict) else None
    if contract not in ACCEPT or checks.check_reply(doc, contract):
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                   "Nothing was written and nothing was confirmed.")
    doc.setdefault("updates", [])
    return doc


def ack(url: str, key: str, batch_id: str) -> tuple[str, dict | None]:
    """Ack one batch, up to 3 tries. Returns ('ok', reply), ('expired', None) or ('unknown', None).
    Raises NoReply when no try got an answer, Stop on any other refusal or an odd reply."""
    body = {"batch_id": batch_id}
    if checks.check_reply(body, "ack-request/1"):
        raise Stop(f"The batch id {batch_id} is not one the Portal gave out. Nothing was confirmed.")
    raw = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(ACK_TRIES):
        if attempt:
            sleep(ACK_WAITS[min(attempt - 1, len(ACK_WAITS) - 1)])
        try:
            r, doc = call(url, key, ACK, raw)
        except NoReply as e:
            last = e
            continue
        if r.status_code >= 500:
            last = NoReply(f"The Portal at {url} had an error (HTTP {r.status_code}) on every try.")
            continue
        if r.status_code == 200:
            if not isinstance(doc, dict) or checks.check_reply(doc, "ack/1") or doc.get("batch_id") != batch_id:
                raise Stop(f"The Portal's reply to the ack was not understood (HTTP {r.status_code}). It may be an "
                           f"older Portal. Any .tmp files stay in {INTAKE}/ (triage skips them); the next run "
                           "finishes them.")
            return "ok", doc
        code, _ = portal_error(r, doc)
        if code == "batch_expired":
            return "expired", None
        if code == "batch_unknown":
            return "unknown", None
        raise refused(url, r, doc, "ack")
    raise last


# ---------------------------------------------------------------- the intake file

def one_line(s) -> str:
    """Titles, names and labels on one line, so a line break cannot break the header or a heading."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in str(s)).split())


def quoted(s: str) -> str:
    return "'" + one_line(s).replace("'", "''") + "'"


def option_text(opt) -> str:
    return f"{one_line(opt['text'])} (`{one_line(opt['v'])}`)" if opt else "none (note only)"


def note_block(note) -> list[str]:
    """A note, indented 4 spaces (Vadim, 2026-10-27), every line kept."""
    if not note:
        return ["none"]
    return ["", *[("    " + ln) if ln.strip() else "" for ln in str(note).replace("\r\n", "\n").split("\n")]]


def render(project: str, slug: str, answers: list[dict], fetched: dt.datetime, product: str = "") -> str:
    """One page's Answers as an intake file. Answers stay in the order the Portal sent. `product`: in a repo with
    two or more products, the product whose Portal project the Answers came from (a `product:` header line)."""
    fetched_at = fetched.strftime("%Y-%m-%d %H:%M UTC")
    title = one_line(answers[-1]["page"]["title"])
    rounds, participants = [], []
    for a in answers:
        rnd = a["round"]
        if rnd["key"] not in [x["key"] for x in rounds]:
            rounds.append({"key": rnd["key"], "label": one_line(rnd["label"]),
                           "published": utc(rnd["published_at"])})
        who = f"{one_line(a['person']['name'])} <{one_line(a['person']['email'])}>"
        if who not in participants:
            participants.append(who)
    sent = sorted(a["sent_at"] for a in answers)

    lines = ["---", "source: portal", f"date: {fetched.strftime('%Y-%m-%d')}", f"project: {quoted(project)}",
             *([f"product: {quoted(product)}"] if product else []), f"page: {quoted(slug)}", f"page_title: {quoted(title)}", "rounds:"]
    for rnd in rounds:
        lines += [f"  - key: {quoted(rnd['key'])}", f"    label: {quoted(rnd['label'])}",
                  f"    published: {quoted(rnd['published'])}"]
    lines.append("participants:")
    lines += [f"  - {quoted(p)}" for p in participants]
    lines += [f"answer_count: {len(answers)}", f"first_answer: {quoted(utc(sent[0]))}",
              f"last_answer: {quoted(utc(sent[-1]))}", f"fetched_at: {quoted(fetched_at)}", "processed: false",
              "---", "", f"# {title} (portal answers)", "",
              f"**Project:** {project or '-'}",
              "**Rounds:** " + "; ".join(f"{r['label']} (published {r['published']})" for r in rounds),
              f"**Answers:** {len(answers)}",
              f"**Fetched:** {fetched_at}", "", "## Answers"]
    for a in answers:
        q, name = a["question"], one_line(a["person"]["name"])
        lines += ["", f"### {one_line(q['id'])} — {name} — {utc(a['sent_at'])}", "",
                  f"**Round:** {one_line(a['round']['label'])} (published {utc(a['round']['published_at'])})",
                  f"**From:** {name} <{one_line(a['person']['email'])}>",
                  f"**Answer id:** {a['id']}",
                  f"**Question:** {one_line(q['title'])}",
                  f"**Option:** {option_text(a['option'])}",
                  "**Note:**" + ("" if a["note"] else " none")]
        if a["note"]:
            lines += note_block(a["note"])
        rep = a.get("replaces")
        if rep:
            lines += ["", f"Replaces the answer sent {utc(rep['sent_at'])} by {one_line(rep['person_name'])}:",
                      f"- Earlier answer id: {rep['id']}",
                      f"- Earlier option: {option_text(rep['option'])}",
                      "- Earlier note:" + ("" if rep["note"] else " none")]
            if rep["note"]:
                lines += note_block(rep["note"])
    return "\n".join(lines) + "\n"


def by_page(answers: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group by page slug, keeping the Portal's order (pages and Answers)."""
    groups: dict[str, list[dict]] = {}
    for a in answers:
        groups.setdefault(a["page"]["slug"], []).append(a)
    return list(groups.items())


# ---------------------------------------------------------------- the updates file

def resolutions(updates: list[dict]) -> list[dict]:
    """The Client's saves in the shape of the BA page's `resolutions` store (map/template.html saveUpdate), one entry
    per item key in the order the items were first saved. `resolved` comes from the item's latest save; notes stay
    oldest first, as the BA page stores them, each with `by`, the person who saved it. `at` is the save time (UTC);
    `updatedAt` the latest save, which sync.py uses as the closing date of an item resolved with no note."""
    entries: dict[str, dict] = {}
    for u in sorted(updates, key=lambda u: (u["sent_at"], u["id"])):
        it = u["item"]
        e = entries.setdefault(it["key"], {"key": it["key"], "kind": it["kind"], "title": it["title"],
                                           "resolved": False, "notes": [], "updatedAt": u["sent_at"]})
        e.update(kind=it["kind"], title=it["title"], resolved=bool(u["resolved"]), updatedAt=u["sent_at"])
        if u["note"]:
            e["notes"].append({"at": u["sent_at"], "text": u["note"], "by": u["person"]["name"]})
    return list(entries.values())


def name_slug(s: str) -> str:
    """A product (or project) name as a file-name part: 'Bond Portal' → 'bond-portal'."""
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60].strip("-")


def updates_tmp_path(root: Path, batch_id: str, label: str) -> Path:
    return root / UPDATES / f"portal-{batch_id}-{label}.json.tmp"


def updates_final_name(root: Path, label: str, fetched: dt.datetime) -> Path:
    base = f"{fetched.strftime('%Y-%m-%d-%H%M')}-{label}"
    folder = root / UPDATES
    target, n = folder / f"{base}.json", 1
    while target.exists():
        n += 1
        target = folder / f"{base}-{n}.json"
    return target


def is_updates(path: Path) -> bool:
    return path.name.endswith(".json.tmp") or path.suffix == ".json"


def tmp_path(root: Path, batch_id: str, slug: str) -> Path:
    return root / INTAKE / f"portal-{batch_id}-{slug}.md.tmp"


def fetched_of(path: Path) -> dt.datetime:
    """The fetch time from a .tmp file's header (fetched_at), so a leftover renames to when it was fetched."""
    try:
        text = path.read_text(encoding="utf-8")
        m = re.search(r"^fetched_at: '(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2}) UTC'$", text, flags=re.M)
        if m:
            return dt.datetime.strptime(f"{m[1]} {m[2]}{m[3]}", "%Y-%m-%d %H%M").replace(tzinfo=dt.timezone.utc)
    except (OSError, UnicodeDecodeError):
        pass
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)


def final_name(root: Path, slug: str, fetched: dt.datetime) -> Path:
    base = f"{fetched.strftime('%Y-%m-%d-%H%M')}-portal-{slug}"
    folder = root / INTAKE
    target, n = folder / f"{base}.md", 1
    while target.exists():
        n += 1
        target = folder / f"{base}-{n}.md"
    return target


def rename_all(root: Path, tmps: list[tuple[Path, str]]) -> list[Path]:
    """Give each .tmp file its real name. An updates file is renamed in docs/BA/portal-updates/ (its slug is the
    product), an intake file in docs/BA/intake/."""
    done = []
    for tmp, slug in tmps:
        name = updates_final_name if is_updates(tmp) else final_name
        target = name(root, slug, fetched_of(tmp))
        tmp.rename(target)
        if tmp in update_counts:
            update_counts[target] = update_counts.pop(tmp)
        done.append(target)
    return done


def done_marker(root: Path, batch_id: str) -> Path:
    """Written only after every file of the batch is on disk: only a marked batch is ever acked. It holds the
    number of files, then the .env variable whose key reserved the batch, so a leftover is acked in its own
    Portal project, then (since answers/2) the number of the Client's updates in the batch."""
    return root / INTAKE / f"portal-{batch_id}.complete"


def marker_updates(marker: Path) -> int | None:
    """The number of updates a marker names (its third line); None for an older marker or none written."""
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    n = lines[2].strip() if len(lines) > 2 else ""
    return int(n) if n.isdigit() else None


def marker_key(marker: Path) -> str | None:
    """The .env variable a marker names (its second line); None for a marker written before Story 4.10."""
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    name = lines[1].strip() if len(lines) > 1 else ""
    return name if KEY_NAME.fullmatch(name) else None


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ---------------------------------------------------------------- the run

def leftovers(root: Path) -> tuple[dict[str, list[tuple[Path, str]]], list[Path]]:
    """Leftover .tmp files by batch (a marker alone counts too) — intake files and updates files — and
    portal-*.md.tmp / portal-*.json.tmp files with a name not ours."""
    folder = root / INTAKE
    batches: dict[str, list[tuple[Path, str]]] = {}
    strays: list[Path] = []
    for where, pattern, name in ((folder, "portal-*.md.tmp", TMP_NAME),
                                 (root / UPDATES, "portal-*.json.tmp", UPD_TMP_NAME)):
        if not where.is_dir():
            continue
        for p in sorted(where.glob(pattern)):
            m = name.match(p.name)
            if m:
                batches.setdefault(m[1].lower(), []).append((p, m[2]))
            else:
                strays.append(p)
    if folder.is_dir():
        for p in sorted(folder.glob("portal-*.complete")):
            m = DONE_NAME.match(p.name)
            if m:
                batches.setdefault(m[1].lower(), [])
    return batches, strays


def drop(paths) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def finish_leftovers(root: Path, url: str, key: str, first: bool = True, known: tuple[str, ...] = (),
                     old_key: tuple[str, str] | None = None) -> tuple[list[Path], list[str]]:
    """Ack each leftover batch of this key first. Returns the files renamed and plain notes for the BA.
    A batch is this key's when its marker names this key's .env variable (key_name). A marker that names none (an
    older one) belongs to PORTAL_PUBLISH_KEY: `old_key` is (that variable, its key) when .env still has it, else
    None and such a batch is left alone. `first`: this is the first product's run, which also deletes cut-off
    batches, acks old batches whose variable is not a product's, and reports strays and batches it cannot ack
    (`known` are the variables the profile names)."""
    global key_name
    written, notes = [], []
    batches, strays = leftovers(root)
    mine: dict[str, tuple[list, str, str]] = {}          # batch id -> (its .tmp files, the key, its variable)
    for batch_id, tmps in batches.items():
        marker = done_marker(root, batch_id)
        if not marker.exists():
            if first:
                mine[batch_id] = (tmps, key, key_name)
            continue
        owner = marker_key(marker)
        if owner is None:                                # written before Story 4.10
            if old_key is None:
                if first and tmps:
                    notes.append(f"{len(tmps)} file(s) from an earlier fetch wait in {INTAKE}/ as .tmp. Their "
                                 f"marker is from an older fetch-portal and names no key, and .env has no "
                                 f"{DEFAULT_KEY}, so it is not clear which Portal project they came from. They are "
                                 f"left alone. Put {DEFAULT_KEY} back in .env to finish them, or delete them.")
                continue
            owner = old_key[0]
        if owner == key_name:
            mine[batch_id] = (tmps, key, key_name)
        elif first and old_key and owner == old_key[0] and owner not in known:
            mine[batch_id] = (tmps, old_key[1], old_key[0])
        elif owner not in known and first and tmps:
            notes.append(f"{len(tmps)} file(s) from an earlier fetch wait in {INTAKE}/ as .tmp. They were fetched "
                         f"with the key in {owner}, which tools.portal.products no longer names, so they are left "
                         "alone. Put that key back in the profile to finish them, or delete them.")
    if strays and first:
        notes.append("These files in " + (INTAKE if all(p.parent == root / INTAKE for p in strays) else
                                          f"{INTAKE}/ and {UPDATES}") + "/ look like unfinished fetch-portal files, "
                     "but fetch-portal does not write names like these, so it leaves them alone. Delete them if you "
                     "do not need them: " + ", ".join(rel(root, p) for p in strays))
    mine_name = key_name
    try:
        for batch_id, (tmps, batch_key, batch_var) in mine.items():
            marker = done_marker(root, batch_id)
            if not marker.exists():
                drop(p for p, _ in tmps)
                notes.append(f"Deleted {len(tmps)} file(s) from an earlier fetch that was cut off while writing. "
                             f"The Portal was never told it had them, so those Answers come again after the hold "
                             f"({HOLD}).")
                continue
            if not tmps:
                drop([marker])
                continue
            for p, _ in tmps:                            # the summary counts an updates file's saves
                if is_updates(p) and marker_updates(marker) is not None:
                    update_counts[p] = marker_updates(marker)
            key_name = batch_var                         # messages name the variable this batch is acked with
            try:
                result, _ = ack(url, batch_key, batch_id)
            except NoReply as e:
                raise Stop(f"{e} {len(tmps)} file(s) from an earlier fetch are still waiting in {INTAKE}/ as .tmp; "
                           "the next run finishes them. Nothing new was fetched.") from None
            finally:
                key_name = mine_name
            if result == "ok":
                written += rename_all(root, tmps)
                drop([marker])
                notes.append(f"Finished an earlier fetch: {len(tmps)} file(s) confirmed by the Portal.")
            else:
                drop([*(p for p, _ in tmps), marker])
                notes.append(f"Deleted {len(tmps)} unfinished file(s) from an earlier fetch: the Portal had already "
                             "given those Answers to a newer fetch, or no longer knows that batch. Those Answers "
                             "come with this fetch or the next one.")
    except Stop as e:
        if written:
            e.files = [rel(root, f) for f in written]
        raise
    return written, notes


def write_batch(root: Path, project: str, batch: dict, product: str = "", label: str = "") -> list[tuple[Path, str]]:
    """Write one .tmp file per page, and one updates .tmp file (named by `label`, the product) when the batch has
    updates. On any write error delete what this batch wrote, ack nothing."""
    fetched = now()
    written: list[tuple[Path, str]] = []
    updates = batch.get("updates") or []
    label = name_slug(label) or "portal"
    try:
        (root / INTAKE).mkdir(parents=True, exist_ok=True)
        for slug, answers in by_page(batch["answers"]):
            path = tmp_path(root, batch["batch_id"], slug)
            path.write_text(render(project, slug, answers, fetched, product), encoding="utf-8", newline="\n")
            written.append((path, slug))
        if updates:
            (root / UPDATES).mkdir(parents=True, exist_ok=True)
            path = updates_tmp_path(root, batch["batch_id"], label)
            path.write_text(json.dumps(resolutions(updates), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
            stamp = fetched.timestamp()
            os.utime(path, (stamp, stamp))                # a leftover renames to the fetch time, as intake files do
            written.append((path, label))
            update_counts[path] = len(updates)
        done_marker(root, batch["batch_id"]).write_text(
            f"{len(written)}\n{key_name}\n" + (f"{len(updates)}\n" if updates else ""), encoding="utf-8", newline="\n")
    except (OSError, ValueError) as e:
        partial = [p for p, _ in written]
        for folder, pattern in ((root / INTAKE, "*.md.tmp"), (root / UPDATES, "*.json.tmp")):
            if folder.is_dir():
                partial += folder.glob(f"portal-{batch['batch_id']}-{pattern}")
        drop([*partial, done_marker(root, batch["batch_id"])])   # a half-written file too: never ack this batch
        why = getattr(e, "strerror", None) or e
        raise Stop(f"Could not write the intake files ({why}). Nothing was written and nothing was "
                   f"confirmed: the Answers{' and updates' if updates else ''} wait in the Portal and come again "
                   f"in a fetch after {utc(batch['reserved_until'])}.") from None
    return written


def updates_line(root: Path, f: Path) -> str:
    """'  - docs/BA/portal-updates/<file>.json (N updates on M items)'. N is left out when it is not known (a file
    from an earlier fetch whose marker did not say)."""
    try:
        items = len(json.loads(f.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return f"  - {rel(root, f)}"
    n = update_counts.get(f)
    saves = f"{n} update{'' if n == 1 else 's'} on " if n is not None else ""
    return f"  - {rel(root, f)} ({saves}{items} item{'' if items == 1 else 's'})"


def summary(root: Path, files: list[Path]) -> str:
    """The intake files, then the updates files with what to do next. Only the parts that have files."""
    intake = [f for f in files if not is_updates(f)]
    upd = [f for f in files if is_updates(f)]
    lines = []
    if intake or not upd:
        lines.append(f"Wrote {len(intake)} intake file{'s' if len(intake) != 1 else ''}:")
    for f in intake:
        try:
            head = f.read_text(encoding="utf-8")
            n = re.search(r"^answer_count: (\d+)$", head, flags=re.M)
            t = re.search(r"^page_title: '(.*)'$", head, flags=re.M)
            p = re.search(r"^product: '(.*)'$", head, flags=re.M)
            product = f"{p[1].replace(chr(39) * 2, chr(39))}: " if p else ""
            extra = f" ({product}{t[1].replace(chr(39) * 2, chr(39)) if t else '?'}, {n[1] if n else '?'} answer{'' if n and n[1] == '1' else 's'})"
        except OSError:
            extra = ""
        lines.append(f"  - {rel(root, f)}{extra}")
    if upd:
        lines += [f"Wrote the Client's updates on dashboard items ({len(upd)} file{'s' if len(upd) != 1 else ''}):",
                  *(updates_line(root, f) for f in upd),
                  'To put them in docs/BA/dashboard.yaml, run "sync the mind map" with '
                  + ("this file." if len(upd) == 1 else "each file.")]
    return "\n".join(lines)


def project_name(url: str, key: str) -> str:
    """GET /status with one product's key: the name of the Portal project that key opens. Fetches nothing."""
    try:
        with http_client() as client:
            r = client.get(url + STATUS, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    except httpx.InvalidURL:
        raise Stop(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it. "
                   "Nothing was written.") from None
    except httpx.RequestError:
        raise Stop(f"The Portal is not reachable at {url}. Check that it is running and that tools.portal.url is "
                   "right. Nothing was written.") from None
    try:
        doc = r.json()
    except ValueError:
        doc = None
    if r.status_code == 200 and isinstance(doc, dict) and not checks.check_reply(doc, "status/1"):
        return doc["project_name"]
    if r.status_code == 200:
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                   "Nothing was written.")
    raise refused(url, r, doc, "status check")


def intake_md(root: Path) -> set[str]:
    folder = root / INTAKE
    return {rel(root, f) for f in folder.glob("*.md")} if folder.is_dir() else set()


def plain_error(e: Exception, wrote: bool) -> str:
    """An unexpected error in one product's run, in plain words. "Nothing was written" only when it is true."""
    if isinstance(e, UnicodeDecodeError):
        why = f"A file is not UTF-8 text ({e.reason})."
    elif isinstance(e, OSError):
        why = (f"A file could not be read or written: {e}. Check {INTAKE}/ for .tmp files; the next run finishes "
               "them.")
    else:
        why = f"The request to the Portal failed ({type(e).__name__})."
    return why + ("" if wrote else " Nothing was written.")


def run(root: Path) -> dict:
    """Every product's Portal project, in tools.portal.products order, one key at a time. A repo with one product
    works as before. With two or more, each key's Portal project is named first (GET /status), and two keys that
    open the same project stop the run before anything is fetched. One product's failure does not stop the
    others: the result reports each product and is ok: false when any failed."""
    global key_name
    url, prof, goes, env = settings(root)
    project = str(prof.get("project") or "").strip()
    old = env.get(DEFAULT_KEY, "").strip()
    old_key = (DEFAULT_KEY, old) if old else None
    if len(goes) == 1:
        key_name = goes[0].key_name
        return run_one(root, url, goes[0].key, project, known=(key_name,), old_key=old_key,
                       label=goes[0].product or project)
    known = tuple(t.key_name for t in goes)
    names: dict[str, str] = {}                     # product -> its Portal project
    early: dict[str, str] = {}                     # product -> why its project could not be named
    owner: dict[str, str] = {}
    for t in goes:
        key_name = t.key_name
        try:
            name = project_name(url, t.key)
        except Stop as e:
            early[t.product] = str(e)
            continue
        if name in owner:
            first = next(x for x in goes if x.product == owner[name])
            raise Stop(f"The keys for {first.product} ({first.key_name}) and {t.product} ({t.key_name}) both open "
                       f"the same Portal project, \"{name}\". Each product needs its own Portal project. Ask an "
                       "Admin for the right key for one of them, put it in .env, and run fetch-portal again. "
                       "Nothing was written.")
        owner[name] = t.product
        names[t.product] = name
    files: list[str] = []
    blocks, failed, products = [], [], []
    for n, t in enumerate(goes):
        key_name = t.key_name
        got: list[str] = []
        seen = intake_md(root)
        if t.product in early:
            ok, msg = False, early[t.product]
        else:
            try:
                res = run_one(root, url, t.key, project, t.product, first=n == 0, known=known, old_key=old_key,
                              label=t.product)
                ok, got, msg = True, res["files"], res["message"]
            except Stop as e:
                ok, got, msg = False, list(e.files), str(e)
            except (OSError, UnicodeDecodeError, httpx.HTTPError) as e:
                got = sorted(intake_md(root) - seen)       # files this product renamed before the error
                ok, msg = False, plain_error(e, bool(got))
        if not ok:
            failed.append(t.product)
        files += got
        products.append({"product": t.product, "ok": ok, "files": got,
                         **({"project_name": names[t.product]} if t.product in names else {})})
        where = f"{t.product} → Portal project \"{names[t.product]}\"" if t.product in names else t.product
        head = f"{where}:" if ok else f"{where} — stopped:"
        blocks.append("\n".join([head, *("  " + ln if ln else "" for ln in msg.splitlines())]))
    message = "\n\n".join(blocks)
    if not failed:
        return {"ok": True, "files": files, "products": products, "message": message}
    message += (f"\n\nNot fetched: {', '.join(failed)}. The other products are done. Fix what stopped, then run "
                "fetch-portal again.")
    return {"ok": False, "files": files, "products": products, "error": message}


def run_one(root: Path, url: str, key: str, project: str, product: str = "", first: bool = True,
            known: tuple[str, ...] = (), old_key: tuple[str, str] | None = None, label: str = "") -> dict:
    """One Portal project: leftovers, then reserve, write and ack, with that project's key. `label`: the product
    name the updates file is named by (product is "" in a repo with one product, where intake files carry none)."""
    files, notes = finish_leftovers(root, url, key, first, known, old_key)
    try:
        return fetch_new(root, url, key, project, files, notes, product, label or product)
    except Stop as e:
        if not files and not notes:
            raise
        msg = str(e).replace("Nothing was written", "Nothing new was written")
        if files:
            msg = summary(root, files) + "\nThose came from an earlier fetch. Then the new fetch stopped: " + msg
        stop = Stop("\n".join([*notes, msg]))
        stop.files = [rel(root, f) for f in files]
        raise stop from None


def fetch_new(root: Path, url: str, key: str, project: str, files: list[Path], notes: list[str],
              product: str = "", label: str = "") -> dict:
    batch = reserve(url, key)
    if batch["batch_id"] is None:
        last = batch["last_fetched_at"]
        what = "answers or updates" if batch["contract"] == "answers/2" else "answers"
        nothing = (f"No new {what} since {utc(last)}." if last else f"No new {what}. None have been fetched yet.")
        msg = "\n".join([*notes, *([summary(root, files)] if files else []), nothing])
        return {"ok": True, "files": [rel(root, f) for f in files], "message": msg}

    tmps = write_batch(root, project, batch, product, label or project)
    try:
        result, _ = ack(url, key, batch["batch_id"])
    except NoReply as e:
        where = f"{INTAKE}/" + (f" and {UPDATES}/" if any(is_updates(p) for p, _ in tmps) else "")
        raise Stop(f"{e} The {len(tmps)} file(s) were written but the Portal has not confirmed them, so they stay in "
                   f"{where} as .tmp (triage skips them). The next fetch-portal run finishes them — run it again "
                   "soon. Do not commit the .tmp files.") from None
    marker = done_marker(root, batch["batch_id"])
    if result != "ok":
        drop([*(p for p, _ in tmps), marker])
        raise Stop("The Portal had already given these Answers to a newer fetch (batch_expired), so the files "
                   "were deleted. The Answers come in the next fetch — run fetch-portal again."
                   if result == "expired" else
                   "The Portal no longer knows this batch (batch_unknown), so the files were deleted. The Answers "
                   "come in the next fetch — run fetch-portal again.")
    files = files + rename_all(root, tmps)
    drop([marker])
    msg = "\n".join([*notes, summary(root, files)])
    return {"ok": True, "files": [rel(root, f) for f in files], "message": msg}


def main(argv: list[str]) -> int:
    global checks
    if "--help" in argv or "-h" in argv:
        sys.stdout.reconfigure(encoding="utf-8")
        print(__doc__)
        return 0
    root = Path(arg(argv, "--root", ".")).resolve()
    try:
        if checks is None:
            checks = load_checks()
        result = run(root)
    except Stop as e:
        out({"ok": False, "files": e.files, "error": str(e)})
        return 1
    except yaml.YAMLError as e:
        out({"ok": False, "files": [], "error": f"{PROFILE} could not be read: {e}. Fix it, then run again. "
                                                "Nothing was written."})
        return 1
    except UnicodeDecodeError as e:
        out({"ok": False, "files": [], "error": f"A file is not UTF-8 text ({e.reason}). Nothing was written."})
        return 1
    except OSError as e:
        out({"ok": False, "files": [], "error": f"A file could not be read or written: {e}. Check {INTAKE}/ for "
                                                ".tmp files; the next run finishes them."})
        return 1
    except httpx.HTTPError as e:
        out({"ok": False, "files": [], "error": f"The request to the Portal failed ({type(e).__name__}). "
                                                "Nothing was written."})
        return 1
    out(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
