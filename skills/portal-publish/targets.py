"""targets — which Portal project each product goes to, and with which key. Shared by portal-publish and fetch-portal.

The profile (docs/BA/specs/.ba-profile.yml) and .env at the repo root become a list of targets:
[(product, the .env variable, the key)]. A repo with one product uses PORTAL_PUBLISH_KEY. A repo with two or more
products sends each product to its own Portal project: tools.portal.products names, per product, the .env variable
that holds that project's key.

Every stop raises TargetError with a plain message that ends without "Nothing was sent / written": each caller adds
its own words. Messages name the product and the variable, never the key.

portal-publish imports this file; fetch-portal loads it with importlib, as it loads checks.py. One copy for both:
a drift here would send a page to the wrong client.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import yaml

PROFILE = "docs/BA/specs/.ba-profile.yml"
DEFAULT_KEY = "PORTAL_PUBLISH_KEY"
KEY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SETUP_HINT = "Run `ba-setup project`"
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class TargetError(Exception):
    """A setting is missing or wrong. The message is shown to the BA as it is, plus the caller's own ending."""


class Target(NamedTuple):
    product: str          # the product name ("" when the profile names no product)
    key_name: str         # the .env variable that holds the key
    key: str              # the key itself: never printed


def text(v) -> str:
    return "" if v is None else str(v).strip()


# ---------------------------------------------------------------- .env and git

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
        raise TargetError("git is not installed (or not on PATH). ba-tools needs git.") from None


def env_is_ignored(root: Path) -> bool:
    r = run_git(root, "check-ignore", "-q", ".env")
    if r.returncode == 128:
        raise TargetError(f"{root} is not a git repository, so git cannot keep .env out of commits. Run the skill "
                          "from the project repo.")
    return r.returncode == 0


def check_url(url: str) -> None:
    """The key travels in the request: plain http:// only to this computer or a .localhost / .test name."""
    import httpx                                  # here, so ba-setup's check can load this file without httpx
    try:
        u = httpx.URL(url)
    except httpx.InvalidURL:
        raise TargetError(f"tools.portal.url ({url}) is not a web address. {SETUP_HINT} to fix it.") from None
    host = (u.host or "").lower()
    if u.scheme == "https" and host:
        return
    if u.scheme == "http" and (host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".test")):
        return
    raise TargetError(f"tools.portal.url ({url}) must start with https:// — plain http:// would send the Publish "
                      "key unencrypted. http:// is allowed only for localhost, 127.0.0.1, *.localhost and *.test.")


def settings(root: Path) -> tuple[str, dict, dict]:
    """The Portal address, the profile and the values in .env. The keys themselves are read by read_keys."""
    prof_path = root / PROFILE
    if not prof_path.exists():
        raise TargetError(f"No project profile at {PROFILE}. {SETUP_HINT} first.")
    prof = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
    tools = (prof.get("tools") or {}) if isinstance(prof, dict) else None
    if not isinstance(tools, dict):
        raise TargetError(f"{PROFILE} is not laid out as a project profile (it, or its tools: part, is not a set "
                          f"of named settings). {SETUP_HINT} to fix it.")
    portal = tools.get("portal") or {}
    url = text(portal.get("url")).rstrip("/") if isinstance(portal, dict) else ""
    if not url:
        raise TargetError(f"The profile has no Portal address (tools.portal.url in {PROFILE}). {SETUP_HINT} to "
                          "add it.")
    check_url(url)
    env = root / ".env"
    if not env.exists():
        raise TargetError(f"There is no .env file at the repo root, so there is no Publish key. {SETUP_HINT}: it "
                          "puts the Publish key in .env.")
    if not env_is_ignored(root):
        raise TargetError(".env is not ignored by git (it is tracked, or .gitignore does not list it). The Publish "
                          "key must never be committed: add .env to .gitignore (and `git rm --cached .env` if it "
                          "was committed), then run again.")
    return url, prof, read_env_file(env)


# ---------------------------------------------------------------- products and keys

def key_map(prof: dict) -> dict[str, str]:
    """tools.portal.products: product name → the name of the .env variable that holds that Portal project's key,
    in the profile's order. Empty when the profile has none."""
    portal = (prof.get("tools") or {}).get("portal") or {}
    found = portal.get("products") if isinstance(portal, dict) else None
    if found in (None, "", {}):
        return {}
    if not isinstance(found, dict) or not all(
            isinstance(k, str) and k.strip() and isinstance(v, str) and KEY_NAME.fullmatch(v.strip())
            for k, v in found.items()):
        raise TargetError(f"tools.portal.products in {PROFILE} must name, for each product, the .env variable "
                          "that holds its Portal project's key, for example {AcmeLending: "
                          f"PORTAL_PUBLISH_KEY_ACME}}. {SETUP_HINT} to fix it.")
    names = {k.strip(): v.strip() for k, v in found.items()}
    seen: dict[str, str] = {}
    for product, name in names.items():           # one key per product: two products never share a project
        if name in seen:
            raise TargetError(f"tools.portal.products in {PROFILE} gives {seen[name]} and {product} the same .env "
                              f"variable ({name}), so both would go to the same Portal project. Each product "
                              f"needs its own Portal project and its own key. {SETUP_HINT} to fix it.")
        seen[name] = product
    return names


def key_names(prof: dict, products: list[str], only: str | None = None) -> dict[str, str]:
    """Which .env variable holds each product's key (only the product `only`, when given). A repo with one
    product: its tools.portal.products entry, else PORTAL_PUBLISH_KEY. Two or more: each needs its own entry."""
    found = key_map(prof)
    if len(products) == 1 and products[0] not in found:
        return {products[0]: DEFAULT_KEY}
    missing = [p for p in ([only] if only else products) if p not in found]
    if missing:
        example = ", ".join(f"{p}: PORTAL_PUBLISH_KEY_{re.sub(r'[^A-Z0-9]+', '_', p.upper()).strip('_')}"
                            for p in missing)
        raise TargetError(f"This repo has {len(products)} products ({', '.join(products)}). Each goes to its own "
                          "Portal project, with that project's own key. tools.portal.products in "
                          f"{PROFILE} names no key for: {', '.join(missing)}. Add one entry per product, naming the "
                          f".env variable that holds its key, for example {{{example}}}. {SETUP_HINT} to set it "
                          "up.")
    return {p: found[p] for p in ([only] if only else products)}


def read_keys(env: dict, names: dict[str, str]) -> dict[str, str]:
    """Each product's key from .env. A missing one stops, naming the variable (and the product)."""
    keys = {}
    for product, name in names.items():
        key = env.get(name, "").strip()
        if not key:
            whose = "" if name == DEFAULT_KEY or not product else f" (the Publish key for {product})"
            raise TargetError(f".env has no {name}{whose}. {SETUP_HINT}: it tells you where to get the key.")
        keys[product] = key
    return keys


def profile_products(prof: dict) -> list[str]:
    """The product names, read the way ba-dashboard's map/build.py reads them: tools.dashboard.map.products, else
    the profile's products that have a jira_project."""
    dash = (prof.get("tools") or {}).get("dashboard") or {}
    mapped = (dash.get("map") or {}).get("products") if isinstance(dash, dict) and isinstance(
        dash.get("map") or {}, dict) else None
    if isinstance(mapped, dict) and mapped:
        return list(dict.fromkeys(text(v) for v in mapped.values() if text(v)))
    return list(dict.fromkeys(text(p.get("name")) for p in prof.get("products") or []
                              if isinstance(p, dict) and p.get("jira_project") and text(p.get("name"))))


def portal_names(prof: dict) -> dict[str, str]:
    """Every product that has a Portal project → its .env variable, in tools.portal.products order. Without
    tools.portal.products: the one product (or "" when the profile names none) → PORTAL_PUBLISH_KEY; a repo with
    two or more products then stops, as the Dashboard send does."""
    found = key_map(prof)
    if found:
        return found
    products = profile_products(prof)
    if len(products) > 1:
        key_names(prof, products)                 # stops, naming every product and the setting
    return {(products[0] if products else ""): DEFAULT_KEY}


def portal_targets(root: Path, prof: dict, env: dict, only: list[str] | None = None) -> list[Target]:
    """[(product, .env variable, key)] in tools.portal.products order: every product, or only the ones named.
    A missing key stops, naming the product and the variable."""
    names = portal_names(prof)
    if only is not None:
        names = {p: n for p, n in names.items() if p in only}
    keys = read_keys(env, names)
    return [Target(p, n, keys[p]) for p, n in names.items()]
