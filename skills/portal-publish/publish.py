"""portal-publish — send the project's Dashboard, or one Clarification page, to the Relevant Clients Portal.
Every command prints one JSON line.

    uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py <command> [--root <project>]

Commands (run from the project root, or pass --root):
  dashboard plan [--refresh]          build the dashboard, make the payload, check it against the contract, send it
                                      to the Portal as a dry run and print what the Client will read (client_list).
                                      Writes the payload to a temp file outside the repo and prints its path.
  dashboard send --payload <file>     after the BA says yes: send that same payload for real, report, delete the file
  dashboard discard --payload <file>  after the BA says no: delete the payload file, send nothing
  page plan <slug>                    find docs/BA/clarifications/<slug>-decisions.yaml (else <slug>.yaml), run
                                      clarification-page's _fixyaml.py on it, build the clarification/1 page (only
                                      the contract's fields; old `settled:` lines become decisions), collect its
                                      screenshots (bare, unique file names), check everything, send it as a
                                      multipart dry run and print what the Client will read (client_view).
                                      Writes the page JSON plus each screenshot's path and SHA-256 to a temp file.
                                      `page <slug>` does the same.
  page send --payload <file>          after the BA says yes: re-read the screenshots (stop if one changed), send the
                                      same page for real, report, delete the file
  page discard --payload <file>       after the BA says no: delete the payload file, send nothing

Settings: tools.portal.url in docs/BA/specs/.ba-profile.yml; PORTAL_PUBLISH_KEY in .env at the repo root, which git
must ignore. The key is never printed. The "Waiting on you" list and the page's Client view come only from the
Portal's dry-run reply.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import httpx
import yaml

import checks

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent
DASHBOARD_PY = SKILLS / "ba-dashboard" / "scripts" / "dashboard.py"
MAP_BUILD_PY = SKILLS / "ba-dashboard" / "map" / "build.py"
SETUP_PY = SKILLS / "ba-setup" / "scripts" / "setup.py"

PROFILE = "docs/BA/specs/.ba-profile.yml"
DASHBOARD = "docs/BA/dashboard.yaml"
SLACK = "docs/BA/dashboard-slack.yaml"
MAP_PAGE = "docs/BA/mind-map/mind-map.html"
JIRA_FILES = ("tickets.json", "areas.json", "releases.json")
ENDPOINT = "/api/v1/publish/dashboard"
CONTRACT = "dashboard/1"
REPLY = "publish-reply/1"
MAX_BYTES = 2 * 1024 * 1024      # the Portal refuses a Dashboard over 2 MB (DASHBOARD_MAX_BYTES, payload_too_large)
STALE_SECONDS = 24 * 3600
TIMEOUT = 30.0
BUILD_TIMEOUT = 600                # seconds for each build step
PAYLOAD_GLOB = "portal-publish-*.json"
PAYLOAD_MAX_AGE = 24 * 3600
SETUP_HINT = "Run `ba-setup project`"
STAGE_NAME = {"concept": "Concept", "spec": "Spec & design", "ready": "Ready for dev", "dev": "In dev",
              "qa": "In QA", "done": "Done"}

# What to do next, per Portal error code. The Portal's own message is shown first.
NEXT_STEP = {
    "invalid_key": "The key in .env (PORTAL_PUBLISH_KEY) is not this Project's key. Ask an Admin for the key "
                   "(Admin → Projects → the Project → Publishing → Regenerate key), put it in .env, and run again.",
    "project_archived": "This Project is archived in the Portal, so it takes no sends. Ask an Admin to restore it.",
    "contract_invalid": "Fix each field listed, then run `dashboard plan` again.",
    "contract_version_not_accepted": "This Portal does not accept the contract this ba-tools version sends. "
                                     "Update ba-tools, or ask an Admin to update the Portal.",
    "payload_too_large": "The Dashboard is too big to send. Remove or shorten features or items, then run again.",
    "bad_request": "The Portal could not read the send. Run `dashboard plan` again; if it repeats, report it.",
    "server_error": "Something went wrong in the Portal. Nothing was stored. Try again later.",
}


class Stop(Exception):
    """Stop the run: nothing (more) is sent. The message is shown to the BA as it is."""


class MaybeSent(Stop):
    """The real send went out but no reply came back: it may have arrived. The payload file is kept."""


# ---------------------------------------------------------------- output and arguments

def out(obj: dict) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))


def arg(argv: list[str], name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


# ---------------------------------------------------------------- settings

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
        raise Stop("git is not installed (or not on PATH). portal-publish needs git. Nothing was sent.") from None


def env_is_ignored(root: Path) -> bool:
    r = run_git(root, "check-ignore", "-q", ".env")
    if r.returncode == 128:
        raise Stop(f"{root} is not a git repository, so git cannot keep .env out of commits. Run portal-publish "
                   "from the project repo. Nothing was sent.")
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
               "Nothing was sent.")


def settings(root: Path) -> tuple[str, str, dict]:
    """The Portal address, the key and the profile. Stops before anything is built or sent."""
    prof_path = root / PROFILE
    if not prof_path.exists():
        raise Stop(f"No project profile at {PROFILE}. {SETUP_HINT} first.")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    portal = (prof.get("tools") or {}).get("portal") or {}
    url = str(portal.get("url") or "").strip().rstrip("/") if isinstance(portal, dict) else ""
    if not url:
        raise Stop(f"The profile has no Portal address (tools.portal.url in {PROFILE}). {SETUP_HINT} to add it.")
    check_url(url)
    env = root / ".env"
    if not env.exists():
        raise Stop(f"There is no .env file at the repo root, so there is no Publish key. {SETUP_HINT}: it puts "
                   "PORTAL_PUBLISH_KEY in .env.")
    if not env_is_ignored(root):
        raise Stop(".env is not ignored by git (it is tracked, or .gitignore does not list it). The Publish key "
                   "must never be committed: add .env to .gitignore (and `git rm --cached .env` if it was "
                   "committed), then run again. Nothing was sent.")
    key = read_env_file(env).get("PORTAL_PUBLISH_KEY", "").strip()
    if not key:
        raise Stop(f".env has no PORTAL_PUBLISH_KEY. {SETUP_HINT}: it tells you where to get the key.")
    return url, key, prof


# ---------------------------------------------------------------- build

def run_build(root: Path, refresh: bool) -> None:
    """dashboard.py build, then map/build.py. Both write into the project's docs/BA folder."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    steps = [("dashboard.py build", [sys.executable, str(DASHBOARD_PY), "build", "--root", str(root)]),
             ("map/build.py", [sys.executable, str(MAP_BUILD_PY), "--root", str(root)]
              + (["--refresh"] if refresh else []))]
    for name, cmd in steps:
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, env=env, timeout=BUILD_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Stop(f"{name} did not finish in {BUILD_TIMEOUT // 60} minutes, so it was stopped. "
                       "Nothing was sent.") from None
        text = (r.stdout or b"").decode("utf-8", "replace").strip()
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        result = None
        for line in reversed(text.splitlines()):
            try:
                result = json.loads(line)
                break
            except ValueError:
                continue
        if r.returncode != 0 or not isinstance(result, dict) or result.get("ok") is not True:
            why = (result or {}).get("error") if isinstance(result, dict) else None
            why = why or (err.splitlines()[-1] if err else text or f"exit code {r.returncode}")
            raise Stop(f"{name} failed: {why}. Fix it, then run `dashboard plan` again. Nothing was sent.")


def stale_warning(root: Path, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    ages = [now - (root / "docs/BA/mind-map" / f).stat().st_mtime
            for f in JIRA_FILES if (root / "docs/BA/mind-map" / f).exists()]
    if not ages or max(ages) <= STALE_SECONDS:
        return None
    hours = int(max(ages) // 3600)
    age = f"{hours // 24} days" if hours >= 48 else f"{hours} hours"
    return (f"The Jira files in docs/BA/mind-map/ are {age} old, so stages, areas and releases may be out of date. "
            "To re-read Jira first, run `dashboard plan --refresh`.")


def read_map(root: Path) -> dict:
    page = root / MAP_PAGE
    if not page.exists():
        raise Stop(f"{MAP_PAGE} was not built. Run `dashboard plan` again. Nothing was sent.")
    text = page.read_text(encoding="utf-8")
    at = text.find("const DATA = ")
    if at < 0:
        raise Stop(f"{MAP_PAGE} holds no map data. Nothing was sent.")
    try:
        data, _ = json.JSONDecoder().raw_decode(text, at + len("const DATA = "))
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise Stop(f"{MAP_PAGE} holds no map data. Nothing was sent.")
    return data


# ---------------------------------------------------------------- payload

def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def item_key(kind: str, title: str) -> str:
    """The map's Item key (ba-dashboard map/build.py item_key): sha1("<kind>|<title>"), first 12 characters."""
    return hashlib.sha1(f"{kind}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


def text(v) -> str:
    return "" if v is None else str(v).strip()


def put(obj: dict, field: str, value) -> None:
    """Add a field only when it has a value: empty strings and empty lists are left out."""
    if isinstance(value, list):
        if value:
            obj[field] = value
    elif value != "":
        obj[field] = value


def hidden_flag(entry: dict) -> bool:
    """client: false hides a Feature or Item — the quoted string "false" too."""
    v = entry.get("client")
    return v is False or (isinstance(v, str) and v.strip().lower() == "false")


def git(root: Path, *args: str) -> str:
    r = run_git(root, *args)
    return (r.stdout or b"").decode("utf-8", "replace").strip() if r.returncode == 0 else ""


def ba_tools_version(prof: dict) -> str:
    v = text(prof.get("ba_tools_version"))
    if v:
        return v
    spec = importlib.util.spec_from_file_location("ba_setup", SETUP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return text(mod.tools_version())


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"


def contacts(root: Path, prof: dict) -> tuple[list[dict], str, str | None]:
    """The Client contacts, where they came from, and a warning when there are none."""
    listed = (prof.get("tools") or {}).get("client_contacts")
    if listed and not isinstance(listed, list):
        raise Stop(f"tools.client_contacts in {PROFILE} must be a list, one {{name, email, slack}} per person. "
                   "Nothing was sent.")
    if listed:
        out_list = []
        for c in listed:
            c = c if isinstance(c, dict) else {"name": c}
            entry: dict = {}
            for f in ("name", "email", "slack"):
                put(entry, f, text(c.get(f)))
            out_list.append(entry)
        return out_list, "profile", None
    slack = root / SLACK
    if slack.exists():
        owners = (yaml.safe_load(slack.read_text(encoding="utf-8")) or {}).get("client_owners") or []
        owners = owners if isinstance(owners, list) else [owners]
        names = [text(o) for o in owners if text(o)]
        if names:
            return [{"name": n} for n in names], "slack", None
    return [], "none", ("No Client contacts: the profile has no tools.client_contacts and docs/BA/dashboard-slack.yaml "
                        "has no client_owners. Nothing will show under \"Waiting on you\" for the Client. "
                        "Ask the BA whether to go on without them.")


RELEASE_NAME_MAX = 100   # dashboard/1: release_rows[].name and features[].releases[]


def release_name(name: str) -> str:
    """A Jira release name as sent: one over RELEASE_NAME_MAX is cut to that length, ending in "…". Rows and each
    Feature's releases go through this one function, so they still match."""
    return name if len(name) <= RELEASE_NAME_MAX else name[:RELEASE_NAME_MAX - 1] + "…"


def map_facts(data: dict) -> tuple[dict, list[str], list[dict], dict]:
    """From the built map: each Feature bubble's stage, done date and area; the areas and release rows in order;
    each Feature's releases. Two products are merged by name, first one first. Long release names are cut
    (`release_name`)."""
    bubbles, areas = {}, []
    for epic in data.get("epics") or []:
        if epic.get("loose"):
            continue                              # "Not linked yet" — loose items, not an area
        for b in epic.get("features") or []:
            if "feature" in b:                    # a feature row (topics and loose items have none)
                bubbles[b["id"]] = {"stage": b.get("stageKey"), "done_date": text(b.get("doneDate"))[:10],
                                    "map_area": epic.get("label")}
        if not epic.get("noarea") and epic.get("label") not in areas:
            areas.append(epic["label"])
    rows, seen = [], set()
    board = data.get("board") or {}
    for product_rows in (board.get("releases") or {}).values():
        for r in product_rows:
            name = release_name(r["name"])
            if name not in seen:
                seen.add(name)
                rows.append({"name": name, "released": bool(r.get("released"))})
    order = {r["name"]: i for i, r in enumerate(rows)}
    releases: dict[str, list[str]] = {}
    for card in board.get("cards") or []:
        if card.get("kind") == "feature" and card.get("row") and card["row"] != "none":
            got = releases.setdefault(card["fid"], [])
            if release_name(card["row"]) not in got:
                got.append(release_name(card["row"]))
    for fid in releases:
        releases[fid].sort(key=lambda n: order.get(n, len(order)))
    return bubbles, areas, rows, releases


def build_payload(root: Path, prof: dict, sent_at: str | None = None):
    """The dashboard/1 payload (data-contract §10), where each sent value came from, counts of what was left out,
    and warnings."""
    d = yaml.safe_load((root / DASHBOARD).read_text(encoding="utf-8")) or {}
    bubbles, areas, rows, releases = map_facts(read_map(root))
    warnings: list[str] = []
    cut = [r["name"] for r in rows if r["name"].endswith("…") and len(r["name"]) == RELEASE_NAME_MAX]
    if cut:
        warnings.append(f"{len(cut)} Jira release name(s) are longer than {RELEASE_NAME_MAX} characters, so the "
                        "Client sees them cut, ending in \"…\": " + "; ".join(f"'{n}'" for n in cut)
                        + ". Shorten them in Jira to show them whole.")
    sources: dict[str, tuple[str, str, dict]] = {}   # "/features/0" -> (file, row label, {field: source field})
    left_out = {"features": 0, "items": 0}

    features, hidden = [], set()
    for f in d.get("features") or []:
        fid = text(f.get("id")) or slug(text(f.get("area")))
        if hidden_flag(f):
            hidden.add(fid)
            left_out["features"] += 1
            continue
        b = bubbles.get(fid)
        if b is None:
            raise Stop(f"{MAP_PAGE} has no bubble for the feature '{text(f.get('area'))}' (id {fid}). "
                       "Run `dashboard plan` again. Nothing was sent.")
        summary_from = "client_s" if text(f.get("client_s")) else "s"
        feat: dict = {"id": fid}
        put(feat, "title", text(f.get("area")))
        put(feat, "short", text(f.get("short")))
        put(feat, "summary", text(f.get(summary_from)))
        opens = f.get("open") or []
        opens = opens if isinstance(opens, list) else [opens]
        put(feat, "open", [text(o) for o in opens if text(o)])
        clar = f.get("clar")
        put(feat, "clar_url", text(clar.get("url") if isinstance(clar, dict) else clar))
        put(feat, "stage", text(b["stage"]))
        if b["map_area"]:
            feat["map_area"] = b["map_area"]
        put(feat, "releases", releases.get(fid, []))
        put(feat, "done_date", b["done_date"])
        if feat.get("map_area") == "No area" and "No area" not in areas:
            areas.append("No area")
        sources[f"/features/{len(features)}"] = (DASHBOARD, f"features '{text(f.get('area')) or fid}'", {
            "id": "id", "title": "area", "short": "short", "summary": summary_from, "open": "open",
            "clar_url": "clar.url", "stage": f"stage (from the map build, {MAP_PAGE})",
            "map_area": f"area (from the map build, {MAP_PAGE})",
            "releases": f"releases (from the map build, {MAP_PAGE})",
            "done_date": f"done date (from the map build, {MAP_PAGE})"})
        features.append(feat)

    items = []
    for listname, kind in (("awaiting", "waiting"), ("agenda", "agenda")):
        for it in d.get(listname) or []:
            if it.get("done") or hidden_flag(it) or text(it.get("feature")) in hidden:
                left_out["items"] += 1
                continue
            text_from = "client_s" if text(it.get("client_s")) else "s"
            title = text(it.get("t"))
            item: dict = {"key": item_key(kind, title), "kind": kind}
            put(item, "feature", text(it.get("feature")))
            put(item, "who", text(it.get("who")))
            put(item, "since", text(it.get("since")))
            put(item, "title", title)
            put(item, "text", text(it.get(text_from)))
            put(item, "how_to_send", text(it.get("l")))
            sources[f"/items/{len(items)}"] = (DASHBOARD, f"{listname} '{title or '?'}'", {
                "key": "t (the item key is made from its title)", "kind": listname, "feature": "feature",
                "who": "who", "since": "since", "title": "t", "text": text_from, "how_to_send": "l"})
            items.append(item)
    left_out["items"] += len(d.get("todos") or [])

    people, came_from, warn = contacts(root, prof)
    if warn:
        warnings.append(warn)
    for i, c in enumerate(people):
        if came_from == "profile":
            sources[f"/client_contacts/{i}"] = (PROFILE, f"tools.client_contacts '{c.get('name', '?')}'", {})
        else:
            sources[f"/client_contacts/{i}"] = (SLACK, f"client_owners '{c.get('name', '?')}'", {})

    sent_by = git(root, "config", "user.name")
    if not sent_by:
        raise Stop("git has no user name (git config user.name). The Portal logs who sent each Publish: set it with "
                   "`git config user.name \"Your Name\"`, then run again. Nothing was sent.")
    payload: dict = {"contract": CONTRACT, "sent_at": sent_at or now_utc(), "sent_by": sent_by,
                     "ba_tools_version": ba_tools_version(prof)}
    put(payload, "source_commit", git(root, "rev-parse", "HEAD"))
    payload.update(features=features, items=items, areas=areas, release_rows=rows, client_contacts=people)
    return payload, sources, left_out, warnings


# ---------------------------------------------------------------- checks and wording

def where(path: str, sources: dict) -> str:
    """Turn a payload path (/features/3/title) into the file, the row and the field it came from."""
    parts = path.strip("/").split("/") if path.strip("/") else []
    if len(parts) >= 2 and f"/{parts[0]}/{parts[1]}" in sources:
        file, row, fields = sources[f"/{parts[0]}/{parts[1]}"]
        field = fields.get(parts[2], parts[2]) if len(parts) > 2 else ""
        return f"{file} → {row}" + (f" → {field}" if field else "")
    top = {
        "features": f"{DASHBOARD} → features", "items": f"{DASHBOARD} → awaiting and agenda",
        "areas": f"the map build ({MAP_PAGE}) → areas", "release_rows": f"the map build ({MAP_PAGE}) → releases",
        "client_contacts": f"{PROFILE} → tools.client_contacts", "sent_by": "git config user.name",
        "ba_tools_version": f"{PROFILE} → ba_tools_version", "source_commit": "git rev-parse HEAD",
        "sent_at": "the send time", "contract": "the contract version",
    }
    return top.get(parts[0], "the payload") if parts else "the payload"


def problem_lines(details: list[dict], sources: dict) -> list[str]:
    lines = []
    for det in details:
        path, msg = str(det.get("path") or ""), str(det.get("message") or "").strip()
        if path and msg.startswith(path):
            msg = msg[len(path):].lstrip(": ").strip()
        if len(msg) > 300:                       # a "too many" message quotes the whole list: keep both ends
            msg = msg[:150].rstrip() + " … " + msg[-100:].lstrip()
        lines.append(f"{where(path, sources)}: {msg}" + (f" ({path})" if path else ""))
    return lines


def local_check(payload: dict, body: bytes, sources: dict) -> None:
    found = checks.check_publish(payload)
    if found:
        lines = problem_lines(found["details"], sources)
        raise Stop("The Dashboard does not match the contract, so nothing was sent. Fix these, then run "
                   "`dashboard plan` again:\n" + "\n".join(f"- {ln}" for ln in lines))
    if len(body) > MAX_BYTES:
        raise Stop(f"The Dashboard is {len(body) / 1e6:.1f} MB; the Portal takes at most 2 MB. Nothing was sent.")


def encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- the Portal

def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def post(url: str, key: str, body: bytes, dry_run: bool, sources: dict) -> dict:
    """POST the payload. Returns the checked 200 reply; anything else stops the run."""
    return exchange(url, ENDPOINT, dry_run, sources, "dashboard",
                    lambda client, target: client.post(target, content=body, headers={
                        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                        "Accept": "application/json"}))


def exchange(url: str, endpoint: str, dry_run: bool, sources: dict, kind: str, send, *,
             next_step: dict | None = None, where_fn=None, first_line=None) -> dict:
    """Send one request with send(client, target) and handle the reply the same way for every kind of Publish.
    Returns the checked 200 reply; anything else stops the run. kind is the command word: dashboard or page."""
    target = url + endpoint + ("?dry_run=1" if dry_run else "")
    try:
        with http_client() as client:
            r = send(client, target)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.UnsupportedProtocol):
        raise Stop(f"The Portal is not reachable at {url}. Check that it is running and that tools.portal.url is "
                   "right. Nothing was sent.") from None
    except httpx.InvalidURL:
        raise Stop(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it. "
                   "Nothing was sent.") from None
    except httpx.RequestError:
        if dry_run:
            raise Stop(f"The Portal is not reachable at {url}: the dry run got no reply. Check that it is running "
                       "and that tools.portal.url is right. Nothing was sent.") from None
        raise MaybeSent(f"The send went out to {url}, but no reply came back, so it may have arrived. Before "
                        "sending again, check the Portal: Admin → Projects → the Project → Publishing. If the "
                        f"send is not there, run `{kind} send` again with the same --payload file (it was "
                        "kept).") from None
    try:
        doc = r.json()
    except ValueError:
        doc = None
    if r.status_code == 200:
        if (not isinstance(doc, dict) or checks.check_reply(doc, REPLY) or doc.get("dry_run") is not dry_run
                or doc.get("kind", "dashboard") != kind):
            raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                       "Nothing more was sent.")
        return doc
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict) or not err.get("code"):
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). Nothing more was sent.")
    code = str(err["code"])
    steps = NEXT_STEP if next_step is None else next_step
    head = first_line(code) if first_line else None
    lines = [head or f"The Portal refused the send ({code}): {text(err.get('message')) or 'no message'}"]
    details = [x for x in (err.get("details") or []) if isinstance(x, dict)]
    lines += [f"- {ln}" for ln in (where_fn or problem_lines)(details, sources)]
    if code in steps:
        lines.append(steps[code])
    lines.append("Nothing more was sent.")
    raise Stop("\n".join(lines))


# ---------------------------------------------------------------- the Client list (display only)

def plain(s) -> str:
    """HTML tags removed for display; the words are the Portal's."""
    t = re.sub(r"<\s*(br|/p|/li|/ul|/ol)\b[^>]*>", "\n", str(s or ""), flags=re.I)
    t = re.sub(r"<\s*li\b[^>]*>", "• ", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(ln for ln in (re.sub(r"[ \t]+", " ", x).strip() for x in t.splitlines()) if ln)


def indent(s: str, pad: str) -> str:
    return "\n".join(pad + ln for ln in s.splitlines())


def client_list(reply: dict) -> str:
    view = reply["client_view"]
    titles = {f["id"]: f["title"] for f in view["features"]}
    out_lines = ["What the Client will read — the Portal's own dry run. Nothing is stored yet.", ""]
    out_lines.append(f"Features ({len(view['features'])}):")
    for f in view["features"]:
        head = f"- {f['title']}" + (f" ({f['short']})" if f.get("short") else "")
        head += f" — {STAGE_NAME.get(f['stage'], f['stage'])} · area: {f['map_area']}"
        head += f" · releases: {', '.join(f['releases'])}" if f.get("releases") else " · Not planned yet"
        out_lines.append(head)
        out_lines.append(indent(plain(f["summary"]), "    "))
        for q in f.get("open") or []:
            out_lines.append(f"    Open question: {plain(q)}")
        page = f.get("page")
        out_lines.append("    Clarification page: " + (f"Published — {page['answered']} of {page['total']} answered"
                                                        if page else "Questions coming"))
        if f.get("hiddenByDoneFilter"):
            out_lines.append("    (Done over 2 weeks ago: hidden while \"Hide done > 2 weeks\" is on, the default)")
    groups = (("Waiting on you", "waitingOnYou"), ("Next-call agenda", "onAgenda"))
    for label, flag in groups:
        shown = [i for i in view["items"] if i.get(flag)]
        out_lines += ["", f"{label} ({len(shown)}):"]
        if not shown:
            out_lines.append("- none")
        for i in shown:
            out_lines.append(f"- {i['title']} — under {titles.get(i['feature'], i['feature'])}")
            if i.get("text"):
                out_lines.append(indent(plain(i["text"]), "    "))
            if i.get("how_to_send"):
                out_lines.append(f"    How to send: {i['how_to_send']}")
    other = [i for i in view["items"] if not i.get("waitingOnYou") and not i.get("onAgenda")]
    if other:
        out_lines += ["", f"Also shown ({len(other)}):"] + [f"- {i['title']}" for i in other]
    names = reply.get("client_contact_names") or []
    out_lines += ["", f"Client contacts ({len(names)}): " + (", ".join(names) if names else "none")]
    return "\n".join(out_lines)


# ---------------------------------------------------------------- commands

def write_payload(body: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix="portal-publish-", suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    return Path(name)


def cmd_plan(root: Path, refresh: bool) -> dict:
    url, key, prof = settings(root)
    clean_old_payloads()
    run_build(root, refresh)
    warnings = []
    if not refresh:
        w = stale_warning(root)
        if w:
            warnings.append(w)
    payload, sources, left_out, more = build_payload(root, prof)
    warnings += more
    body = encode(payload)
    local_check(payload, body, sources)
    reply = post(url, key, body, dry_run=True, sources=sources)
    path = write_payload(body)
    return {"ok": True, "portal": url, "payload": str(path), "sent_at": payload["sent_at"],
            "counts": reply["counts"], "left_out": left_out, "warnings": warnings,
            "client_list": client_list(reply)}


def payload_arg(argv: list[str]) -> Path:
    """Only a file `dashboard plan` or `page plan` wrote: portal-publish-*.json in the system temp folder. Nothing else is
    read or deleted."""
    p = arg(argv, "--payload")
    if not p:
        raise Stop("--payload <file> is required (the path `dashboard plan` or `page plan` printed).")
    path = Path(p).resolve()
    if not path.match(PAYLOAD_GLOB) or path.parent != Path(tempfile.gettempdir()).resolve():
        raise Stop(f"{p} is not a payload file `dashboard plan` or `page plan` wrote (portal-publish-*.json in the "
                   f"temp folder {tempfile.gettempdir()}). Nothing was sent or deleted.")
    return path


def clean_old_payloads(now: float | None = None) -> None:
    """Payload files hold contact emails: drop ones left over from runs more than a day ago."""
    now = time.time() if now is None else now
    for f in Path(tempfile.gettempdir()).glob(PAYLOAD_GLOB):
        try:
            if now - f.stat().st_mtime > PAYLOAD_MAX_AGE:
                f.unlink()
        except OSError:
            pass


def payload_kind(path: Path) -> str | None:
    """"page" for a file `page plan` wrote, "dashboard" for one `dashboard plan` wrote, else None."""
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(doc, dict) and doc.get("kind") == "page":
        return "page"
    if isinstance(doc, dict) and doc.get("contract") == CONTRACT:
        return "dashboard"
    return None


def check_kind(path: Path, want: str, action: str) -> None:
    """Stop, deleting nothing, when a page payload is given to a dashboard command or the reverse."""
    got = payload_kind(path)
    if got and got != want:
        raise Stop(f"{path} is a {got} payload, not a {want} one: use `{got} {action}`. Nothing was sent or "
                   "deleted.")


def cmd_send(root: Path, path: Path) -> dict:
    check_kind(path, "dashboard", "send")
    keep = False
    try:
        url, key, _ = settings(root)
        if not path.exists():
            raise Stop(f"{path} is not there. Run `dashboard plan` again. Nothing was sent.")
        body = path.read_bytes()
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            raise Stop(f"{path} is not a payload `dashboard plan` wrote. Run `dashboard plan` again.") from None
        local_check(payload, body, {})
        try:
            reply = post(url, key, body, dry_run=False, sources={})
        except MaybeSent:
            keep = True
            raise
    finally:
        if not keep:
            path.unlink(missing_ok=True)
    c = reply["counts"]
    report = (f"Sent the Dashboard to {url}: {c['features']} Features, {c['items']} Items, "
              f"{c['client_contacts']} Client contacts. The Portal confirmed it at {reply['received_at']} (UTC), "
              f"publish id {reply['publish_id']}.")
    return {"ok": True, "sent": "Dashboard", "portal": url, "counts": c, "publish_id": reply["publish_id"],
            "received_at": reply["received_at"], "report": report}


def cmd_discard(path: Path, kind: str = "dashboard") -> dict:
    check_kind(path, kind, "discard")
    existed = path.exists()
    path.unlink(missing_ok=True)
    return {"ok": True, "sent": None, "deleted": str(path) if existed else None,
            "report": "Nothing was sent. The payload file was deleted."}


# ---------------------------------------------------------------- page <slug> (a Clarification page)

CLARIFICATIONS = "docs/BA/clarifications"
FIXYAML_PY = SKILLS / "clarification-page" / "scripts" / "_fixyaml.py"
PAGE_ENDPOINT = "/api/v1/publish/page"
PAGE_CONTRACT = "clarification/1"
PUBLISH_PART = "publish"
SCREEN_MAX_BYTES = 10 * 1024 * 1024      # each screenshot (contract clarification-1.md, AD-12)
PAGE_MAX_BYTES = 90 * 1024 * 1024        # the publish part plus every screenshot


def multipart_margin(parts: int) -> int:
    """Room for the multipart framing in the 90 MB check."""
    return 1024 * parts + 64 * 1024


SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# The fields the skill reads from the page YAML, per level. Anything else stays in the repo and is listed in
# left_out. `src` is read to find the file; `title` and `standfirst` only stand in for `name` and `description`;
# `settled` is read only when there is no `decisions` list.
PAGE_FIELDS = {"slug", "store_key", "url", "name", "title", "round", "description", "standfirst", "problem",
               "solution", "design", "decisions", "settled", "questions"}
DESIGN_FIELDS = {"label", "more_label", "summary", "detail", "screens"}
DESIGN_SCREEN_FIELDS = {"src", "cap", "hero"}
DECISION_FIELDS = {"id", "date", "who", "how", "title", "detail"}
QUESTION_FIELDS = {"id", "section", "title", "meta", "body", "body2", "snag", "quote", "note", "note_placeholder",
                   "options", "screens"}
QUOTE_FIELDS = {"text", "cite"}
OPTION_FIELDS = {"v", "t", "d", "rec"}
QUESTION_SCREEN_FIELDS = {"src", "cap"}

PAGE_NEXT_STEP = {
    **NEXT_STEP,
    "contract_invalid": "Fix each field listed in the page YAML, then run `page plan <slug>` again.",
    "payload_too_large": "The page is too big to send (at most 10 MB per screenshot, 90 MB in all). Make the "
                         "screenshots smaller or fewer, then run `page plan <slug>` again.",
    "bad_request": "The Portal could not read the send. Run `page plan <slug>` again; if it repeats, report it.",
    "screenshot_mismatch": "A screenshot the page names did not arrive, or one arrived that the page does not "
                           "name. Run `page plan <slug>` again; if it repeats, report it.",
}


def find_page_yaml(root: Path, slug_arg: str) -> Path:
    if not SLUG_RE.fullmatch(slug_arg or ""):
        raise Stop(f"'{slug_arg}' is not a page slug (only a-z, 0-9 and single hyphens). Nothing was sent.")
    tried = [f"{CLARIFICATIONS}/{slug_arg}-decisions.yaml", f"{CLARIFICATIONS}/{slug_arg}.yaml"]
    for rel in tried:
        if (root / rel).is_file():
            return root / rel
    raise Stop(f"No page YAML for '{slug_arg}'. Looked for {tried[0]} and {tried[1]}. Check the slug "
               "(it is the `slug:` line of the page YAML). Nothing was sent.")


def fix_yaml(path: Path) -> int:
    """Run clarification-page's _fixyaml.py on the BA's YAML (it quotes values holding a colon). Returns how many
    lines it changed. When it changed none, the file is put back byte for byte (the script rewrites line endings
    on Windows); when it changed some, the file keeps its own line endings."""
    before = path.read_bytes()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        r = subprocess.run([sys.executable, str(FIXYAML_PY), str(path)], capture_output=True, env=env, timeout=60)
    except subprocess.TimeoutExpired:
        path.write_bytes(before)
        raise Stop("_fixyaml.py did not finish in a minute, so it was stopped. Nothing was sent.") from None
    said = (r.stdout or b"").decode("utf-8", "replace")
    m = re.search(r"->\s*(\d+)\s+quoted", said)
    if r.returncode != 0 or not m:
        path.write_bytes(before)
        why = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise Stop(f"_fixyaml.py failed on {path.name}: {why[-1] if why else said.strip() or r.returncode}. "
                   "Nothing was sent.")
    fixed = int(m.group(1))
    if fixed == 0:
        path.write_bytes(before)
        return 0
    after = path.read_bytes().replace(b"\r\n", b"\n")
    if b"\r\n" in before:                       # keep the file's own line endings, whatever the OS wrote
        after = after.replace(b"\n", b"\r\n")
    try:
        yaml.safe_load(after.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as e:
        path.write_bytes(before)
        raise Stop(f"After _fixyaml.py quoted {fixed} line(s) in {path.name}, the file still does not read as YAML "
                   f"({e}). The file was put back as it was. Fix it by hand, then run again. "
                   "Nothing was sent.") from None
    path.write_bytes(after)
    return fixed


def light_text(s) -> str:
    """An old `settled:` line as plain text: tags removed, entities turned into characters."""
    t = html.unescape(re.sub(r"<[^>]+>", "", str(s or "")))
    t = re.sub(r"<[^>]+>", "", t).replace("<", "‹").replace(">", "›")   # &lt;b&gt; unescaped: no tags in text
    return re.sub(r"\s+", " ", t).strip()


def settled_decisions(settled) -> tuple[list[dict], list[int]]:
    """Old pages: each `settled:` HTML line becomes a decision with no date, who or how. The <strong> part is the
    title, the rest the detail (as clarification-page's _generate.py build_decisions). Also returns, per decision,
    its index in the `settled:` list."""
    lines = settled if isinstance(settled, list) else [settled]
    out, where = [], []
    for n, line in enumerate(lines):
        line = str(line or "")
        m = re.match(r"\s*<strong>(.*?)</strong>(.*)", line, re.S)
        title, detail = (light_text(m.group(1)), light_text(m.group(2))) if m else (light_text(line), "")
        if not title or title.lower().startswith("already decided"):
            continue
        dec: dict = {"id": f"s{len(out) + 1}"}
        put(dec, "title", title.rstrip("."))
        put(dec, "detail", detail.lstrip(".,;:—– ").strip())
        out.append(dec)
        where.append(n)
    return out, where


def is_placeholder_url(url: str) -> bool:
    """A url the BA has not filled in yet (https://claude.ai/artifact/<the page id>, TBD, an address with no id).
    A real link has http(s), a host and a non-empty last path part."""
    if re.search(r"[<>\s]", url):
        return True
    try:
        u = urllib.parse.urlsplit(url)
        host = u.hostname
    except ValueError:
        return True
    return not (u.scheme in ("http", "https") and host and u.path.split("/")[-1])


def truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


def sniff(data: bytes) -> str | None:
    """The image type by its first bytes: PNG, JPEG or WebP, else None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


EXTENSION_TYPE = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def inside(path: Path, root: Path) -> bool:
    """True when the resolved path sits inside the project repo."""
    return path.resolve().is_relative_to(root.resolve())


def bare_name(src: str) -> str:
    return re.split(r"[\\/]", src.strip())[-1]


def unique_name(name: str, taken: set[str]) -> str:
    """The bare name, or name-2.png, name-3.png … when another screen took it (letter case aside)."""
    if name.lower() not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, dot + ext) if stem else (name, "")
    n = 2
    while f"{stem}-{n}{ext}".lower() in taken:
        n += 1
    return f"{stem}-{n}{ext}"


def as_list(v) -> list:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def as_dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def left_out_fields(cfg: dict) -> list[str]:
    """Every field of the page YAML the skill does not send, as a path (questions[].spec_ref)."""
    found: list[str] = []

    def note(path: str) -> None:
        if path not in found:
            found.append(path)

    def extra(obj, allowed: set, prefix: str) -> None:
        for k in as_dict(obj):
            if k not in allowed:
                note(f"{prefix}{k}")

    extra(cfg, PAGE_FIELDS, "")
    if text(cfg.get("name")) and "title" in cfg:
        note("title")
    if text(cfg.get("description")) and "standfirst" in cfg:
        note("standfirst")
    if cfg.get("decisions") and "settled" in cfg:
        note("settled")
    design = as_dict(cfg.get("design"))
    extra(design, DESIGN_FIELDS, "design.")
    for s in as_list(design.get("screens")):
        extra(s, DESIGN_SCREEN_FIELDS, "design.screens[].")
    if cfg.get("decisions"):
        for d in as_list(cfg.get("decisions")):
            extra(d, DECISION_FIELDS, "decisions[].")
    for q in as_list(cfg.get("questions")):
        extra(q, QUESTION_FIELDS, "questions[].")
        q = as_dict(q)
        extra(q.get("quote"), QUOTE_FIELDS, "questions[].quote.")
        for o in as_list(q.get("options")):
            extra(o, OPTION_FIELDS, "questions[].options[].")
        for s in as_list(q.get("screens")):
            extra(s, QUESTION_SCREEN_FIELDS, "questions[].screens[].")
    return found


def build_page(root: Path, yaml_path: Path, cfg: dict, prof: dict, sent_at: str | None = None):
    """The clarification/1 page (contract clarification-1.md), built by allow-list; its screenshot parts
    (name, source path, type, bytes); where each sent value came from; what was left out; warnings.
    A screenshot that is missing, not PNG / JPEG / WebP, or over 10 MB stops the run here."""
    rel = yaml_path.relative_to(root).as_posix()
    base = yaml_path.parent
    warnings: list[str] = []
    left_out = left_out_fields(cfg)
    sources: dict[str, str] = {}             # "/questions/2" -> "questions[2] 'q3-…'"
    parts: list[dict] = []
    taken: set[str] = set()

    def screen(s, where: str, label: str) -> dict:
        s = s if isinstance(s, dict) else {"src": s}
        src = text(s.get("src"))
        sources[where] = label
        if not src:
            raise Stop(f"{rel} → {label} has no src (the screenshot file). Add it, then run `page plan` again. "
                       "Nothing was sent.")
        path = (base / src).resolve()
        if not inside(path, root):
            raise Stop(f"{rel} → {label} → src: {src} is outside the project repo ({path}). Screenshots must sit in "
                       "the repo, next to the page YAML. Nothing was sent.")
        if not path.is_file():
            raise Stop(f"{rel} → {label} → src: the screenshot {src} is not there (looked for {path}). Add the "
                       "file or fix the path (it is relative to the YAML's folder), then run `page plan` again. "
                       "Nothing was sent.")
        size = path.stat().st_size
        if size > SCREEN_MAX_BYTES:
            raise Stop(f"{rel} → {label} → src: {src} is {size / 1024 / 1024:.1f} MB; a screenshot may be at "
                       "most 10 MB. Make it smaller, then run `page plan` again. Nothing was sent.")
        data = path.read_bytes()
        kind = sniff(data)
        if kind is None:
            raise Stop(f"{rel} → {label} → src: {src} is not a PNG, JPEG or WebP image (judged by its first "
                       "bytes). Save it as one of those, then run `page plan` again. Nothing was sent.")
        if EXTENSION_TYPE.get(Path(src).suffix.lower()) != kind:
            warnings.append(f"{rel} → {label} → src: {src} is really a {kind.split('/')[1].upper()} image, but its "
                            "name says otherwise. It is sent as it is; renaming it would avoid confusion.")
        name = unique_name(bare_name(src), taken)
        taken.add(name.lower())
        parts.append({"name": name, "path": str(path), "type": kind, "data": data})
        return {"file": name}

    page: dict = {}
    put(page, "slug", text(cfg.get("slug")))
    put(page, "store_key", text(cfg.get("store_key")))
    url = text(cfg.get("url"))
    if url and is_placeholder_url(url):
        warnings.append(f"The page's url in {rel} ({url}) is a placeholder, not a real link, so it was left out. "
                        "The Client Dashboard links a Feature to this page by that url: put the page's real link "
                        "there when it has one, and send the page again.")
        left_out.append("url (a placeholder)")
    else:
        put(page, "url", url)
    put(page, "name", text(cfg.get("name")) or text(cfg.get("title")))
    put(page, "round", text(cfg.get("round")))
    put(page, "description", text(cfg.get("description")) or text(cfg.get("standfirst")))
    put(page, "problem", text(cfg.get("problem")))
    put(page, "solution", text(cfg.get("solution")))

    src_design = as_dict(cfg.get("design"))
    design: dict = {}
    for k in ("label", "more_label", "summary", "detail"):
        put(design, k, text(src_design.get(k)))
    screens = []
    for i, s in enumerate(as_list(src_design.get("screens"))):
        out = screen(s, f"/design/screens/{i}", f"design.screens[{i}]")
        put(out, "cap", text(as_dict(s).get("cap")))
        if truthy(as_dict(s).get("hero")):
            out["hero"] = True
        screens.append(out)
    put(design, "screens", screens)
    page["design"] = design

    if cfg.get("decisions"):
        decisions = []
        for i, d in enumerate(as_list(cfg.get("decisions"))):
            d = d if isinstance(d, dict) else {"title": d}
            dec: dict = {}
            put(dec, "id", text(d.get("id")))
            date = d.get("date")
            if isinstance(date, dt.datetime):          # YAML reads "2026-09-11 10:00" as a datetime: date part
                date = date.date()
            put(dec, "date", date.isoformat() if isinstance(date, dt.date) else text(date))
            for k in ("who", "how", "title", "detail"):
                put(dec, k, text(d.get(k)))
            sources[f"/decisions/{i}"] = f"decisions[{i}] '{text(d.get('id')) or text(d.get('title'))}'"
            decisions.append(dec)
    else:
        decisions, lines = settled_decisions(cfg.get("settled") or [])
        for i, n in enumerate(lines):
            sources[f"/decisions/{i}"] = f"settled[{n}] (sent as a decision)"
    put(page, "decisions", decisions)

    questions = []
    for i, q in enumerate(as_list(cfg.get("questions"))):
        q = as_dict(q)
        label = f"questions[{i}] '{text(q.get('id')) or '?'}'"
        sources[f"/questions/{i}"] = label
        qo: dict = {}
        put(qo, "id", text(q.get("id")))
        for k in ("section", "title", "meta", "body", "body2", "snag"):
            put(qo, k, text(q.get(k)))
        quote = q.get("quote")
        if quote:
            quote = quote if isinstance(quote, dict) else {"text": quote}
            qq: dict = {}
            put(qq, "text", text(quote.get("text")))
            put(qq, "cite", text(quote.get("cite")))
            qo["quote"] = qq
        for k in ("note", "note_placeholder"):
            put(qo, k, text(q.get(k)))
        options = []
        for o in as_list(q.get("options")):
            o = o if isinstance(o, dict) else {"t": o}
            opt: dict = {}
            put(opt, "v", text(o.get("v")))
            put(opt, "t", text(o.get("t")))
            put(opt, "d", text(o.get("d")))
            if truthy(o.get("rec")):
                opt["rec"] = True
            options.append(opt)
        qo["options"] = options
        qscreens = []
        for j, s in enumerate(as_list(q.get("screens"))):
            out = screen(s, f"/questions/{i}/screens/{j}", f"{label} → screens[{j}]")
            put(out, "cap", text(as_dict(s).get("cap")))
            qscreens.append(out)
        put(qo, "screens", qscreens)
        questions.append(qo)
    page["questions"] = questions

    sent_by = git(root, "config", "user.name")
    if not sent_by:
        raise Stop("git has no user name (git config user.name). The Portal logs who sent each Publish: set it with "
                   "`git config user.name \"Your Name\"`, then run again. Nothing was sent.")
    envelope: dict = {"contract": PAGE_CONTRACT, "sent_at": sent_at or now_utc(), "sent_by": sent_by,
                      "ba_tools_version": ba_tools_version(prof)}
    put(envelope, "source_commit", git(root, "rev-parse", "HEAD"))
    return {**envelope, **page}, parts, sources, left_out, warnings


def page_where(rel: str, sources: dict):
    """problem_lines for a page: a payload path becomes the YAML file, the row and the field."""
    top = {"sent_by": "git config user.name", "ba_tools_version": f"{PROFILE} → ba_tools_version",
           "source_commit": "git rev-parse HEAD", "sent_at": "the send time", "contract": "the contract version"}

    def lines(details: list[dict], _sources=None) -> list[str]:
        out = []
        for det in details:
            path, msg = str(det.get("path") or ""), str(det.get("message") or "").strip()
            if path and msg.startswith(path):
                msg = msg[len(path):].lstrip(": ").strip()
            if len(msg) > 300:
                msg = msg[:150].rstrip() + " … " + msg[-100:].lstrip()
            bits = path.strip("/").split("/") if path.strip("/") else []
            if bits and bits[0] in top:
                out.append(f"{top[bits[0]]}: {msg} ({path})")
                continue
            row, rest = "", bits
            for n in range(len(bits), 0, -1):
                if "/" + "/".join(bits[:n]) in sources:
                    row, rest = sources["/" + "/".join(bits[:n])], bits[n:]
                    break
            loc = " → ".join(x for x in (rel, row, ".".join(rest)) if x)
            out.append(f"{loc}: {msg}" + (f" ({path})" if path else ""))
        return out
    return lines


def page_local_check(page: dict, body: bytes, parts: list[dict], rel: str, sources: dict) -> None:
    found = checks.check_publish(page, "clarification", [p["name"] for p in parts])
    if found:
        lines = page_where(rel, sources)(found["details"])
        raise Stop(f"The page does not match the contract, so nothing was sent. Fix these in {rel}, then run "
                   "`page plan` again:\n" + "\n".join(f"- {ln}" for ln in lines))
    # The multipart framing adds a little per part: leave room for it (1 KB per part plus 64 KB).
    total = len(body) + sum(len(p["data"]) for p in parts) + multipart_margin(len(parts) + 1)
    if total > PAGE_MAX_BYTES:
        raise Stop(f"The page and its {len(parts)} screenshots come to {total / 1024 / 1024:.1f} MB; the Portal "
                   "takes at most 90 MB in one send. Make the screenshots smaller or fewer, then run `page plan` "
                   "again. Nothing was sent.")


def post_page(url: str, key: str, body: bytes, parts: list[dict], dry_run: bool, rel: str, sources: dict,
              round_label: str) -> dict:
    """POST the page as multipart: part `publish` = the JSON, then one part per screenshot named by its file."""
    files = [(PUBLISH_PART, (None, body, "application/json"))]
    files += [(p["name"], (p["name"], p["data"], p["type"])) for p in parts]

    def first_line(code: str) -> str | None:
        if code == "round_has_answers":
            return f"Round {round_words(round_label)} already has answers — give it a new round key"
        return None

    steps = {**PAGE_NEXT_STEP,
             "round_has_answers": f"Change store_key in {rel} to a new round key (and the round label), then run "
                                  "`page plan` again."}
    reply = exchange(url, PAGE_ENDPOINT, dry_run, sources, "page",
                     lambda client, target: client.post(target, files=files, headers={
                         "Authorization": f"Bearer {key}", "Accept": "application/json"}),
                     next_step=steps, where_fn=page_where(rel, sources), first_line=first_line)
    if reply["round"].get("key") != json.loads(body.decode("utf-8")).get("store_key"):
        raise Stop("The Portal's reply was not understood (HTTP 200): it names a different round key from the one "
                   "sent. Nothing more was sent.")
    return reply


def round_words(label: str) -> str:
    """The Round label without a leading "Round", so messages do not say "Round Round V4"."""
    label = text(label)
    return label[6:].strip() if label.lower().startswith("round ") else label


def page_view(reply: dict) -> str:
    """The Client view of the page, from the Portal's dry-run reply only. Tags removed for display."""
    view, rnd, counts = reply["client_view"], reply["round"], reply["counts"]
    lines = ["What the Client will read — the Portal's own dry run. Nothing is stored yet.", "",
             f"Page: {plain(view['name'])}",
             f"Round label: {plain(view['round'])}",
             "A new Round." if rnd.get("new") else
             f"This replaces the Round with the same key ({rnd.get('key')}); no answers were sent on it yet."]
    for field, label in (("description", "Description"), ("problem", "Problem"), ("solution", "Solution")):
        if view.get(field):
            lines += ["", f"{label}:", indent(plain(view[field]), "    ")]
    design = view.get("design") or {}
    lines += ["", f"{plain(design.get('label')) or 'What it looks like'}:", indent(plain(design.get("summary")), "    ")]
    if design.get("screens"):
        lines.append(f"    Screens ({len(design['screens'])}):")
        lines += [f"    - {plain(s.get('cap')) or '(no caption)'}" for s in design["screens"]]
    questions = view.get("questions") or []
    lines += ["", f"Questions ({len(questions)}):"]
    if not questions:
        lines.append("- none")
    for n, q in enumerate(questions, 1):
        section = f"[{plain(q['section'])}] " if q.get("section") else ""
        lines.append(f"{n}. {section}{plain(q['title'])}")
        for o in q.get("options") or []:
            lines.append(f"    - {plain(o['t'])}" + (" (recommended)" if o.get("rec") else ""))
            if o.get("d"):
                lines.append(indent(plain(o["d"]), "        "))
        if q.get("screens"):
            lines.append(f"    Screens: {len(q['screens'])}")
    decisions = view.get("decisions") or []
    lines += ["", f"Answered questions ({len(decisions)}):"]
    if not decisions:
        lines.append("- none (the section is hidden)")
    for d in decisions:
        when = ", ".join(plain(d[k]) for k in ("date", "who", "how") if d.get(k))
        lines.append(f"- {plain(d['title'])}" + (f" ({when})" if when else ""))
        if d.get("detail"):
            lines.append(indent(plain(d["detail"]), "    "))
    lines += ["", f"Counts: {counts['questions']} Questions, {counts['screenshots']} screenshots."]
    return "\n".join(lines)


def cmd_page_plan(root: Path, slug_arg: str) -> dict:
    url, key, prof = settings(root)
    clean_old_payloads()
    yaml_path = find_page_yaml(root, slug_arg)
    rel = yaml_path.relative_to(root).as_posix()

    def first_checks(cfg) -> dict:
        if not isinstance(cfg, dict):
            raise Stop(f"{rel} is not a page YAML (it holds no fields). Nothing was sent.")
        if text(cfg.get("slug")) != slug_arg:
            raise Stop(f"{rel} has slug '{text(cfg.get('slug'))}', but you asked for '{slug_arg}'. Run `page plan` "
                       "with the YAML's slug, or fix its `slug:` line. Nothing was sent.")
        if not text(cfg.get("round")):
            raise Stop(f"{rel} has no `round:` line — the Round label the Client reads (for example \"Round V1 · "
                       "sent 27 Oct 2026 by <your name>\"). Add one, then run `page plan` again. Nothing was sent.")
        return cfg

    # The slug and round checks run on a plain read first, so a wrong slug never rewrites the file. A YAML that
    # does not read yet (an unquoted colon) is checked after _fixyaml.py has quoted it.
    try:
        first_checks(yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {})
    except (yaml.YAMLError, UnicodeDecodeError):
        pass
    fixed = fix_yaml(yaml_path)
    try:
        cfg = first_checks(yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {})
        page, parts, sources, left_out, warnings = build_page(root, yaml_path, cfg, prof)
        body = encode(page)
        page_local_check(page, body, parts, rel, sources)
        reply = post_page(url, key, body, parts, True, rel, sources, page["round"])
    except Stop as e:
        if fixed:
            raise Stop(f"{e}\n(Before this stop, _fixyaml.py quoted {fixed} line(s) in {rel}: the file changed; "
                       "keep the change.)") from None
        raise
    saved = {"kind": "page", "slug": page["slug"], "name": page["name"], "round": page["round"], "yaml": rel,
             "portal": url, "publish": body.decode("utf-8"),
             "parts": [{"name": p["name"], "path": p["path"], "type": p["type"],
                        "sha256": hashlib.sha256(p["data"]).hexdigest()} for p in parts]}
    path = write_payload(json.dumps(saved, ensure_ascii=False).encode("utf-8"))
    if fixed:
        warnings.insert(0, f"_fixyaml.py quoted {fixed} line(s) in {rel} (values holding a colon). The file "
                           "changed: commit it with the page.")
    return {"ok": True, "portal": url, "payload": str(path), "page": page["slug"], "yaml": rel,
            "round": reply["round"], "sent_at": page["sent_at"], "counts": reply["counts"],
            "left_out": left_out, "warnings": warnings, "fixed_lines": fixed, "client_view": page_view(reply)}


def read_page_payload(path: Path, root: Path) -> tuple[dict, bytes, list[dict]]:
    """The payload `page plan` wrote, with every screenshot re-read (only from inside the repo) and matched to its
    SHA-256."""
    if not path.exists():
        raise Stop(f"{path} is not there. Run `page plan <slug>` again. Nothing was sent.")
    try:
        saved = json.loads(path.read_bytes().decode("utf-8"))
        if not (isinstance(saved, dict) and saved.get("kind") == "page" and isinstance(saved.get("publish"), str)
                and isinstance(saved.get("parts"), list)):
            raise ValueError
        body = saved["publish"].encode("utf-8")
        if not isinstance(json.loads(body.decode("utf-8")), dict):
            raise ValueError
    except ValueError:
        raise Stop(f"{path} is not a payload `page plan` wrote. Run `page plan <slug>` again. "
                   "Nothing was sent.") from None
    parts = []
    for p in saved["parts"]:
        p = as_dict(p)
        src = Path(str(p.get("path") or ""))
        if not p.get("path") or not inside(src, root):
            raise Stop(f"{path} names a screenshot outside the project repo ({src}). Run `page plan "
                       f"{saved.get('slug')}` again. Nothing was sent.")
        data = src.read_bytes() if src.is_file() else None
        if data is None or not p.get("sha256") or hashlib.sha256(data).hexdigest() != p.get("sha256"):
            raise Stop(f"The screenshot {src} changed (or is gone) since `page plan`. Run `page plan "
                       f"{saved.get('slug')}` again, so the Client view the BA approves is what is sent. "
                       "Nothing was sent.")
        parts.append({"name": str(p.get("name")), "path": str(src), "type": str(p.get("type")), "data": data})
    return saved, body, parts


def cmd_page_send(root: Path, path: Path) -> dict:
    check_kind(path, "page", "send")
    keep = False
    try:
        url, key, _ = settings(root)
        saved, body, parts = read_page_payload(path, root)
        if text(saved.get("portal")).rstrip("/") != url:
            raise Stop(f"`page plan` ran its dry run against {saved.get('portal') or 'another Portal'}, but "
                       f"tools.portal.url is now {url}. Run `page plan {saved.get('slug')}` again. Nothing was sent.")
        rel = text(saved.get("yaml")) or "the page YAML"
        page_local_check(json.loads(body.decode("utf-8")), body, parts, rel, {})
        try:
            reply = post_page(url, key, body, parts, False, rel, {}, text(saved.get("round")))
        except MaybeSent:
            keep = True
            raise
    finally:
        if not keep:
            path.unlink(missing_ok=True)
    c, rnd = reply["counts"], reply["round"]
    how = "a new Round" if rnd.get("new") else "it replaced the Round with the same key"
    report = (f"Sent the page \"{saved.get('name')}\" ({saved.get('slug')}) to {url}: "
              f"Round {round_words(rnd['label'])} — {how}. {c['questions']} Questions, {c['screenshots']} "
              f"screenshots. The Portal confirmed it at {reply['received_at']} (UTC), "
              f"publish id {reply['publish_id']}.")
    return {"ok": True, "sent": "page", "page": saved.get("slug"), "portal": url, "round": rnd, "counts": c,
            "publish_id": reply["publish_id"], "received_at": reply["received_at"], "report": report}


def main(argv: list[str]) -> int:
    root = Path(arg(argv, "--root", ".")).resolve()
    words = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in
                                                                           ("--root", "--payload"))]
    try:
        if words[:1] == ["page"] and words[1:2] not in (["send"], ["discard"]):
            rest = words[2:] if words[1:2] == ["plan"] else words[1:]
            if len(rest) != 1:
                raise Stop("Name one page: `page plan <slug>` (the `slug:` line of its YAML).")
            result = cmd_page_plan(root, rest[0])
        elif words[:2] == ["page", "send"]:
            result = cmd_page_send(root, payload_arg(argv))
        elif words[:2] == ["page", "discard"]:
            result = cmd_discard(payload_arg(argv), "page")
        elif words[:2] == ["dashboard", "plan"]:
            result = cmd_plan(root, "--refresh" in argv)
        elif words[:2] == ["dashboard", "send"]:
            result = cmd_send(root, payload_arg(argv))
        elif words[:2] == ["dashboard", "discard"]:
            result = cmd_discard(payload_arg(argv))
        else:
            sys.stdout.reconfigure(encoding="utf-8")
            print(__doc__)
            return 2
    except Stop as e:
        out({"ok": False, "error": str(e)})
        return 1
    except yaml.YAMLError as e:
        out({"ok": False, "error": f"A YAML file could not be read: {e}. Fix it, then run again. Nothing was sent."})
        return 1
    except UnicodeDecodeError as e:
        out({"ok": False, "error": f"A file is not UTF-8 text ({e.reason}). Nothing was sent."})
        return 1
    except OSError as e:
        out({"ok": False, "error": f"A file could not be read or written: {e}. Nothing was sent."})
        return 1
    except httpx.HTTPError as e:
        out({"ok": False, "error": f"The request to the Portal failed ({type(e).__name__}). Nothing was sent."})
        return 1
    out(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
