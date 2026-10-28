"""fetch-portal — bring the Client's Answers from the Relevant Clients Portal into docs/BA/intake/. Prints one JSON line.

    uv run --project <skills>/fetch-portal python <skills>/fetch-portal/fetch.py [--root <project>]

Run from the project root, or pass --root. What it does, in order:
  1. Leftover .tmp files from an earlier run (docs/BA/intake/portal-<batch_id>-<slug>.md.tmp): ack that batch.
     200 → rename to the real name; batch_expired or batch_unknown → delete; no reply → keep them and stop.
  2. Reserve a batch: POST /api/v1/answers/reserve. Nothing new → say so, write nothing.
  3. Write one file per Clarification page under a .tmp name, then a marker portal-<batch_id>.complete once every
     page is on disk, then ack: POST /api/v1/answers/ack (3 tries). A leftover batch with no marker was cut off
     mid-write: its .tmp files are deleted, never acked, and its Answers come again after the hold.
  4. On 200, rename each to docs/BA/intake/YYYY-MM-DD-HHMM-portal-<slug>.md (-2, -3 … if taken).

Settings: tools.portal.url in docs/BA/specs/.ba-profile.yml; the Publish key in .env at the repo root, which git
must ignore: PORTAL_PUBLISH_KEY, or, when the profile has tools.portal.products (one Portal project per product), the
first product's variable there. The key is never printed. Every reply is checked against the portal-publish
contract (answers/1, ack/1); a reply that fails stops the run: nothing written, no ack.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent
CHECKS_PY = SKILLS / "portal-publish" / "checks.py"

PROFILE = "docs/BA/specs/.ba-profile.yml"
INTAKE = "docs/BA/intake"
RESERVE = "/api/v1/answers/reserve"
ACK = "/api/v1/answers/ack"
TIMEOUT = 30.0
ACK_TRIES = 3
ACK_WAITS = (2.0, 5.0)            # seconds before the 2nd and the 3rd ack try
SETUP_HINT = "Run `ba-setup project`"
KEY_PLACE = "Admin → Projects → the Project → Publishing"
DEFAULT_KEY = "PORTAL_PUBLISH_KEY"
KEY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
key_name = DEFAULT_KEY            # the .env variable the key came from; settings() sets it, messages name it
TMP_NAME = re.compile(r"^portal-([0-9a-fA-F-]{36})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md\.tmp$")
DONE_NAME = re.compile(r"^portal-([0-9a-fA-F-]{36})\.complete$")
HOLD = "about 10 minutes"


class Stop(Exception):
    """Stop the run. The message is shown to the BA as it is. `files`: intake files already written this run."""

    files: list[str] = []


class NoReply(Stop):
    """The Portal did not answer (connect error, timeout, or a 5xx on every ack try)."""


def load_checks():
    """portal-publish's checks.py, imported from the sibling folder: one contract, never a copy."""
    if not CHECKS_PY.exists():
        raise Stop(f"fetch-portal needs the portal-publish skill next to it ({CHECKS_PY} is missing). "
                   "Install ba-tools again. Nothing was written.")
    spec = importlib.util.spec_from_file_location("portal_publish_checks", CHECKS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


checks = None   # loaded in main(), so a missing portal-publish gives a plain stop message


# ---------------------------------------------------------------- output and arguments

def out(obj: dict) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))


def arg(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


# ---------------------------------------------------------------- settings (copied from portal-publish/publish.py)

def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[name] = value
    return values


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True)
    except FileNotFoundError:
        raise Stop("git is not installed (or not on PATH). fetch-portal needs git. Nothing was written.") from None


def env_is_ignored(root: Path) -> bool:
    r = run_git(root, "check-ignore", "-q", ".env")
    if r.returncode == 128:
        raise Stop(f"{root} is not a git repository, so git cannot keep .env out of commits. Run fetch-portal "
                   "from the project repo. Nothing was written.")
    return r.returncode == 0


LOCAL_HOSTS = ("localhost", "127.0.0.1")


def check_url(url: str) -> None:
    """The key travels in the request: plain http:// only to this computer or a .localhost / .test name."""
    try:
        u = httpx.URL(url)
    except httpx.InvalidURL:
        raise Stop(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it.") from None
    host = (u.host or "").lower()
    if u.scheme == "https" and host:
        return
    if u.scheme == "http" and (host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".test")):
        return
    raise Stop(f"tools.portal.url ({url}) must start with https:// — plain http:// would send the Publish key "
               "unencrypted. http:// is allowed only for localhost, 127.0.0.1, *.localhost and *.test. "
               "Nothing was written.")


def settings(root: Path) -> tuple[str, str, dict]:
    """The Portal address, the key and the profile. Stops before anything is asked of the Portal."""
    prof_path = root / PROFILE
    if not prof_path.exists():
        raise Stop(f"No project profile at {PROFILE}. {SETUP_HINT} first.")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    tools = (prof.get("tools") or {}) if isinstance(prof, dict) else None
    if not isinstance(tools, dict):
        raise Stop(f"{PROFILE} is not laid out as a project profile (it, or its tools: part, is not a set of "
                   f"named settings). {SETUP_HINT} to fix it. Nothing was written.")
    portal = tools.get("portal") or {}
    url = str(portal.get("url") or "").strip().rstrip("/") if isinstance(portal, dict) else ""
    if not url:
        raise Stop(f"The profile has no Portal address (tools.portal.url in {PROFILE}). {SETUP_HINT} to add it.")
    check_url(url)
    env = root / ".env"
    if not env.exists():
        raise Stop(f"There is no .env file at the repo root, so there is no Publish key. {SETUP_HINT}: it puts "
                   "the Publish key in .env.")
    if not env_is_ignored(root):
        raise Stop(".env is not ignored by git (it is tracked, or .gitignore does not list it). The Publish key "
                   "must never be committed: add .env to .gitignore (and `git rm --cached .env` if it was "
                   "committed), then run again. Nothing was written.")
    global key_name
    key_name = first_product_key(portal)
    key = read_env_file(env).get(key_name, "").strip()
    if not key:
        raise Stop(f".env has no {key_name}. {SETUP_HINT}: it tells you where to get the key.")
    return url, key, prof


def first_product_key(portal: dict) -> str:
    """The .env variable to use. With tools.portal.products (a key per product, portal-publish Story 3.8), the
    first product's variable, until Answers are fetched per product (Story 4.10); else PORTAL_PUBLISH_KEY."""
    found = portal.get("products") if isinstance(portal, dict) else None
    if found in (None, "", {}):
        return DEFAULT_KEY
    names = list(found.values()) if isinstance(found, dict) else []
    if not names or not all(isinstance(v, str) and KEY_NAME.fullmatch(v.strip()) for v in names):
        raise Stop(f"tools.portal.products in {PROFILE} must name, for each product, the .env variable that holds "
                   "its Portal project's key, for example {AcmeLending: PORTAL_PUBLISH_KEY_ACME}. "
                   f"{SETUP_HINT} to fix it. Nothing was written.")
    return names[0].strip()


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
    tail = ("Nothing was written." if step == "reserve" else
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
    try:
        r, doc = call(url, key, RESERVE, None)
    except NoReply as e:
        raise Stop(f"{e} Nothing was written. If the Portal had already set Answers aside for this fetch, they "
                   f"come again after the hold ({HOLD}).") from None
    if r.status_code != 200:
        raise refused(url, r, doc, "reserve")
    if not isinstance(doc, dict) or checks.check_reply(doc, "answers/1"):
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                   "Nothing was written and nothing was confirmed.")
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


def render(project: str, slug: str, answers: list[dict], fetched: dt.datetime) -> str:
    """One page's Answers as an intake file. Answers stay in the order the Portal sent."""
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
             f"page: {quoted(slug)}", f"page_title: {quoted(title)}", "rounds:"]
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
    done = []
    for tmp, slug in tmps:
        target = final_name(root, slug, fetched_of(tmp))
        tmp.rename(target)
        done.append(target)
    return done


def done_marker(root: Path, batch_id: str) -> Path:
    """Written only after every page of the batch is on disk: only a marked batch is ever acked."""
    return root / INTAKE / f"portal-{batch_id}.complete"


def rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ---------------------------------------------------------------- the run

def leftovers(root: Path) -> tuple[dict[str, list[tuple[Path, str]]], list[Path]]:
    """Leftover .tmp files by batch (a marker alone counts too), and portal-*.md.tmp files with a name not ours."""
    folder = root / INTAKE
    batches: dict[str, list[tuple[Path, str]]] = {}
    strays: list[Path] = []
    if folder.is_dir():
        for p in sorted(folder.glob("portal-*.md.tmp")):
            m = TMP_NAME.match(p.name)
            if m:
                batches.setdefault(m[1].lower(), []).append((p, m[2]))
            else:
                strays.append(p)
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


def finish_leftovers(root: Path, url: str, key: str) -> tuple[list[Path], list[str]]:
    """Ack each leftover batch first. Returns the files renamed and plain notes for the BA."""
    written, notes = [], []
    batches, strays = leftovers(root)
    if strays:
        notes.append("These files in " + INTAKE + "/ look like unfinished fetch-portal files, but fetch-portal does "
                     "not write names like these, so it leaves them alone. Delete them if you do not need them: "
                     + ", ".join(rel(root, p) for p in strays))
    for batch_id, tmps in batches.items():
        marker = done_marker(root, batch_id)
        if not marker.exists():
            drop(p for p, _ in tmps)
            notes.append(f"Deleted {len(tmps)} file(s) from an earlier fetch that was cut off while writing. The "
                         f"Portal was never told it had them, so those Answers come again after the hold ({HOLD}).")
            continue
        if not tmps:
            drop([marker])
            continue
        try:
            result, _ = ack(url, key, batch_id)
        except NoReply as e:
            raise Stop(f"{e} {len(tmps)} file(s) from an earlier fetch are still waiting in {INTAKE}/ as .tmp; the "
                       "next run finishes them. Nothing new was fetched.") from None
        if result == "ok":
            written += rename_all(root, tmps)
            drop([marker])
            notes.append(f"Finished an earlier fetch: {len(tmps)} file(s) confirmed by the Portal.")
        else:
            drop([*(p for p, _ in tmps), marker])
            notes.append(f"Deleted {len(tmps)} unfinished file(s) from an earlier fetch: the Portal had already "
                         "given those Answers to a newer fetch, or no longer knows that batch. Those Answers come "
                         "with this fetch or the next one.")
    return written, notes


def write_batch(root: Path, project: str, batch: dict) -> list[tuple[Path, str]]:
    """Write one .tmp file per page. On any write error delete what this batch wrote, ack nothing."""
    fetched = now()
    written: list[tuple[Path, str]] = []
    try:
        (root / INTAKE).mkdir(parents=True, exist_ok=True)
        for slug, answers in by_page(batch["answers"]):
            path = tmp_path(root, batch["batch_id"], slug)
            path.write_text(render(project, slug, answers, fetched), encoding="utf-8", newline="\n")
            written.append((path, slug))
        done_marker(root, batch["batch_id"]).write_text(f"{len(written)}\n", encoding="utf-8")
    except (OSError, ValueError) as e:
        folder = root / INTAKE
        partial = [p for p, _ in written] + (list(folder.glob(f"portal-{batch['batch_id']}-*.md.tmp"))
                                             if folder.is_dir() else [])
        drop([*partial, done_marker(root, batch["batch_id"])])   # a half-written file too: never ack this batch
        why = getattr(e, "strerror", None) or e
        raise Stop(f"Could not write the intake files ({why}). Nothing was written and nothing was "
                   f"confirmed: the Answers wait in the Portal and come again in a fetch after "
                   f"{utc(batch['reserved_until'])}.") from None
    return written


def summary(root: Path, files: list[Path]) -> str:
    lines = [f"Wrote {len(files)} intake file{'s' if len(files) != 1 else ''}:"]
    for f in files:
        try:
            head = f.read_text(encoding="utf-8")
            n = re.search(r"^answer_count: (\d+)$", head, flags=re.M)
            t = re.search(r"^page_title: '(.*)'$", head, flags=re.M)
            extra = f" ({t[1].replace(chr(39) * 2, chr(39)) if t else '?'}, {n[1] if n else '?'} answer{'' if n and n[1] == '1' else 's'})"
        except OSError:
            extra = ""
        lines.append(f"  - {rel(root, f)}{extra}")
    return "\n".join(lines)


def run(root: Path) -> dict:
    url, key, prof = settings(root)
    project = str(prof.get("project") or "").strip()
    files, notes = finish_leftovers(root, url, key)
    try:
        return fetch_new(root, url, key, project, files, notes)
    except Stop as e:
        if not files and not notes:
            raise
        msg = str(e).replace("Nothing was written", "Nothing new was written")
        if files:
            msg = summary(root, files) + "\nThose came from an earlier fetch. Then the new fetch stopped: " + msg
        stop = Stop("\n".join([*notes, msg]))
        stop.files = [rel(root, f) for f in files]
        raise stop from None


def fetch_new(root: Path, url: str, key: str, project: str, files: list[Path], notes: list[str]) -> dict:
    batch = reserve(url, key)
    if batch["batch_id"] is None:
        last = batch["last_fetched_at"]
        nothing = (f"No new answers since {utc(last)}." if last else "No new answers. None have been fetched yet.")
        msg = "\n".join([*notes, *([summary(root, files)] if files else []), nothing])
        return {"ok": True, "files": [rel(root, f) for f in files], "message": msg}

    tmps = write_batch(root, project, batch)
    try:
        result, _ = ack(url, key, batch["batch_id"])
    except NoReply as e:
        raise Stop(f"{e} The {len(tmps)} file(s) were written but the Portal has not confirmed them, so they stay in "
                   f"{INTAKE}/ as .tmp (triage skips them). The next fetch-portal run finishes them — run it again "
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
