"""ba-setup helper. Every subcommand prints one JSON object and never prints a secret.

    uv run --with pyyaml python <skill>/scripts/setup.py <command> [options]

Commands
  check-me                     personal keys and local tools: is each one set, and does it work?
  check-project [root]         the project profile: complete, tool areas set, template copy unchanged
  list-jira-projects           Jira projects the token can see
  list-confluence-spaces       Confluence spaces the token can see
  list-slack-channels          Slack channels the token's user is a member of
  keys-add <tool…> [--set NAME=VALUE]
                               add PASTE-… placeholder lines for a tool's missing keys to the env block of
                               ~/.claude/settings.json (tools: jira, confluence, fireflies, gmail, slack). --set
                               fills a site address or an email the BA gave; it refuses keys and tokens.
  defaults-plan                what installing the starter defaults would add (changes nothing)
  defaults-apply               add the starter defaults (backs up both files first)
  check-me, defaults-plan and defaults-apply take --connectors '{"<connector name>": "<id>", …}' (the desktop
  app's connector list), so the connector rules are added under the names the desktop app uses as well.
  stamp                        record that setup passed for this ba-tools version
  stamp-status                 is there a passing stamp for this version?
  connect <root> --product <name or ""> --code <code> [--replace]
                               swap an Admin's one-time connect code for a Portal key and write it into the
                               repo's .env. Needs `--with httpx --with jsonschema` as well. Prints the Portal
                               project's name, the .env variable and the key's last 4 characters, never the key.
"""
import argparse
import base64
import datetime as dt
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
TOOLS = SKILL.parent.parent
TEMPLATE = TOOLS / "skills/ba-spec/assets/spec-template.md"
HOME = Path.home()
CLAUDE = HOME / ".claude"
STAMP = CLAUDE / "ba-tools" / "setup.json"
GMAIL_TOKEN = next((p for p in (CLAUDE / "ba-tools/state/gmail-token.json",
                                 CLAUDE / "skills/fetch-gmail/state/token.json") if p.exists()),
                   CLAUDE / "ba-tools/state/gmail-token.json")
MARK_START = "<!-- ba-tools:starter-instructions -->"
MARK_END = "<!-- /ba-tools:starter-instructions -->"

PROFILE_REQUIRED = ["profile_version", "ba_tools_version", "project", "products", "decider_model", "downstream",
                    "cadence", "release_folders", "conflict_scope", "ids", "prd", "code", "spec_links",
                    "client_review", "tools"]


def out(obj):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def tools_version():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8").split("---")[1])["ba_tools_version"]


def http(method, url, headers=None, body=None, timeout=20):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:  # network, DNS, timeout
        return 0, {"error": type(e).__name__}


# Keys live in the `env` block of ~/.claude/settings.json. A session reads that block once, when it starts, so a
# key the BA has just saved is in the file but not yet in os.environ. The checks read the file as well, so they
# test the key the BA saved, and say "start a new session" when the session is behind the file.
PLACEHOLDER = "PASTE-"
KEY_GROUPS = {
    "jira": ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"],
    "confluence": ["CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"],
    "fireflies": ["FIREFLIES_API_KEY", "FIREFLIES_USER_EMAIL"],
    "gmail": ["GMAIL_OAUTH_CLIENT_ID", "GMAIL_OAUTH_CLIENT_SECRET"],
    "slack": ["SLACK_USER_TOKEN"],
}
PLACEHOLDER_TEXT = {
    "JIRA_BASE_URL": "PASTE-the-Jira-site-like-https://example.atlassian.net",
    "JIRA_EMAIL": "PASTE-the-email-you-sign-in-to-Jira-with",
    "JIRA_API_TOKEN": "PASTE-your-Atlassian-API-token",
    "CONFLUENCE_BASE_URL": "PASTE-the-Confluence-site-only-if-not-the-Jira-site",
    "CONFLUENCE_EMAIL": "PASTE-the-email-you-sign-in-to-Confluence-with",
    "CONFLUENCE_API_TOKEN": "PASTE-your-Atlassian-API-token-for-that-site",
    "FIREFLIES_API_KEY": "PASTE-your-Fireflies-API-key",
    "FIREFLIES_USER_EMAIL": "PASTE-the-email-Fireflies-has-for-you",
    "GMAIL_OAUTH_CLIENT_ID": "PASTE-the-client-ID-from-the-lead-BA",
    "GMAIL_OAUTH_CLIENT_SECRET": "PASTE-the-client-secret-from-the-lead-BA",
    "SLACK_USER_TOKEN": "PASTE-the-User-OAuth-Token-starting-xoxp-",
}
NOT_SECRET = re.compile(r"_(BASE_URL|EMAIL)$")   # the only values the BA may give in chat (keys-add --set)
SAVED_NOT_LOADED, STILL_PLACEHOLDER = set(), set()


def settings_env():
    try:
        return json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8")).get("env") or {}
    except Exception:
        return {}


def env(*names):
    """The value of each name: this session's, or else the one saved in settings.json. A placeholder counts as
    not set. Notes which names are saved but not loaded, and which still hold a placeholder."""
    saved, vals = settings_env(), {}
    for n in names:
        v = os.environ.get(n, "")
        if not v and saved.get(n):
            v = str(saved[n])
            if not v.startswith(PLACEHOLDER):
                SAVED_NOT_LOADED.add(n)
        if v.startswith(PLACEHOLDER):
            STILL_PLACEHOLDER.add(n)
            v = ""
        vals[n] = v
    return vals


def not_set(missing):
    """The 'not set' detail, naming the ones that still hold a placeholder."""
    ph = [m for m in missing if m in STILL_PLACEHOLDER]
    rest = [m for m in missing if m not in STILL_PLACEHOLDER]
    parts = ([f"not set: {', '.join(rest)}"] if rest else []) + \
            ([f"still a placeholder (PASTE-…): {', '.join(ph)}"] if ph else [])
    return "; ".join(parts)


def row(tool, state, detail, fix=""):
    return {"tool": tool, "state": state, "detail": detail, "fix": fix}


def atlassian_auth(prefix):
    e = env(f"{prefix}_BASE_URL", f"{prefix}_EMAIL", f"{prefix}_API_TOKEN")
    vals = list(e.values())
    if not all(vals):
        return None, [k for k, v in e.items() if not v]
    tok = base64.b64encode(f"{vals[1]}:{vals[2]}".encode()).decode()
    return (vals[0].rstrip("/"), {"Authorization": f"Basic {tok}", "Accept": "application/json"}), []


# ---------------------------------------------------------------- check-me

def check_jira():
    auth, missing = atlassian_auth("JIRA")
    if not auth:
        return row("Jira", "missing", not_set(missing), "see references/me.md → Jira")
    base, h = auth
    code, body = http("GET", f"{base}/rest/api/3/myself", h)
    if code == 200:
        return row("Jira", "ok", f"signed in as {body.get('displayName', '?')} on {base}")
    return row("Jira", "broken", f"{base} answered {code or 'nothing'}",
               "401 = wrong email or token; make a new token (references/me.md → Jira)")


def check_confluence():
    auth, _ = atlassian_auth("CONFLUENCE")
    if not auth:
        auth, missing = atlassian_auth("JIRA")
        if not auth:
            return row("Confluence", "missing", "uses the Jira token — set that first", "references/me.md → Jira")
    base, h = auth
    code, _ = http("GET", f"{base}/wiki/api/v2/spaces?limit=1", h)
    if code == 200:
        return row("Confluence", "ok", f"reachable on {base}/wiki")
    return row("Confluence", "broken", f"{base}/wiki answered {code or 'nothing'}",
               "check your account has Confluence access on this site")


def check_fireflies():
    e = env("FIREFLIES_API_KEY", "FIREFLIES_USER_EMAIL")
    missing = [k for k, v in e.items() if not v]
    if missing:
        return row("Fireflies", "missing", not_set(missing), "references/me.md → Fireflies")
    code, body = http("POST", "https://api.fireflies.ai/graphql",
                      {"Authorization": f"Bearer {e['FIREFLIES_API_KEY']}", "Content-Type": "application/json"},
                      {"query": "{ user { email name } }"})
    user = (body.get("data") or {}).get("user") if code == 200 else None
    if not user:
        return row("Fireflies", "broken", f"api.fireflies.ai answered {code or 'nothing'}",
                   "make a new API key (references/me.md → Fireflies)")
    note = "" if user.get("email", "").lower() == e["FIREFLIES_USER_EMAIL"].lower() else \
        f" — ⚠ FIREFLIES_USER_EMAIL differs from the account email ({user.get('email')})"
    return row("Fireflies", "ok" if not note else "warn", f"signed in as {user.get('name')}{note}")


def check_gmail():
    e = env("GMAIL_OAUTH_CLIENT_ID", "GMAIL_OAUTH_CLIENT_SECRET")
    missing = [k for k, v in e.items() if not v]
    if missing:
        return row("Gmail", "missing", not_set(missing), "references/me.md → Gmail")
    if not GMAIL_TOKEN.exists():
        return row("Gmail", "missing", "keys set, but you have not signed in yet",
                   "ask Claude to run the Gmail sign-in (references/me.md → Gmail, step 3)")
    try:
        refresh = json.loads(GMAIL_TOKEN.read_text(encoding="utf-8")).get("refresh_token", "")
    except Exception:
        refresh = ""
    form = urllib.parse.urlencode({"client_id": e["GMAIL_OAUTH_CLIENT_ID"], "client_secret": e["GMAIL_OAUTH_CLIENT_SECRET"],
                                   "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    code, body = http("POST", "https://oauth2.googleapis.com/token",
                      {"Content-Type": "application/x-www-form-urlencoded"}, form)
    if code != 200 or "access_token" not in body:
        return row("Gmail", "broken", "the saved sign-in no longer works", "ask Claude to run the Gmail sign-in again (references/me.md → Gmail, step 3)")
    code, prof = http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                      {"Authorization": f"Bearer {body['access_token']}"})
    if code == 200:
        return row("Gmail", "ok", f"signed in as {prof.get('emailAddress')}")
    return row("Gmail", "broken", f"Gmail answered {code or 'nothing'}", "is the Gmail API enabled in your Google Cloud project?")


def check_slack():
    tok = env("SLACK_USER_TOKEN")["SLACK_USER_TOKEN"]
    if not tok:
        return row("Slack", "missing", not_set(["SLACK_USER_TOKEN"]), "references/me.md → Slack")
    if not tok.startswith("xoxp-"):
        return row("Slack", "broken", "SLACK_USER_TOKEN is not a user token (it should start with xoxp-)",
                   "copy the User OAuth Token, not the Bot token (references/me.md → Slack)")
    code, body = http("POST", "https://slack.com/api/auth.test", {"Authorization": f"Bearer {tok}"})
    if code == 200 and body.get("ok"):
        return row("Slack", "ok", f"signed in as {body.get('user')} in {body.get('team')}")
    return row("Slack", "broken", f"Slack said: {body.get('error', code)}", "reinstall the Slack app and copy a fresh token")


def check_program(name, args, need, fix):
    exe = shutil.which(name)
    if not exe:
        return row(name, "missing", "not installed", fix)
    try:
        v = subprocess.run([exe, *args], capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[0]
    except Exception:
        v = "?"
    return row(name, "ok", f"{v} ({need})")


def check_github_token():
    if os.environ.get("GITHUB_TOKEN"):
        return row("GITHUB_TOKEN", "warn", "set — the BMad installer fails if it is invalid",
                   "remove it from ~/.claude/settings.json unless something you use needs it")
    return None


def check_plugins():
    try:
        s = json.loads((CLAUDE / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if (s.get("enabledPlugins") or {}).get("fdw@fdw"):
        return row("fdw plugin", "warn", "switched on — it is retired and its skills compete with ba-tools",
                   'set "fdw@fdw": false in ~/.claude/settings.json')
    return None


INSTALL = {   # Claude runs these for the BA, after a yes (winget ships with Windows 11)
    "git": "winget install --id Git.Git -e",
    "node": "winget install --id OpenJS.NodeJS.LTS -e",
    "uv": "winget install --id astral-sh.uv -e",
}
NEW_SESSION = "start a new session (New session in the sidebar): this one started before the change"


def by_connector(r, connectors, name, what):
    """fetch-gmail and fetch-slack work through the connector when there is no key. So with the connector
    connected, a missing key is fine and a broken one is only a warning (the skill falls back by itself)."""
    if name not in (connectors or {}) or r["state"] == "ok":
        return r
    if r["state"] == "missing":
        return row(r["tool"], "ok", f"fetches through the {name} connector (keys are optional: {what})")
    return row(r["tool"], "warn", f"{r['detail']} — fetches fall back to the {name} connector", r["fix"])


def cmd_check_me(connectors=None):
    rows = [check_jira(), check_confluence(), check_fireflies(),
            by_connector(check_gmail(), connectors, "Gmail", "they keep email text out of the chat"),
            by_connector(check_slack(), connectors, "Slack", "it keeps message text out of the chat"),
            check_program("git", ["--version"], "needed", f"Claude can install it: {INSTALL['git']}"),
            check_program("node", ["--version"], "needed by the fetch scripts",
                          f"Claude can install it: {INSTALL['node']}"),
            check_program("uv", ["--version"], "needed by BMad and ba-tools", f"Claude can install it: {INSTALL['uv']}")]
    rows += [r for r in (check_github_token(), check_plugins()) if r]
    if SAVED_NOT_LOADED:
        rows.append(row("New session", "warn",
                        f"saved in your settings but not loaded here: {', '.join(sorted(SAVED_NOT_LOADED))}. "
                        "The check above used the saved values; the fetch scripts will not see them yet",
                        NEW_SESSION))
    rows.append(row("Connectors", "skill-checks", "checked by the skill (the session's connector list), not this script"))
    out({"rows": rows, "defaults_installed": defaults_installed(connectors)})


def cmd_keys_add(argv):
    """Add placeholder lines for the missing keys of the named tools to the env block of settings.json, so the BA
    only swaps each PASTE-… text for the real value: no JSON to type, no commas to get wrong. Keeps every value
    already there. Backs the file up first. Prints names only, never a value."""
    p = argparse.ArgumentParser(prog="setup.py keys-add")
    p.add_argument("tools", nargs="+", choices=sorted(KEY_GROUPS))
    p.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                   help="a site address or an email the BA gave (never a key or a token)")
    a = p.parse_args(argv)
    given = {}
    for item in a.set:
        name, _, value = item.partition("=")
        if not NOT_SECRET.search(name):
            out({"ok": False, "error": f"--set takes only a site address or an email, not {name}. "
                                       "Keys are typed into the settings file by the BA."})
            sys.exit(1)
        given[name] = value.strip()
    sp = CLAUDE / "settings.json"
    try:
        settings = load_json(sp)
    except json.JSONDecodeError as e:
        out({"ok": False, "error": f"settings.json is not valid JSON (line {e.lineno}): fix that first; "
                                   "nothing was written", "settings_path": str(sp)})
        sys.exit(1)
    block = settings.setdefault("env", {})
    added, filled, kept = [], [], []
    for tool in a.tools:
        for name in KEY_GROUPS[tool]:
            current = str(block.get(name, ""))
            if name in given and (not current or current.startswith(PLACEHOLDER)):
                block[name] = given[name]
                filled.append(name)
            elif current:
                kept.append(name)
            else:
                block[name] = PLACEHOLDER_TEXT[name]
                added.append(name)
    backup = None
    if added or filled:
        if sp.exists():
            backup = sp.with_name(f"settings.json.bak-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
            shutil.copy2(sp, backup)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    placeholders = sorted(n for n, v in block.items() if str(v).startswith(PLACEHOLDER))
    out({"ok": True, "settings_path": str(sp), "placeholders_added": added, "filled_from_chat": filled,
         "already_set": kept, "placeholders_left": placeholders, "backup": str(backup) if backup else None,
         "open_with": f'notepad "{sp}"'})


# ---------------------------------------------------------------- check-project

PORTAL_SKILL = SKILL.parent / "portal-publish"
PORTAL_TARGETS = PORTAL_SKILL / "targets.py"
PORTAL_CHECKS = PORTAL_SKILL / "checks.py"
CONNECT_PLACE = "Admin → Projects → the project → Publishing → Connect a repo"


def load_portal_module(path, name):
    """A portal-publish file (targets.py, checks.py), loaded as fetch-portal loads it: one copy of each rule."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def portal_key_rows(root, prof):
    """One row per Portal product key: in .env, or missing. Reads which .env variable each product uses with
    portal-publish's targets.py (the same rule page sends, Dashboard sends and fetch-portal use). Only the names
    in .env are looked at; a key is never shown."""
    fix = (f"ask an Admin for a connect code ({CONNECT_PLACE}), one per product, then run ba-setup project: "
           "it puts the key in .env")
    if not PORTAL_TARGETS.exists():
        return [row("Portal keys", "broken", "the portal-publish skill is not installed next to ba-setup",
                    "install ba-tools again")]
    targets = load_portal_module(PORTAL_TARGETS, "portal_publish_targets")
    try:
        names = targets.portal_names(prof)
    except targets.TargetError as e:
        return [row("Portal keys", "broken", str(e), "ba-setup project, step 5 (Client Portal)")]
    env_file = root / ".env"
    env = targets.read_env_file(env_file) if env_file.exists() else {}
    rows = []
    for product, name in names.items():
        there = bool(env.get(name, "").strip())
        rows.append(row(f"Portal key: {product}" if product else "Portal key", "ok" if there else "missing",
                        f"{name} is in .env" if there else f".env has no {name}", "" if there else fix))
    return rows


def cmd_check_project(root):
    root = Path(root).resolve()
    p = root / "docs/BA/specs/.ba-profile.yml"
    if not p.exists():
        out({"root": str(root), "profile": "missing", "rows": []})
        return
    prof = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = []
    miss = [k for k in PROFILE_REQUIRED if k not in prof]
    rows.append(row("profile keys", "ok" if not miss else "missing",
                    "all present" if not miss else f"missing: {', '.join(miss)}", "ba-setup project"))
    if prof.get("profile_version") != 2:
        rows.append(row("profile version", "broken", f"is {prof.get('profile_version')!r}, ba-tools expects 2",
                        "ba-setup project — it upgrades the file"))
    for pr in prof.get("products") or []:
        if not (pr.get("roles") or {}).get("list"):
            rows.append(row(f"roles: {pr.get('key')}", "missing", "no role list", "ba-setup project"))
    t = prof.get("tools") or {}
    down = prof.get("downstream") or []
    rows.append(row("Jira area", "ok" if prof.get("jira") and all(pr.get("jira_project") for pr in prof.get("products") or [])
                    else ("n/a" if "jira" not in down else "missing"),
                    "site + projects set" if prof.get("jira") else "no jira block", "ba-setup project"))
    for key, label, need in [("confluence", "Confluence area", ["space"]), ("figma", "Figma area", ["files"]),
                             ("slack", "Slack area", ["channels"]), ("client_emails", "Client emails", ["include"]),
                             ("dashboard", "BA dashboard", ["file", "url"]), ("dictionary", "Data dictionary", ["config"]),
                             ("messages", "Messages catalogue", ["file"])]:
        v = t.get(key)
        if key in t and v in ({}, []):
            rows.append(row(label, "n/a", "not used on this project"))
            continue
        ok = bool(v) if need is None else bool(v) and all(v.get(n) for n in need)
        if key == "dashboard" and v and v.get("file") and v.get("timelines"):  # the Timelines are the dashboard
            ok = all((x or {}).get("url") and (x or {}).get("data") for x in v["timelines"].values())
        rows.append(row(label, "ok" if ok else "missing", "set" if ok else "not set", "ba-setup project"))
    if isinstance(t.get("portal"), dict) and t["portal"]:
        rows += portal_key_rows(root, prof)
    # The dashboard is best started right after the project brief: every feature and question hangs from it.
    dash = t.get("dashboard") or {}
    briefs = sorted({*root.glob("docs/**/product-brief*.md"), *root.glob("docs/planning-artifacts/**/*brief*.md")})
    if not dash.get("url") and not dash.get("timelines") and briefs:
        rows.append(row("BA dashboard", "warn", f"the project has a brief ({briefs[0].relative_to(root).as_posix()}) but no dashboard",
                        "ba-dashboard — Starting one (it seeds the features from the brief)"))
    elif dash.get("url") and not dash.get("page"):
        rows.append(row("dashboard page", "warn", "the dashboard is still the old table page",
                        "ba-dashboard — Starting one, steps 4–6: build the Map/Board page and publish it to the same link"))
    for pr in prof.get("products") or []:
        dp = pr.get("design_profile")
        if not dp:
            rows.append(row(f"design profile: {pr.get('key')}", "missing", "no design_profile path", "ba-setup design"))
            continue
        f = root / dp
        if not f.exists():
            rows.append(row(f"design profile: {pr.get('key')}", "missing", f"{dp} does not exist", "ba-setup design"))
            continue
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        gaps = [k for k in ("figma", "frames", "tokens", "registry") if not d.get(k)]
        fig = d.get("figma") or {}
        if not (fig.get("build_file") or {}).get("key"):
            gaps.append("figma.build_file")
        if not fig.get("ds_library_key"):
            gaps.append("figma.ds_library_key")
        rows.append(row(f"design profile: {pr.get('key')}", "ok" if not gaps else "warn",
                        "complete" if not gaps else f"not filled: {', '.join(gaps)}", "ba-setup design"))
    places = ([Path(os.environ["BA_TOOLS_HOME"])] if os.environ.get("BA_TOOLS_HOME") else []) +              [Path("C:/dev/ba-tools"), HOME / "dev/ba-tools"]   # where the ba-tools clone usually lives
    clone = next((c for c in places if (c / "scripts/install.py").exists()), None)
    if clone:
        try:
            newest = yaml.safe_load((clone / "skills/ba-spec/assets/spec-template.md").read_text(encoding="utf-8")
                                    .split("---")[1])["ba_tools_version"]
            if newest != tools_version():
                rows.append(row("ba-tools update", "warn", f"this project has {tools_version()}, your ba-tools clone has {newest}",
                                f"uv run --with pyyaml python {clone.as_posix()}/scripts/install.py {root.as_posix()}"))
        except Exception:
            pass
    tv = tools_version()
    if prof.get("ba_tools_version") != tv:
        rows.append(row("ba-tools version", "warn", f"profile says {prof.get('ba_tools_version')}, installed is {tv}",
                        "reinstall, then update ba_tools_version in the profile"))
    copy = root / "docs/BA/specs/_template.md"
    if copy.exists():
        same = copy.read_bytes().replace(b"\r\n", b"\n") == TEMPLATE.read_bytes().replace(b"\r\n", b"\n")
        rows.append(row("template copy", "ok" if same else "broken",
                        "matches ba-tools" if same else "differs from ba-tools — edited locally or out of date",
                        "move any project fact into the profile, then copy the template from ba-tools again"))
    out({"root": str(root), "profile": "present", "rows": rows})


# ---------------------------------------------------------------- lists for ba-setup project

def cmd_list_jira():
    auth, missing = atlassian_auth("JIRA")
    if not auth:
        out({"error": f"not set: {', '.join(missing)}"}); return
    base, h = auth
    code, body = http("GET", f"{base}/rest/api/3/project/search?maxResults=100&orderBy=name", h)
    out({"site": base, "projects": [{"key": p["key"], "name": p["name"]} for p in body.get("values", [])]}
        if code == 200 else {"error": f"Jira answered {code}"})


def cmd_list_confluence():
    auth, _ = atlassian_auth("CONFLUENCE")
    if not auth:
        auth, missing = atlassian_auth("JIRA")
        if not auth:
            out({"error": "no Atlassian token set"}); return
    base, h = auth
    code, body = http("GET", f"{base}/wiki/api/v2/spaces?limit=250", h)
    out({"spaces": [{"key": s["key"], "name": s["name"], "homepage": s.get("homepageId")} for s in body.get("results", [])]}
        if code == 200 else {"error": f"Confluence answered {code}"})


def cmd_list_slack():
    tok = env("SLACK_USER_TOKEN")["SLACK_USER_TOKEN"]
    if not tok:
        out({"error": "not set: SLACK_USER_TOKEN"}); return
    chans, cursor = [], ""
    while True:
        q = urllib.parse.urlencode({"types": "public_channel,private_channel", "limit": 200, "exclude_archived": "true",
                                    **({"cursor": cursor} if cursor else {})})
        code, body = http("GET", f"https://slack.com/api/users.conversations?{q}", {"Authorization": f"Bearer {tok}"})
        if not body.get("ok"):
            out({"error": f"Slack said: {body.get('error', code)}"}); return
        chans += [{"name": c["name"], "id": c["id"], "private": c.get("is_private", False)} for c in body["channels"]]
        cursor = (body.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            break
    out({"channels": sorted(chans, key=lambda c: c["name"])})


# ---------------------------------------------------------------- starter defaults

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


CONNECTOR_RULE = re.compile(r"^mcp__claude_ai_([A-Za-z0-9_]+?)__(.+)$")


def connectors_arg(argv):
    """--connectors '{"Atlassian Rovo": "<id>", "Gmail": "<id>", …}': the session's claude.ai connectors, as the
    skill reads them from the desktop app's connector list. Empty when not given."""
    if "--connectors" not in argv:
        return {}
    i = argv.index("--connectors")
    try:
        return {str(k): str(v) for k, v in json.loads(argv[i + 1]).items() if v}
    except (IndexError, ValueError, AttributeError):
        out({"ok": False, "error": "--connectors needs a JSON object of connector name → id"})
        sys.exit(1)


def starter_rules(connectors):
    """The starter permissions. The file names connector tools as the command line does (mcp__claude_ai_Gmail__…).
    The desktop app names the same tool after the connector's id (mcp__<id>__…), so each such rule is added again
    under the id of every connector given, or a "never send email" rule would not block anything there."""
    starter = json.loads((SKILL / "assets/starter-permissions.json").read_text(encoding="utf-8"))
    by_key = {re.sub(r"\W+", "_", name).strip("_"): cid for name, cid in connectors.items()}
    rules = {}
    for k in ("allow", "deny"):
        rules[k] = []
        for r in starter.get(k, []):
            rules[k].append(r)
            m = CONNECTOR_RULE.match(r)
            if m and m.group(1) in by_key:
                rules[k].append(f"mcp__{by_key[m.group(1)]}__{m.group(2)}")
    return rules


def defaults_plan(connectors=None):
    starter = starter_rules(connectors or {})
    settings = load_json(CLAUDE / "settings.json")
    perms = settings.get("permissions") or {}
    add = {k: [r for r in starter.get(k, []) if r not in (perms.get(k) or [])] for k in ("allow", "deny")}
    md = CLAUDE / "CLAUDE.md"
    block = (SKILL / "assets/starter-instructions.md").read_text(encoding="utf-8").strip()
    text = md.read_text(encoding="utf-8") if md.exists() else ""
    if MARK_START in text:
        current = text.split(MARK_START, 1)[1].split(MARK_END, 1)[0].strip()
        instr = "up to date" if current == block else "replace the ba-tools section"
    else:
        instr = "add the ba-tools section"
    return {"permissions_to_add": add, "instructions": instr, "settings_path": str(CLAUDE / "settings.json"),
            "claude_md_path": str(md)}


def defaults_installed(connectors=None):
    p = defaults_plan(connectors)
    return not p["permissions_to_add"]["allow"] and not p["permissions_to_add"]["deny"] and p["instructions"] == "up to date"


def cmd_defaults_apply(connectors=None):
    plan = defaults_plan(connectors)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    sp, md = CLAUDE / "settings.json", CLAUDE / "CLAUDE.md"
    backups = []
    for f in (sp, md):
        if f.exists():
            b = f.with_name(f"{f.name}.bak-{stamp}")
            shutil.copy2(f, b)
            backups.append(str(b))
    settings = load_json(sp)
    perms = settings.setdefault("permissions", {})
    for k in ("allow", "deny"):
        perms[k] = (perms.get(k) or []) + plan["permissions_to_add"][k]
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    block = (SKILL / "assets/starter-instructions.md").read_text(encoding="utf-8").strip()
    text = md.read_text(encoding="utf-8") if md.exists() else ""
    section = f"{MARK_START}\n{block}\n{MARK_END}"
    if MARK_START in text:
        head, rest = text.split(MARK_START, 1)
        text = head + section + rest.split(MARK_END, 1)[1]
    else:
        text = (text.rstrip() + "\n\n" if text.strip() else "") + section + "\n"
    md.write_text(text, encoding="utf-8")
    out({"applied": plan, "backups": backups})


# ---------------------------------------------------------------- stamp

def cmd_stamp():
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps({"ba_tools_version": tools_version(), "passed_at": dt.date.today().isoformat()}),
                     encoding="utf-8")
    out({"stamped": str(STAMP)})


def cmd_stamp_status():
    s = load_json(STAMP)
    out({"current": s.get("ba_tools_version") == tools_version(), "stamp": s, "installed": tools_version()})


# ---------------------------------------------------------------- connect (a one-time code → a key in .env)
#
# The key is in memory only between the Portal's reply and the write to .env. It is never printed, logged, put on
# a command line or put in an error message: errors name the variable and, for a reply that does not match
# connect/1, only the paths of the wrong fields (a schema message would quote the value).

CODE = re.compile(r"[2-9A-HJKMNP-Za-hjkmnp-z]{3}-?[2-9A-HJKMNP-Za-hjkmnp-z]{3}")
LABEL_MAX = 100
NOTHING = "Nothing was written."


class ConnectStop(Exception):
    """The run stops. The message is shown to the BA as it is."""


def env_line_name(line, name):
    """True when the .env line sets `name` (NAME=…, or export NAME=…)."""
    return re.match(rf"\s*(export\s+)?{re.escape(name)}\s*=", line) is not None


def check_env_writable(path):
    """Raise when .env cannot be read as UTF-8 or written, or its folder cannot take write_env_key's temporary file."""
    if path.exists():
        raw = path.read_bytes()
        (raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw).decode("utf-8")
        with open(path, "ab"):
            pass
    probe = path.with_name(".env.connect-probe")
    os.close(os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
    probe.unlink()


def write_env_key(path, name, value):
    """Set `name` in .env, keeping every other line, the line endings and a BOM as they are. A new line uses the
    file's own line ending (\\n for a new file). Written to a temporary file next to it, then moved over it."""
    raw = path.read_bytes() if path.exists() else b""
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if env_line_name(line, name)]
    if hits:
        first = lines[hits[0]]
        ending = first[len(first.rstrip("\r\n")):]
        lines[hits[0]] = f"{name}={value}{ending}"
        lines = [line for i, line in enumerate(lines) if i not in hits[1:]]
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines.append(f"{name}={value}{nl}")
    if path.is_symlink():   # write through a link, so it stays a link
        path = path.resolve()
    tmp = path.with_name(".env.connect-tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # never readable by others, even briefly
        with os.fdopen(fd, "wb") as f:
            f.write((b"\xef\xbb\xbf" if bom else b"") + "".join(lines).encode("utf-8"))
        if path.exists():
            shutil.copymode(path, tmp)   # keep the old file's permissions
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def repo_label(root):
    """The name the Admin sees under Connected repos: "<repo folder> · <git user.name>", or the folder alone."""
    try:
        r = subprocess.run(["git", "config", "user.name"], cwd=root, capture_output=True, timeout=20)
        who = r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        who = ""
    label = f"{root.name} · {who}" if who else root.name
    label = re.sub(r"\s+", " ", "".join(ch for ch in label if ch.isprintable() or ch.isspace())).strip()
    return (label or "repo")[:LABEL_MAX].strip()


def pick_target(targets, prof, product):
    """(product, .env variable) by targets.py's own rule: the variable portal-publish and fetch-portal read."""
    try:
        names = targets.portal_names(prof)
    except targets.TargetError as e:
        raise ConnectStop(f"{e} Nothing was sent.") from None
    if product:
        if product not in names:
            known = ", ".join(n for n in names if n) or "(the profile names none)"
            raise ConnectStop(f"There is no product called '{product}' with a Portal project. This repo's "
                              f"products: {known}. Nothing was sent.")
        return product, names[product]
    if len(names) > 1:
        raise ConnectStop(f"This repo has {len(names)} products ({', '.join(names)}), each with its own Portal "
                          "project. Say which one this code is for with --product. Nothing was sent.")
    return next(iter(names.items()))


def portal_error(status, body, headers):
    """(code, message, seconds to wait) from the error envelope; code is "" when the reply is not one."""
    try:
        doc = json.loads(body or b"{}")
    except ValueError:
        doc = None
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict) or not err.get("code"):
        return "", "", None
    wait = err.get("retry_after_s")
    if not isinstance(wait, int) or isinstance(wait, bool):
        header = (headers or {}).get("Retry-After", "")
        wait = int(header) if str(header).strip().isdigit() else None
    return str(err["code"]), str(err.get("message") or "").strip(), wait


def refused(url, status, body, headers):
    code, msg, wait = portal_error(status, body, headers)
    if code == "connect_code_invalid":
        return ConnectStop(f"This code does not work. Ask an Admin for a new one ({CONNECT_PLACE}). {NOTHING}")
    if code == "too_many_tries":
        minutes = max(1, math.ceil(wait / 60)) if wait else 0
        when = f"in {minutes} minute{'s' if minutes > 1 else ''}" if minutes else "in a few minutes"
        return ConnectStop(f"Too many wrong codes were tried on the Portal. Try again {when}. {NOTHING}")
    if code:
        return ConnectStop(f"The Portal refused the connect ({code}): {msg or 'no message'}. {NOTHING}")
    if status in (404, 405):
        return ConnectStop(f"The Portal at {url} cannot connect a repo with a code yet (HTTP {status}). Ask an Admin "
                           f"to update the Portal. {NOTHING}")
    return ConnectStop(f"The Portal's reply was not understood (HTTP {status}). {NOTHING}")


def post_connect(url, body):
    """POST connect-request/1. Returns (status, body bytes, headers). No Authorization header: the code is the
    proof."""
    req = urllib.request.Request(f"{url}/api/v1/connect", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    lost = (f"The Portal at {url} did not answer in time. The code may now be used up: if it does not work next "
            f"time, ask an Admin for a new one. {NOTHING}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise ConnectStop(lost) from None
        raise ConnectStop(f"The Portal is not reachable at {url}. Check that it is running and that "
                          f"tools.portal.url is right. {NOTHING}") from None
    except (TimeoutError, socket.timeout, ConnectionError, OSError):
        raise ConnectStop(lost) from None


def connect(root, product, code, replace):
    """Swap a one-time code for a key; write it into .env. Returns what may be shown (never the key)."""
    if not PORTAL_TARGETS.exists() or not PORTAL_CHECKS.exists():
        raise ConnectStop("The portal-publish skill is not installed next to ba-setup. Install ba-tools again.")
    try:
        targets = load_portal_module(PORTAL_TARGETS, "portal_publish_targets")
        checks = load_portal_module(PORTAL_CHECKS, "portal_publish_checks")
        import httpx  # noqa: F401  (targets.check_url needs it)
    except ImportError as e:
        raise ConnectStop(f"connect needs {e.name}: run it with `uv run --with pyyaml --with httpx --with "
                          "jsonschema python setup.py connect …`. Nothing was sent.") from None

    prof_path = root / targets.PROFILE
    if not prof_path.exists():
        raise ConnectStop(f"No project profile at {targets.PROFILE}. Run `ba-setup project` first. Nothing was sent.")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    portal = ((prof.get("tools") or {}).get("portal") or {}) if isinstance(prof, dict) else {}
    url = targets.text(portal.get("url")).rstrip("/") if isinstance(portal, dict) else ""
    if not url:
        raise ConnectStop(f"The profile has no Portal address (tools.portal.url in {targets.PROFILE}). Add it "
                          "first: ba-setup project, step 5 (Client Portal). Nothing was sent.")
    try:
        targets.check_url(url)
    except targets.TargetError as e:
        raise ConnectStop(f"{e} Nothing was sent.") from None
    product, name = pick_target(targets, prof, product)

    env_path = root / ".env"
    try:   # find a .env or folder we cannot write before the code is used up
        check_env_writable(env_path)
        env = targets.read_env_file(env_path) if env_path.exists() else {}
    except Exception as e:   # never the message: it could quote a line of .env
        raise ConnectStop(f".env cannot be written ({type(e).__name__}). Fix that (is it open in another program, "
                          "read-only, or not UTF-8?), then run again. Nothing was sent, so the code still "
                          "works.") from None
    had_key = bool(env.get(name, "").strip())
    if had_key and not replace:
        whose = f" (the Portal key for {product})" if product else ""
        raise ConnectStop(f".env already has {name}{whose}. Ask the BA before replacing it: this repo would then "
                          "use the new key (the old one may still work in the Portal until an Admin removes it "
                          "under Connected repos). On yes, run again with --replace. Nothing was sent, so the code "
                          "still works.")
    code = code.strip()
    if not CODE.fullmatch(code):
        raise ConnectStop("This does not look like a connect code. A code has 6 letters and digits, like K7P-4XM. "
                          "Nothing was sent.")
    warnings = []
    try:
        ignored = targets.env_is_ignored(root)
    except targets.TargetError as e:
        warnings.append(str(e))
        ignored = True
    if not ignored:
        raise ConnectStop(".env is not ignored by git, so the key could be committed. Add .env to .gitignore (and "
                          "run `git rm --cached .env` if it was committed), then run again. Nothing was sent, so "
                          "the code still works.")

    request = {"code": code, "label": repo_label(root)}
    if checks.check_reply(request, "connect-request/1"):
        raise ConnectStop("The request does not match connect-request/1. Nothing was sent.")
    status, body, headers = post_connect(url, request)
    if status != 200:
        raise refused(url, status, body, headers)
    used_up = "The code may now be used up: ask an Admin for a new one."
    try:
        reply = json.loads(body)
    except ValueError:
        raise ConnectStop(f"The Portal's reply was not understood (HTTP 200, not JSON). {used_up} {NOTHING}") from None
    wrong = sorted({d["path"] or "/" for d in checks.check_reply(reply, "connect/1")})
    if not wrong and reply["key_last4"] != reply["key"][-4:]:
        wrong = ["/key_last4"]
    if wrong:   # paths only: a schema message would quote the key
        raise ConnectStop(f"The Portal's reply does not match connect/1 (at {', '.join(wrong)}). {used_up} "
                          f"{NOTHING}")
    created = not env_path.exists()
    try:
        write_env_key(env_path, name, reply["key"])
    except Exception as e:   # never the message: it could hold the line being written
        raise ConnectStop(f"The key could not be written to .env ({type(e).__name__}). The Portal already made it: "
                          f"ask an Admin to remove the repo whose key ends in {reply['key'][-4:]} (Admin → Projects "
                          "→ the project → Publishing → Connected repos), then get a new code and run again.") from None
    project_name = reply["project"]["name"]
    last4 = reply["key"][-4:]
    return {
        "project": project_name, "product": product, "variable": name, "key_last4": last4,
        "replaced": had_key, "env_created": created,
        "message": f'Connected to Portal project "{project_name}". The key is in .env as {name} '
                   f"(it ends in {last4}).",
        "warnings": warnings,
    }


def cmd_connect(argv):
    p = argparse.ArgumentParser(prog="setup.py connect", description="Swap a one-time connect code for a key.")
    p.add_argument("root", help="the project root (where .env is)")
    p.add_argument("--product", default="", help='the product the code is for; "" when the repo has one')
    p.add_argument("--code", required=True, help="the connect code from the Admin, like K7P-4XM")
    p.add_argument("--replace", action="store_true", help="replace a key already in .env (ask the BA first)")
    a = p.parse_args(argv)
    try:
        result = connect(Path(a.root).resolve(), a.product.strip(), a.code, a.replace)
    except ConnectStop as e:
        out({"ok": False, "error": str(e)})
        sys.exit(1)
    out({"ok": True, **result})


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "connect":
        cmd_connect(sys.argv[2:])
        sys.exit(0)
    c = sys.argv[1] if len(sys.argv) > 1 else "help"
    arg = sys.argv[2] if len(sys.argv) > 2 else "."
    if c == "keys-add":
        cmd_keys_add(sys.argv[2:])
        sys.exit(0)
    conn = connectors_arg(sys.argv[2:])
    {"check-me": lambda: cmd_check_me(conn), "check-project": lambda: cmd_check_project(arg),
     "list-jira-projects": cmd_list_jira, "list-confluence-spaces": cmd_list_confluence,
     "list-slack-channels": cmd_list_slack, "defaults-plan": lambda: out(defaults_plan(conn)),
     "defaults-apply": lambda: cmd_defaults_apply(conn), "stamp": cmd_stamp, "stamp-status": cmd_stamp_status,
     }.get(c, lambda: print(__doc__))()
