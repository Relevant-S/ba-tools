"""portal-publish — send the project's Dashboard to the Relevant Clients Portal. Every command prints one JSON line.

    uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py <command> [--root <project>]

Commands (run from the project root, or pass --root):
  dashboard plan [--refresh]          build the dashboard, make the payload, check it against the contract, send it
                                      to the Portal as a dry run and print what the Client will read (client_list).
                                      Writes the payload to a temp file outside the repo and prints its path.
  dashboard send --payload <file>     after the BA says yes: send that same payload for real, report, delete the file
  dashboard discard --payload <file>  after the BA says no: delete the payload file, send nothing
  page <slug>                         not built yet (Story 4.3)

Settings: tools.portal.url in docs/BA/specs/.ba-profile.yml; PORTAL_PUBLISH_KEY in .env at the repo root, which git
must ignore. The key is never printed. The "Waiting on you" list comes only from the Portal's dry-run reply.
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


def map_facts(data: dict) -> tuple[dict, list[str], list[dict], dict]:
    """From the built map: each Feature bubble's stage, done date and area; the areas and release rows in order;
    each Feature's releases. Two products are merged by name, first one first."""
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
            if r["name"] not in seen:
                seen.add(r["name"])
                rows.append({"name": r["name"], "released": bool(r.get("released"))})
    order = {r["name"]: i for i, r in enumerate(rows)}
    releases: dict[str, list[str]] = {}
    for card in board.get("cards") or []:
        if card.get("kind") == "feature" and card.get("row") and card["row"] != "none":
            got = releases.setdefault(card["fid"], [])
            if card["row"] not in got:
                got.append(card["row"])
    for fid in releases:
        releases[fid].sort(key=lambda n: order.get(n, len(order)))
    return bubbles, areas, rows, releases


def build_payload(root: Path, prof: dict, sent_at: str | None = None):
    """The dashboard/1 payload (data-contract §10), where each sent value came from, counts of what was left out,
    and warnings."""
    d = yaml.safe_load((root / DASHBOARD).read_text(encoding="utf-8")) or {}
    bubbles, areas, rows, releases = map_facts(read_map(root))
    warnings: list[str] = []
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
    target = url + ENDPOINT + ("?dry_run=1" if dry_run else "")
    try:
        with http_client() as client:
            r = client.post(target, content=body, headers={"Authorization": f"Bearer {key}",
                                                           "Content-Type": "application/json",
                                                           "Accept": "application/json"})
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
                        "send is not there, run `dashboard send` again with the same --payload file (it was "
                        "kept).") from None
    try:
        doc = r.json()
    except ValueError:
        doc = None
    if r.status_code == 200:
        if not isinstance(doc, dict) or checks.check_reply(doc, REPLY) or doc.get("dry_run") is not dry_run:
            raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                       "Nothing more was sent.")
        return doc
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict) or not err.get("code"):
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). Nothing more was sent.")
    code = str(err["code"])
    lines = [f"The Portal refused the send ({code}): {text(err.get('message')) or 'no message'}"]
    details = [x for x in (err.get("details") or []) if isinstance(x, dict)]
    lines += [f"- {ln}" for ln in problem_lines(details, sources)]
    if code in NEXT_STEP:
        lines.append(NEXT_STEP[code])
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
    """Only a file `dashboard plan` wrote: portal-publish-*.json in the system temp folder. Nothing else is
    read or deleted."""
    p = arg(argv, "--payload")
    if not p:
        raise Stop("--payload <file> is required (the path `dashboard plan` printed).")
    path = Path(p).resolve()
    if not path.match(PAYLOAD_GLOB) or path.parent != Path(tempfile.gettempdir()).resolve():
        raise Stop(f"{p} is not a payload file `dashboard plan` wrote (portal-publish-*.json in the temp folder "
                   f"{tempfile.gettempdir()}). Nothing was sent or deleted.")
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


def cmd_send(root: Path, path: Path) -> dict:
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


def cmd_discard(path: Path) -> dict:
    existed = path.exists()
    path.unlink(missing_ok=True)
    return {"ok": True, "sent": None, "deleted": str(path) if existed else None,
            "report": "Nothing was sent. The payload file was deleted."}


def main(argv: list[str]) -> int:
    root = Path(arg(argv, "--root", ".")).resolve()
    words = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in
                                                                           ("--root", "--payload"))]
    try:
        if words[:1] == ["page"]:
            raise Stop("`portal-publish page <slug>` is not built yet (it comes with the Clarification pages, "
                       "Story 4.3). Only `dashboard` works today.")
        if words[:2] == ["dashboard", "plan"]:
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
