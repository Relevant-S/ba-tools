"""portal-publish — send the project's Dashboard, or one Clarification page, to the Relevant Clients Portal.
Every command prints one JSON line.

    uv run --project <skills>/portal-publish python <skills>/portal-publish/publish.py <command> [--root <project>]

Commands (run from the project root, or pass --root):
  dashboard plan [--refresh] [--product <name>]
                                      build the dashboard and make one dashboard/2 payload per product (or only the
                                      product named). Check every payload against the contract first; then, per
                                      product, ask the Portal which project its key opens (GET /status), send the
                                      payload as a dry run and print what the Client will read (client_list).
                                      Writes each payload to a temp file outside the repo and prints its path.
  dashboard send --payload <file>     after the BA says yes to that product: send that same payload for real,
                                      report, delete the file
  dashboard discard --payload <file>  after the BA says no to that product: delete the payload file, send nothing
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

Settings: tools.portal.url in docs/BA/specs/.ba-profile.yml; the Publish key in .env at the repo root, which git
must ignore. A repo with one product uses PORTAL_PUBLISH_KEY. A repo with two or more products sends each product to
its own Portal project: tools.portal.products in the profile names, per product, the .env variable that holds that
project's key. Pages use the first product's key there. Keys are never printed. The "Waiting on you" list and the
page's Client view come only from the Portal's dry-run reply.
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
STATUS_ENDPOINT = "/api/v1/status"
CONTRACT = "dashboard/2"
REPLY = "publish-reply/1"
STATUS = "status/1"
MAX_BYTES = 5 * 1024 * 1024      # the Portal refuses a Dashboard over 5 MB (DASHBOARD_MAX_BYTES, payload_too_large)
DEFAULT_KEY = "PORTAL_PUBLISH_KEY"
KEY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
OPEN_TICKETS_SHOWN = 5           # an area's open tickets, as the BA page shows them
STALE_SECONDS = 24 * 3600
TIMEOUT = 30.0
BUILD_TIMEOUT = 600                # seconds for each build step
PAYLOAD_GLOB = "portal-publish-*.json"
PAYLOAD_MAX_AGE = 24 * 3600
SETUP_HINT = "Run `ba-setup project`"
STAGE_NAME = {"concept": "Concept", "spec": "Spec & design", "ready": "Ready for dev", "dev": "In dev",
              "qa": "In QA", "done": "Done"}

def invalid_key_step(key_name: str) -> str:
    return (f"The key in .env ({key_name}) is not this Project's key. Ask an Admin for the key "
            "(Admin → Projects → the Project → Publishing → Regenerate key), put it in .env, and run again.")


# What to do next, per Portal error code. The Portal's own message is shown first.
NEXT_STEP = {
    "invalid_key": invalid_key_step(DEFAULT_KEY),
    "project_archived": "This Project is archived in the Portal, so it takes no sends. Ask an Admin to restore it.",
    "contract_invalid": "Fix each field listed, then run `dashboard plan` again.",
    "contract_version_not_accepted": "This Portal does not accept the contract this ba-tools version sends. "
                                     "Update ba-tools, or ask an Admin to update the Portal.",
    "payload_too_large": "The Dashboard is too big to send. Remove or shorten features or items, then run again.",
    "bad_request": "The Portal could not read the send. Run `dashboard plan` again; if it repeats, report it.",
    "server_error": "Something went wrong in the Portal. Nothing was stored. Try again later.",
}


def key_steps(key_name: str, steps: dict | None = None) -> dict:
    """The next steps, with the invalid_key step naming the .env variable the key came from."""
    return {**(NEXT_STEP if steps is None else steps), "invalid_key": invalid_key_step(key_name)}


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


def settings(root: Path) -> tuple[str, dict, dict]:
    """The Portal address, the profile and the values in .env. Stops before anything is built or sent.
    The keys themselves are read by read_keys."""
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
                   "the Publish key in .env.")
    if not env_is_ignored(root):
        raise Stop(".env is not ignored by git (it is tracked, or .gitignore does not list it). The Publish key "
                   "must never be committed: add .env to .gitignore (and `git rm --cached .env` if it was "
                   "committed), then run again. Nothing was sent.")
    return url, prof, read_env_file(env)


def key_map(prof: dict) -> dict[str, str]:
    """tools.portal.products: product name → the name of the .env variable that holds that Portal project's key.
    Empty when the profile has none."""
    portal = (prof.get("tools") or {}).get("portal") or {}
    found = portal.get("products") if isinstance(portal, dict) else None
    if found in (None, "", {}):
        return {}
    if not isinstance(found, dict) or not all(
            isinstance(k, str) and k.strip() and isinstance(v, str) and KEY_NAME.fullmatch(v.strip())
            for k, v in found.items()):
        raise Stop(f"tools.portal.products in {PROFILE} must name, for each product, the .env variable that holds "
                   "its Portal project's key, for example {AcmeLending: PORTAL_PUBLISH_KEY_ACME}. "
                   f"{SETUP_HINT} to fix it. Nothing was sent.")
    names = {k.strip(): v.strip() for k, v in found.items()}
    seen: dict[str, str] = {}
    for product, name in names.items():           # one key per product: two products never share a project
        if name in seen:
            raise Stop(f"tools.portal.products in {PROFILE} gives {seen[name]} and {product} the same .env "
                       f"variable ({name}), so both would go to the same Portal project. Each product needs its "
                       f"own Portal project and its own key. {SETUP_HINT} to fix it. Nothing was sent.")
        seen[name] = product
    return names


def key_names(prof: dict, products: list[str], only: str | None = None) -> dict[str, str]:
    """Which .env variable holds each product's key (only the product `only`, when given). A repo with one
    product: its tools.portal.products entry, else PORTAL_PUBLISH_KEY. Two or more: each needs its own entry, or
    the run stops before anything is sent."""
    found = key_map(prof)
    if len(products) == 1 and products[0] not in found:
        return {products[0]: DEFAULT_KEY}
    missing = [p for p in ([only] if only else products) if p not in found]
    if missing:
        example = ", ".join(f"{p}: PORTAL_PUBLISH_KEY_{re.sub(r'[^A-Z0-9]+', '_', p.upper()).strip('_')}"
                            for p in missing)
        raise Stop(f"This repo has {len(products)} products ({', '.join(products)}). Each goes to its own Portal "
                   "project, with that project's own key. tools.portal.products in "
                   f"{PROFILE} names no key for: {', '.join(missing)}. Add one entry per product, naming the .env "
                   f"variable that holds its key, for example {{{example}}}. {SETUP_HINT} to set it up. "
                   "Nothing was sent.")
    return {p: found[p] for p in ([only] if only else products)}


def read_keys(env: dict, names: dict[str, str]) -> dict[str, str]:
    """Each product's key from .env. A missing one stops the run, naming the variable."""
    keys = {}
    for product, name in names.items():
        key = env.get(name, "").strip()
        if not key:
            whose = "" if name == DEFAULT_KEY else f" (the Publish key for {product})"
            raise Stop(f".env has no {name}{whose}. {SETUP_HINT}: it tells you where to get the key. "
                       "Nothing was sent.")
        keys[product] = key
    return keys


def page_key(prof: dict, env: dict) -> tuple[str, str]:
    """The key for a page send, and its .env variable. With tools.portal.products, the first product's key (until
    pages are sent per product); else PORTAL_PUBLISH_KEY."""
    found = key_map(prof)
    name = next(iter(found.values())) if found else DEFAULT_KEY
    return read_keys(env, {"page": name})["page"], name


def profile_products(prof: dict) -> list[str]:
    """The product names, read the way ba-dashboard's map/build.py reads them: tools.dashboard.map.products, else
    the profile's products that have a jira_project. Used to check the keys before the build."""
    dash = (prof.get("tools") or {}).get("dashboard") or {}
    mapped = (dash.get("map") or {}).get("products") if isinstance(dash, dict) and isinstance(
        dash.get("map") or {}, dict) else None
    if isinstance(mapped, dict) and mapped:
        return list(dict.fromkeys(text(v) for v in mapped.values() if text(v)))
    return list(dict.fromkeys(text(p.get("name")) for p in prof.get("products") or []
                              if isinstance(p, dict) and p.get("jira_project") and text(p.get("name"))))


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


def item_key(kind: str, parent: str, title: str) -> str:
    """The dashboard/2 Item key: sha1("<kind>|<parent>|<title>"), first 12 characters. The parent is in it, so two
    Items with one title under two parents do not clash."""
    return hashlib.sha1(f"{kind}|{parent}|{title.strip()}".encode("utf-8")).hexdigest()[:12]


def text(v) -> str:
    return "" if v is None else str(v).strip()


def jira_text(v) -> str:
    """Text copied from Jira, with HTML entities (&amp;) turned back into characters. The Portal escapes it."""
    return html.unescape(text(v))


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


def in_product(row: dict, product: str) -> bool:
    """A row of the map belongs to a product's send when its prod is that product or "Both"."""
    return text(row.get("prod")) in (product, "Both")


def map_products(data: dict) -> list[str]:
    """The products of the built map, in its order (DATA.products)."""
    found = [text(p) for p in data.get("products") or [] if text(p)]
    if not found:
        raise Stop(f"{MAP_PAGE} names no products. Run `dashboard plan` again. Nothing was sent.")
    return list(dict.fromkeys(found))


def jira_base(data: dict, prof: dict) -> str:
    """The Jira site, as the BA page's JIRA_BASE: the scheme and host of the first area's Jira search link.
    Without one, the profile's jira.site. Without both, the run stops."""
    for e in data.get("epics") or []:
        j = e.get("jira") if isinstance(e, dict) else None
        search = text(j.get("search")) if isinstance(j, dict) else ""
        if search:
            u = urllib.parse.urlsplit(search)
            if u.scheme and u.netloc:
                return f"{u.scheme}://{u.netloc}"
    site = prof.get("jira")
    site = text(site.get("site")) if isinstance(site, dict) else ""
    site = re.sub(r"^[a-z][a-z0-9+.-]*://", "", site, flags=re.I).split("/")[0].strip()
    if site:
        return f"https://{site}"
    raise Stop("There is no Jira site address to link tickets to: the map has no Jira areas "
               f"(docs/BA/mind-map/areas.json), and {PROFILE} has no jira.site. Add jira.site to the profile "
               "(for example yourcompany.atlassian.net), or run `dashboard plan --refresh` to read Jira. "
               "Nothing was sent.")


def ticket(t: dict) -> dict:
    """A ticket as dashboard/2 sends it. The map's `who` is the assignee."""
    out = {"key": text(t.get("key")), "summary": jira_text(t.get("summary")), "status": jira_text(t.get("status")),
           "stage": text(t.get("stage"))}
    put(out, "assignee", jira_text(t.get("who") or t.get("assignee")))
    return out


def open_tickets(opens: list) -> list[dict]:
    """An area's open tickets as the BA page shows them: being built or tested first (Jira category
    `indeterminate`), then newest updated; the first 5. Rows with no key (an older areas.json) are not sent."""
    keyed = [o for o in opens if isinstance(o, dict) and text(o.get("key"))]
    keyed.sort(key=lambda o: text(o.get("updated")), reverse=True)        # stable: ties keep Jira's order
    keyed.sort(key=lambda o: o.get("category") != "indeterminate")
    return [{"key": text(o["key"]), "summary": jira_text(o.get("summary")), "status": jira_text(o.get("status")),
             "stage": "dev" if o.get("category") == "indeterminate" else "ready"}
            for o in keyed[:OPEN_TICKETS_SHOWN]]


def area_jira(j: dict) -> dict:
    """An area's Jira facts. The search link is not sent (jira_base is)."""
    opens = [o for o in j.get("open") or [] if isinstance(o, dict)]
    out: dict = {}
    put(out, "description", jira_text(j.get("description")))
    out["done"] = int(j.get("done") or 0)
    out["in_progress"] = sum(1 for o in opens if o.get("category") == "indeterminate")
    out["open"] = len(opens)
    put(out, "last_done", text(j.get("lastDone"))[:10])
    put(out, "shipped", [{"key": text(s.get("key")), "summary": jira_text(s.get("summary")),
                          "date": text(s.get("date"))[:10]}
                         for s in j.get("shipped") or [] if isinstance(s, dict) and text(s.get("date"))])
    put(out, "open_tickets", open_tickets(opens))
    return out


def area_of_epic(e: dict) -> dict:
    """One area (an entry of DATA.epics — a Jira component, "No area" or "Not linked yet")."""
    area = {"id": text(e.get("id")), "name": jira_text(e.get("label")), "quiet": not e.get("active", True)}
    if e.get("noarea"):
        area["special"] = "no_area"
    elif e.get("loose"):
        area["special"] = "not_linked"
    if isinstance(e.get("jira"), dict):
        area["jira"] = area_jira(e["jira"])
    return area


def build_payload(root: Path, prof: dict, product: str | None = None, data: dict | None = None,
                  sent_at: str | None = None):
    """One product's dashboard/2 payload (contract dashboard-2.md), built from the BA page's own data; where each
    sent value came from; counts of what was left out; warnings. Rows whose prod is the product or "Both" go in."""
    d = yaml.safe_load((root / DASHBOARD).read_text(encoding="utf-8")) or {}
    data = read_map(root) if data is None else data
    products = map_products(data)
    if product is None:
        if len(products) > 1:
            raise Stop(f"This repo has {len(products)} products ({', '.join(products)}): name one. Nothing was sent.")
        product = products[0]
    epics = [e for e in data.get("epics") or [] if isinstance(e, dict)]
    board = data.get("board") or {}
    warnings: list[str] = []
    sources: dict[str, tuple[str, str, dict]] = {}   # "/features/0" -> (file, row label, {field: source field})
    left_out = {"features": 0, "items": 0, "cards": 0}

    bubbles, area_of = {}, {}          # bubble id -> the map's bubble, and the id of the area it sits in
    for e in epics:
        for b in e.get("features") or []:
            bubbles[b["id"]] = b
            area_of[b["id"]] = text(e.get("id"))

    features, hidden = [], set()
    for f in d.get("features") or []:
        fid = text(f.get("id")) or slug(text(f.get("area")))
        if not in_product(f, product):
            continue
        if hidden_flag(f):
            hidden.add(fid)
            left_out["features"] += 1
            continue
        b = bubbles.get(fid)
        if b is None or "feature" not in b:
            raise Stop(f"{MAP_PAGE} has no bubble for the feature '{text(f.get('area'))}' (id {fid}). "
                       "Run `dashboard plan` again. Nothing was sent.")
        summary_from = "client_s" if text(f.get("client_s")) else "s"
        feat: dict = {"id": fid, "area": area_of[fid]}
        put(feat, "title", text(f.get("area")))
        put(feat, "short", text(f.get("short")))
        put(feat, "summary", text(f.get(summary_from)))
        opens = f.get("open") or []
        opens = opens if isinstance(opens, list) else [opens]
        put(feat, "open", [text(o) for o in opens if text(o)])
        settled = (b.get("feature") or {}).get("settled")
        if isinstance(settled, int) and settled + len(feat.get("open", [])):
            feat["answered"] = {"done": settled, "total": settled + len(feat.get("open", []))}
        put(feat, "stage", text(b.get("stageKey")))
        put(feat, "done_date", text(b.get("doneDate"))[:10])
        clar = f.get("clar")
        put(feat, "clar_url", text(clar.get("url") if isinstance(clar, dict) else clar))
        feat["tickets"] = [ticket(t) for t in b.get("tickets") or [] if isinstance(t, dict)]
        map_field = f"(from the map build, {MAP_PAGE})"
        sources[f"/features/{len(features)}"] = (DASHBOARD, f"features '{text(f.get('area')) or fid}'", {
            "id": "id", "title": "area", "short": "short", "summary": summary_from, "open": "open",
            "clar_url": "clar.url", "stage": f"stage {map_field}", "area": f"area {map_field}",
            "answered": f"answered questions {map_field}", "done_date": f"done date {map_field}",
            "tickets": f"Jira tickets {map_field}"})
        features.append(feat)
    sent_features = {f["id"]: f for f in features}

    topics = []
    for e in epics:
        for b in e.get("features") or []:
            if "feature" in b or not in_product(b, product):
                continue
            topic = {"id": text(b.get("id")), "area": text(e.get("id"))}
            put(topic, "title", text(b.get("label")))
            put(topic, "stage", text(b.get("stageKey")))
            topic["tickets"] = [ticket(t) for t in b.get("tickets") or [] if isinstance(t, dict)]
            sources[f"/topics/{len(topics)}"] = (
                (MAP_PAGE, "the \"Not linked yet\" bubble", {}) if e.get("loose") else
                (DASHBOARD, f"topics '{topic.get('title') or topic['id']}'", {"title": "title", "id": "id"}))
            topics.append(topic)
    sent_topics = {t["id"]: t for t in topics}
    parents = set(sent_features) | set(sent_topics)
    loose = next((b["id"] for e in epics if e.get("loose") for b in e.get("features") or []), "unlinked")

    items = []
    for listname, kind in (("awaiting", "waiting"), ("agenda", "agenda")):
        for it in d.get(listname) or []:
            if not in_product(it, product):
                continue
            named = text(it.get("feature"))
            parent = named if named and named in bubbles and named != loose else loose
            if it.get("done") or hidden_flag(it) or named in hidden or parent not in parents:
                left_out["items"] += 1
                continue
            text_from = "client_s" if text(it.get("client_s")) else "s"
            title = text(it.get("t"))
            item: dict = {"key": item_key(kind, parent, title), "kind": kind, "parent": parent}
            put(item, "who", text(it.get("who")))
            put(item, "since", text(it.get("since")))
            put(item, "title", title)
            put(item, "text", text(it.get(text_from)))
            put(item, "how_to_send", text(it.get("l")))
            sources[f"/items/{len(items)}"] = (DASHBOARD, f"{listname} '{title or '?'}'", {
                "key": "t (the item key is made from its kind, parent and title)", "kind": listname,
                "parent": "feature", "who": "who", "since": "since", "title": "t", "text": text_from,
                "how_to_send": "l"})
            items.append(item)
    left_out["items"] += sum(1 for t in d.get("todos") or [] if in_product(t, product))

    releases = []
    for r in (board.get("releases") or {}).get(product) or []:
        rel: dict = {"name": jira_text(r.get("name"))}
        put(rel, "date", text(r.get("date"))[:10])
        rel.update(released=bool(r.get("released")), overdue=bool(r.get("overdue")))
        sources[f"/releases/{len(releases)}"] = ("Jira", f"the release '{rel['name']}'", {"name": "its name"})
        releases.append(rel)
    release_names = {r["name"] for r in releases}

    no_area = next((text(e.get("id")) for e in epics if e.get("noarea")), "noarea")
    by_name = {jira_text(e.get("label")): text(e.get("id")) for e in epics
               if text(e.get("prod")) == product and not e.get("noarea") and not e.get("loose")}
    extra_areas: dict[str, dict] = {}   # a card's area that is not in the map's areas (Jira has no such component)
    cards, foreign = [], []
    for c in board.get("cards") or []:
        if not isinstance(c, dict) or not in_product(c, product):
            continue
        kind = text(c.get("kind"))
        fid = text(c.get("fid"))
        if kind == "feature" and fid in sent_topics:
            # The map gives a topic a "feature" card too. dashboard/2 ties a feature card to a Feature, so a
            # topic's card goes as an "other" card, under the topic's name and in the topic's area.
            kind, area = "other", sent_topics[fid]["area"]
        elif kind == "feature":
            if fid not in sent_features:            # client: false (or not in this product): its card stays out
                left_out["cards"] += 1
                continue
            area = sent_features[fid]["area"]
        else:
            name = jira_text(c.get("area")) or "No area"
            area = no_area if name == "No area" else by_name.get(name)
            if area is None:
                area = f"board:{name}"
                extra_areas.setdefault(area, {"id": area, "name": name, "quiet": False})
        row = text(c.get("row"))
        release = None if row in ("", "none") else jira_text(row)
        title = jira_text(c.get("title")) or ("Other tickets" if kind == "other" else "")
        if release is not None and release not in release_names:
            # The BA page shows only this product's releases as rows, so it never shows this card here.
            left_out["cards"] += 1
            foreign.append(f"'{title}' ({release})")
            continue
        card: dict = {"id": text(c.get("id")), "kind": kind, "area": area, "release": release}
        put(card, "title", title)
        card.update(stage=text(c.get("stage")), blocked=bool(c.get("blocked")))
        put(card, "done_date", text(c.get("doneDate"))[:10])
        if kind == "feature":
            card["feature"] = fid
        elif kind == "epic":
            put(card, "epic", text(c.get("epic")))
        card["tickets"] = [ticket(t) for t in c.get("tickets") or [] if isinstance(t, dict)]
        sources[f"/cards/{len(cards)}"] = (MAP_PAGE, f"the Board card '{title}' ({release or 'Not planned yet'})", {})
        cards.append(card)
    if foreign:
        warnings.append(f"{product}: {len(foreign)} Board card(s) sit in a release of another product, so the BA "
                        f"page does not show them on {product}'s Board, and they are not sent: "
                        + "; ".join(foreign) + ". To send them, put their tickets in one of this product's "
                        "releases in Jira.")

    # The product's areas, plus any area of another product that a sent Feature, topic or card sits in.
    wanted = {x["area"] for x in features + topics + cards}
    areas = []
    for e in epics:
        if in_product(e, product) or text(e.get("id")) in wanted:
            sources[f"/areas/{len(areas)}"] = (MAP_PAGE, f"the area '{jira_text(e.get('label'))}'", {
                "name": "its name (from Jira)", "jira": "its Jira facts"})
            areas.append(area_of_epic(e))
    for extra in extra_areas.values():
        sources[f"/areas/{len(areas)}"] = (MAP_PAGE, f"the Board column '{extra['name']}'", {})
        areas.append(extra)

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
    payload.update(jira_base=jira_base(data, prof), areas=areas, features=features, topics=topics, items=items,
                   releases=releases, cards=cards, client_contacts=people)
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
        "topics": f"the map build ({MAP_PAGE}) → topics", "areas": f"the map build ({MAP_PAGE}) → areas",
        "releases": f"the map build ({MAP_PAGE}) → releases", "cards": f"the map build ({MAP_PAGE}) → Board cards",
        "jira_base": f"the Jira site (the first Jira area in {MAP_PAGE}, else jira.site in {PROFILE})",
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


def local_check(payload: dict, body: bytes, sources: dict, product: str = "") -> None:
    what = f"The {product} Dashboard" if product else "The Dashboard"
    found = checks.check_publish(payload)
    if found:
        lines = problem_lines(found["details"], sources)
        raise Stop(f"{what} does not match the contract, so nothing was sent. Fix these, then run "
                   "`dashboard plan` again:\n" + "\n".join(f"- {ln}" for ln in lines))
    if len(body) > MAX_BYTES:
        raise Stop(f"{what} is {len(body) / 1e6:.1f} MB; the Portal takes at most 5 MB. Nothing was sent.")


def encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- the Portal

def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT)


def post(url: str, key: str, body: bytes, dry_run: bool, sources: dict, key_name: str = DEFAULT_KEY) -> dict:
    """POST the payload. Returns the checked 200 reply; anything else stops the run."""
    return exchange(url, ENDPOINT, dry_run, sources, "dashboard",
                    lambda client, target: client.post(target, content=body, headers={
                        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                        "Accept": "application/json"}), next_step=key_steps(key_name))


def project_name(url: str, key: str, key_name: str, contract: str | None = CONTRACT) -> str:
    """GET /status with one product's key: the name of the Portal project that key opens. Sends no Dashboard.
    Stops when the Portal does not answer, refuses the key, or does not accept `contract` (dashboard/2; None skips
    that check, for a page)."""
    try:
        with http_client() as client:
            r = client.get(url + STATUS_ENDPOINT, headers={"Authorization": f"Bearer {key}",
                                                            "Accept": "application/json"})
    except httpx.InvalidURL:
        raise Stop(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it. "
                   "Nothing was sent.") from None
    except httpx.RequestError:
        raise Stop(f"The Portal is not reachable at {url}. Check that it is running and that tools.portal.url is "
                   "right. Nothing was sent.") from None
    try:
        doc = r.json()
    except ValueError:
        doc = None
    if r.status_code == 200:
        if not isinstance(doc, dict) or checks.check_reply(doc, STATUS):
            raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). It may be an older Portal. "
                       "Nothing was sent.")
        if contract and contract not in doc["accepted_contracts"]:
            raise Stop(f"The Portal at {url} does not accept {contract} yet (it accepts "
                       f"{', '.join(doc['accepted_contracts'])}). Ask an Admin to update the Portal. "
                       "Nothing was sent.")
        return doc["project_name"]
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict) or not err.get("code"):
        raise Stop(f"The Portal's reply was not understood (HTTP {r.status_code}). Nothing was sent.")
    code = str(err["code"])
    lines = [f"The Portal refused the key in {key_name} ({code}): {text(err.get('message')) or 'no message'}"]
    steps = key_steps(key_name)
    if code in steps:
        lines.append(steps[code])
    lines.append("Nothing was sent.")
    raise Stop("\n".join(lines))


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


def client_list(reply: dict, product: str = "", project: str = "") -> str:
    """The dry-run list for one product, from the Portal's own reply (a dashboard/2 Client view). Ticket lists are
    counted, never printed."""
    view = reply["client_view"]
    if not isinstance(view, dict) or "cards" not in view:
        raise Stop("The Portal's dry-run reply is not a dashboard/2 view. It may be an older Portal. "
                   "Nothing was sent.")
    area_names = {a["id"]: a["name"] for a in view["areas"]}
    titles = {x["id"]: x["title"] for x in view["features"] + view["topics"]}
    out_lines = [f"{product} → Portal project \"{project}\"", ""] if product else []
    out_lines += ["What the Client will read — the Portal's own dry run. Nothing is stored yet.", ""]
    active = [a for a in view["areas"] if not a["quiet"]]
    quiet = [a for a in view["areas"] if a["quiet"]]
    out_lines.append(f"Areas ({len(view['areas'])}: {len(active)} active, {len(quiet)} quiet):")
    for a in active:
        j = a.get("jira")
        out_lines.append(f"- {a['name']}" + (f" — {j['open']} open tickets in Jira ({j['in_progress']} being built "
                                             f"or tested), {j['done']} done" if j else ""))
    if quiet:
        out_lines.append("- Quiet: " + ", ".join(a["name"] for a in quiet))
    out_lines += ["", f"Features ({len(view['features'])}):"]
    for f in view["features"]:
        head = f"- {f['title']}" + (f" ({f['short']})" if f.get("short") else "")
        head += f" — {STAGE_NAME.get(f['stage'], f['stage'])} · area: {area_names.get(f['area'], f['area'])}"
        if f.get("answered"):
            head += f" · {f['answered']['done']} of {f['answered']['total']} questions answered"
        head += f" · Jira tickets: {len(f['tickets'])}" if f.get("tickets") else ""
        out_lines.append(head)
        out_lines.append(indent(plain(f["summary"]), "    "))
        for q in f.get("open") or []:
            out_lines.append(f"    Open question: {plain(q)}")
        page = f.get("page")
        out_lines.append("    Clarification page: " + (f"Published — {page['answered']} of {page['total']} answered"
                                                        if page else "Questions coming"))
        if f.get("hiddenByDoneFilter"):
            out_lines.append("    (Done over 2 weeks ago: hidden while \"Hide done > 2 weeks\" is on, the default)")
    out_lines += ["", f"Topics ({len(view['topics'])}):"]
    if not view["topics"]:
        out_lines.append("- none")
    for t in view["topics"]:
        out_lines.append(f"- {t['title']} — {STAGE_NAME.get(t['stage'], t['stage'])} · area: "
                         f"{area_names.get(t['area'], t['area'])}"
                         + (f" · Jira tickets: {len(t['tickets'])}" if t.get("tickets") else ""))
    kinds = {k: sum(1 for c in view["cards"] if c["kind"] == k) for k in ("feature", "epic", "other")}
    tickets = sum(len(c["tickets"]) for c in view["cards"])
    out_lines += ["", f"Board: {len(view['cards']):,} cards ({kinds['feature']} feature / {kinds['epic']} epic / "
                      f"{kinds['other']} other), {tickets:,} tickets, in {len(view['releases'])} releases "
                      "and \"Not planned yet\"."]
    groups = (("Waiting on you", "waitingOnYou"), ("Next-call agenda", "onAgenda"))
    for label, flag in groups:
        shown = [i for i in view["items"] if i.get(flag)]
        out_lines += ["", f"{label} ({len(shown)}):"]
        if not shown:
            out_lines.append("- none")
        for i in shown:
            out_lines.append(f"- {i['title']} — under {titles.get(i['parent'], i['parent'])}")
            if i.get("text"):
                out_lines.append(indent(plain(i["text"]), "    "))
            if i.get("how_to_send"):
                out_lines.append(f"    How to send: {i['how_to_send']}")
    other = [i for i in view["items"] if not i.get("waitingOnYou") and not i.get("onAgenda")]
    if other:
        out_lines += ["", f"Also shown — waiting on someone else ({len(other)}):"]
        out_lines += [f"- {i['title']}" + (f" — {i['who']}" if i.get("who") else "") for i in other]
    names = reply.get("client_contact_names") or []
    out_lines += ["", f"Client contacts ({len(names)}): " + (", ".join(names) if names else "none")]
    return "\n".join(out_lines)


# ---------------------------------------------------------------- commands

def write_payload(body: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix="portal-publish-", suffix=".json")
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    return Path(name)


def save_dashboard(product: str, project: str, url: str, key_name: str, body: bytes) -> Path:
    """The payload file `dashboard send` reads: the exact bytes to send (`publish`), plus which product, Portal
    project and .env variable they belong to. The sent payload itself holds no product."""
    return write_payload(json.dumps({"kind": "dashboard", "product": product, "project_name": project,
                                     "portal": url, "key_name": key_name, "publish": body.decode("utf-8")},
                                    ensure_ascii=False).encode("utf-8"))


def cmd_plan(root: Path, refresh: bool, only: str | None = None) -> dict:
    url, prof, env = settings(root)
    planned = profile_products(prof)
    if only and planned and only not in planned:
        raise Stop(f"There is no product called '{only}'. This repo's products: {', '.join(planned)}. "
                   "Nothing was sent.")
    if planned:                                   # stop on a missing key before the build, as before
        read_keys(env, key_names(prof, planned, only))
    clean_old_payloads()
    run_build(root, refresh)
    warnings = []
    if not refresh:
        w = stale_warning(root)
        if w:
            warnings.append(w)
    data = read_map(root)
    products = map_products(data)
    if only and only not in products:
        raise Stop(f"There is no product called '{only}'. This repo's products: {', '.join(products)}. "
                   "Nothing was sent.")
    names = key_names(prof, products, only)
    products = [only] if only else products
    keys = read_keys(env, names)
    sent_at = now_utc()
    built = []
    for product in products:                      # every product's local check passes before anything is sent
        payload, sources, left_out, more = build_payload(root, prof, product, data, sent_at)
        body = encode(payload)
        local_check(payload, body, sources, product if len(products) > 1 or only else "")
        warnings += [w for w in more if w not in warnings]
        built.append((product, body, sources, left_out))
    results = []
    owner: dict[str, str] = {}                    # Portal project → the product whose key opened it
    for product, body, sources, left_out in built:
        project = project_name(url, keys[product], names[product])
        if project in owner:
            raise Stop(f"The keys for {owner[project]} ({names[owner[project]]}) and {product} ({names[product]}) "
                       f"both open the same Portal project, \"{project}\". Each product needs its own Portal "
                       f"project. Ask an Admin for the right key for one of them, put it in .env, and run "
                       "`dashboard plan` again. Nothing was sent.")
        owner[project] = product
        reply = post(url, keys[product], body, dry_run=True, sources=sources, key_name=names[product])
        results.append((product, project, body, reply, left_out))
    out_products = []
    for product, project, body, reply, left_out in results:
        path = save_dashboard(product, project, url, names[product], body)
        out_products.append({"product": product, "project_name": project, "payload": str(path),
                             "counts": reply["counts"], "left_out": left_out,
                             "client_list": client_list(reply, product, project)})
    return {"ok": True, "portal": url, "sent_at": sent_at, "warnings": warnings, "products": out_products}


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


def read_saved(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def payload_kind(path: Path) -> str | None:
    """"page" for a file `page plan` wrote, "dashboard" for one `dashboard plan` wrote, else None."""
    doc = read_saved(path) or {}
    return doc.get("kind") if doc.get("kind") in ("page", "dashboard") else None


def check_kind(path: Path, want: str, action: str) -> None:
    """Stop, deleting nothing, when a page payload is given to a dashboard command or the reverse."""
    got = payload_kind(path)
    if got and got != want:
        raise Stop(f"{path} is a {got} payload, not a {want} one: use `{got} {action}`. Nothing was sent or "
                   "deleted.")


def read_dashboard_payload(path: Path) -> tuple[dict, bytes]:
    """The file `dashboard plan` wrote: what it says about the send, and the exact bytes to send."""
    if not path.exists():
        raise Stop(f"{path} is not there. Run `dashboard plan` again. Nothing was sent.")
    saved = read_saved(path)
    if not (saved and saved.get("kind") == "dashboard" and isinstance(saved.get("publish"), str)
            and text(saved.get("product")) and KEY_NAME.fullmatch(text(saved.get("key_name")))):
        raise Stop(f"{path} is not a payload `dashboard plan` wrote. Run `dashboard plan` again. "
                   "Nothing was sent.")
    return saved, saved["publish"].encode("utf-8")


def cmd_send(root: Path, path: Path) -> dict:
    check_kind(path, "dashboard", "send")
    keep = False
    try:
        url, prof, env = settings(root)
        saved, body = read_dashboard_payload(path)
        product, project, key_name = text(saved["product"]), text(saved.get("project_name")), saved["key_name"]
        if text(saved.get("portal")).rstrip("/") != url:
            raise Stop(f"`dashboard plan` ran its dry run against {saved.get('portal') or 'another Portal'}, but "
                       f"tools.portal.url is now {url}. Run `dashboard plan` again. Nothing was sent.")
        key = read_keys(env, {product: key_name})[product]
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            raise Stop(f"{path} is not a payload `dashboard plan` wrote. Run `dashboard plan` again.") from None
        local_check(payload, body, {}, product)
        now_opens = project_name(url, key, key_name)
        if now_opens != project:
            keep = True                           # kept: `dashboard discard` removes it, or it goes after a day
            raise Stop(f"The key in {key_name} now opens Portal project \"{now_opens}\", but `dashboard plan` "
                       f"showed the {product} Dashboard going to \"{project or 'an unnamed project'}\". Check "
                       f"that {key_name} in .env holds the key for the right project, then run `dashboard plan` "
                       f"again and look at the new dry run before sending. Nothing was sent.")
        try:
            reply = post(url, key, body, dry_run=False, sources={}, key_name=key_name)
        except MaybeSent:
            keep = True
            raise
    finally:
        if not keep:
            path.unlink(missing_ok=True)
    c = reply["counts"]
    got = {k: c.get(k, len(payload[k])) for k in ("areas", "topics", "cards")}
    tickets = c.get("tickets", sum(len(x["tickets"]) for x in payload["cards"]))
    report = (f"Sent the {product} Dashboard to Portal project \"{project}\" at {url}: {got['areas']} areas, "
              f"{c['features']} Features, {got['topics']} topics, {c['items']} Items, {got['cards']:,} Board cards "
              f"with {tickets:,} tickets, {c['client_contacts']} Client contacts. The Portal confirmed it at "
              f"{reply['received_at']} (UTC), publish id {reply['publish_id']}.")
    return {"ok": True, "sent": "Dashboard", "product": product, "project_name": project, "portal": url,
            "counts": c, "publish_id": reply["publish_id"], "received_at": reply["received_at"], "report": report}


def cmd_discard(path: Path, kind: str = "dashboard") -> dict:
    check_kind(path, kind, "discard")
    existed = path.exists()
    product = text((read_saved(path) or {}).get("product")) if kind == "dashboard" and existed else ""
    path.unlink(missing_ok=True)
    return {"ok": True, "sent": None, "deleted": str(path) if existed else None,
            "report": ("Nothing was sent" + (f" for {product}" if product else "") + ". The payload file was deleted.")}


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
              round_label: str, key_name: str = DEFAULT_KEY) -> dict:
    """POST the page as multipart: part `publish` = the JSON, then one part per screenshot named by its file."""
    files = [(PUBLISH_PART, (None, body, "application/json"))]
    files += [(p["name"], (p["name"], p["data"], p["type"])) for p in parts]

    def first_line(code: str) -> str | None:
        if code == "round_has_answers":
            return f"Round {round_words(round_label)} was already used (it has answers, or it was replaced and deleted) — give it a new round key"
        return None

    steps = {**key_steps(key_name, PAGE_NEXT_STEP),
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
    url, prof, env = settings(root)
    key, key_name = page_key(prof, env)
    clean_old_payloads()
    yaml_path = find_page_yaml(root, slug_arg)
    products = list(key_map(prof))
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
        # Two or more products: the page goes with the first product's key (until pages are sent per product),
        # so the BA must see which Portal project that is before saying yes.
        target = project_name(url, key, key_name, contract=None) if len(products) > 1 else ""
        reply = post_page(url, key, body, parts, True, rel, sources, page["round"], key_name)
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
    view = page_view(reply)
    result = {"ok": True, "portal": url, "payload": str(path), "page": page["slug"], "yaml": rel,
              "round": reply["round"], "sent_at": page["sent_at"], "counts": reply["counts"],
              "left_out": left_out, "warnings": warnings, "fixed_lines": fixed}
    if target:
        view = f"Goes to Portal project \"{target}\" (the key in {key_name}).\n\n{view}"
        warnings.append(f"This repo has {len(products)} products ({', '.join(products)}). Until pages are sent "
                        f"per product, every page goes to the first product's Portal project, \"{target}\". "
                        "Check that this is the right project before saying yes.")
        result["project_name"] = target
    result["client_view"] = view
    return result


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
        url, prof, env = settings(root)
        key, key_name = page_key(prof, env)
        saved, body, parts = read_page_payload(path, root)
        if text(saved.get("portal")).rstrip("/") != url:
            raise Stop(f"`page plan` ran its dry run against {saved.get('portal') or 'another Portal'}, but "
                       f"tools.portal.url is now {url}. Run `page plan {saved.get('slug')}` again. Nothing was sent.")
        rel = text(saved.get("yaml")) or "the page YAML"
        page_local_check(json.loads(body.decode("utf-8")), body, parts, rel, {})
        try:
            reply = post_page(url, key, body, parts, False, rel, {}, text(saved.get("round")), key_name)
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
                                                                           ("--root", "--payload", "--product"))]
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
            if "--product" in argv and not text(arg(argv, "--product")):
                raise Stop("--product needs a product name, as the dashboard writes it (for example "
                           "--product \"Bond Portal\"). Nothing was sent.")
            result = cmd_plan(root, "--refresh" in argv, text(arg(argv, "--product")) or None)
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
