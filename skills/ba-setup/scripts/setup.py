"""ba-setup helper. Every subcommand prints one JSON object and never prints a secret.

    uv run --with pyyaml python <skill>/scripts/setup.py <command> [options]

Commands
  check-me                     personal keys and local tools: is each one set, and does it work?
  check-project [root]         the project profile: complete, tool areas set, template copy unchanged
  list-jira-projects           Jira projects the token can see
  list-confluence-spaces       Confluence spaces the token can see
  list-slack-channels          Slack channels the token's user is a member of
  defaults-plan                what installing the starter defaults would add (changes nothing)
  defaults-apply               add the starter defaults (backs up both files first)
  stamp                        record that setup passed for this ba-tools version
  stamp-status                 is there a passing stamp for this version?
"""
import base64
import datetime as dt
import json
import os
import shutil
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
GMAIL_TOKEN = CLAUDE / "skills/fetch-gmail/state/token.json"
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


def env(*names):
    return {n: os.environ.get(n, "") for n in names}


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
        return row("Jira", "missing", f"not set: {', '.join(missing)}", "see references/me.md → Jira")
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
        return row("Fireflies", "missing", f"not set: {', '.join(missing)}", "references/me.md → Fireflies")
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
        return row("Gmail", "missing", f"not set: {', '.join(missing)}", "references/me.md → Gmail")
    if not GMAIL_TOKEN.exists():
        return row("Gmail", "missing", "keys set, but you have not signed in yet",
                   "run the fetch-gmail sign-in once (references/me.md → Gmail, step 6)")
    try:
        refresh = json.loads(GMAIL_TOKEN.read_text(encoding="utf-8")).get("refresh_token", "")
    except Exception:
        refresh = ""
    form = urllib.parse.urlencode({"client_id": e["GMAIL_OAUTH_CLIENT_ID"], "client_secret": e["GMAIL_OAUTH_CLIENT_SECRET"],
                                   "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    code, body = http("POST", "https://oauth2.googleapis.com/token",
                      {"Content-Type": "application/x-www-form-urlencoded"}, form)
    if code != 200 or "access_token" not in body:
        return row("Gmail", "broken", "the saved sign-in no longer works", "sign in again (references/me.md → Gmail, step 6)")
    code, prof = http("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                      {"Authorization": f"Bearer {body['access_token']}"})
    if code == 200:
        return row("Gmail", "ok", f"signed in as {prof.get('emailAddress')}")
    return row("Gmail", "broken", f"Gmail answered {code or 'nothing'}", "is the Gmail API enabled in your Google Cloud project?")


def check_slack():
    tok = os.environ.get("SLACK_USER_TOKEN", "")
    if not tok:
        return row("Slack", "missing", "not set: SLACK_USER_TOKEN", "references/me.md → Slack")
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


def cmd_check_me():
    rows = [check_jira(), check_confluence(), check_fireflies(), check_gmail(), check_slack(),
            check_program("git", ["--version"], "needed", "install Git for Windows"),
            check_program("node", ["--version"], "needed by the fetch scripts", "install Node 22 LTS"),
            check_program("uv", ["--version"], "needed by BMad and ba-tools", "install uv from astral.sh")]
    rows += [r for r in (check_github_token(), check_plugins()) if r]
    rows.append(row("Atlassian connector", "skill-checks", "checked by the skill, not this script"))
    rows.append(row("Figma connector", "skill-checks", "checked by the skill, not this script"))
    out({"rows": rows, "defaults_installed": defaults_installed()})


# ---------------------------------------------------------------- check-project

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
                             ("slack", "Slack area", ["channels"]), ("client_emails", "Client emails", ["include"])]:
        v = t.get(key)
        if key in t and v in ({}, []):
            rows.append(row(label, "n/a", "not used on this project"))
            continue
        ok = bool(v) if need is None else bool(v) and all(v.get(n) for n in need)
        rows.append(row(label, "ok" if ok else "missing", "set" if ok else "not set", "ba-setup project"))
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
    tok = os.environ.get("SLACK_USER_TOKEN", "")
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


def defaults_plan():
    starter = json.loads((SKILL / "assets/starter-permissions.json").read_text(encoding="utf-8"))
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


def defaults_installed():
    p = defaults_plan()
    return not p["permissions_to_add"]["allow"] and not p["permissions_to_add"]["deny"] and p["instructions"] == "up to date"


def cmd_defaults_apply():
    plan = defaults_plan()
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


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "help"
    arg = sys.argv[2] if len(sys.argv) > 2 else "."
    {"check-me": cmd_check_me, "check-project": lambda: cmd_check_project(arg),
     "list-jira-projects": cmd_list_jira, "list-confluence-spaces": cmd_list_confluence,
     "list-slack-channels": cmd_list_slack, "defaults-plan": lambda: out(defaults_plan()),
     "defaults-apply": cmd_defaults_apply, "stamp": cmd_stamp, "stamp-status": cmd_stamp_status,
     }.get(c, lambda: print(__doc__))()
