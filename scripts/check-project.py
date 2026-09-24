"""Check a project against the installed ba-tools: the profile has every key, and the project's copy of
the spec template is byte-identical to the one in ba-tools.

    uv run --with pyyaml python scripts/check-project.py <project-root>
"""
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent.parent
TEMPLATE = TOOLS / "skills/ba-spec/assets/spec-template.md"
REQUIRED = ["profile_version", "ba_tools_version", "project", "products", "decider_model", "downstream",
            "cadence", "release_folders", "conflict_scope", "ids", "prd", "code", "spec_links", "client_review"]


def main(root: Path) -> int:
    problems = []
    profile_path = root / "docs/BA/specs/.ba-profile.yml"
    if not profile_path.exists():
        print(f"FAIL  no profile at {profile_path}")
        return 1
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}

    problems += [f"profile is missing `{k}`" for k in REQUIRED if k not in profile]
    if profile.get("profile_version") != 1:
        problems.append(f"profile_version is {profile.get('profile_version')!r}, ba-tools expects 1")
    for p in profile.get("products", []):
        if not p.get("roles", {}).get("list"):
            problems.append(f"product `{p.get('key')}` has no roles.list")
    if "jira" in (profile.get("downstream") or []) and "jira" not in profile:
        problems.append("downstream includes jira but there is no `jira` block")

    tools_version = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8").split("---")[1])["ba_tools_version"]
    if profile.get("ba_tools_version") != tools_version:
        problems.append(f"profile says ba_tools_version {profile.get('ba_tools_version')}, ba-tools is {tools_version}")

    copy = root / "docs/BA/specs/_template.md"
    if copy.exists() and copy.read_bytes() != TEMPLATE.read_bytes():
        problems.append("docs/BA/specs/_template.md differs from ba-tools - it was edited locally or is out of date; "
                        "move any project fact into the profile and reinstall the template")

    for line in problems:
        print(f"FAIL  {line}")
    if not problems:
        print(f"OK    {root} matches ba-tools {tools_version}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()))
