"""Install or update ba-tools in a project.

    git -C <ba-tools> pull
    uv run --with pyyaml python <ba-tools>/scripts/install.py <project-root> [--dry-run]

What it does, and nothing else:
  1. Copies every skill in <ba-tools>/skills/ into <project>/.claude/skills/, replacing the old copy of
     each (other skills in that folder — BMad, project-only ones — are left alone). Personal state is
     never copied.
  2. Copies the spec template to <project>/docs/BA/specs/_template.md.
  3. Sets ba_tools_version in the project profile, if the project has one.
  4. Installs the one npm dependency (the confluence skill's `marked`) when it is missing.
  5. Prints what changed, skill by skill. It never commits — review with `git status`, then commit.
"""
import filecmp
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent.parent
SKILLS = TOOLS / "skills"
TEMPLATE = SKILLS / "ba-spec/assets/spec-template.md"
SKIP = {"state", "node_modules", "__pycache__"}


def version():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8").split("---")[1])["ba_tools_version"]


def files(root: Path):
    return sorted(p.relative_to(root) for p in root.rglob("*")
                  if p.is_file() and not SKIP.intersection(p.relative_to(root).parts))


def same_tree(a: Path, b: Path) -> bool:
    if not b.exists():
        return False
    fa, fb = files(a), files(b)
    if fa != fb:
        return False
    return all(filecmp.cmp(a / f, b / f, shallow=False) or
               (a / f).read_bytes().replace(b"\r\n", b"\n") == (b / f).read_bytes().replace(b"\r\n", b"\n")
               for f in fa)


def main(root: Path, dry: bool):
    if not (root / ".git").exists() and not (root / "docs").exists():
        sys.exit(f"{root} does not look like a project (no .git or docs/).")
    report = {"project": str(root), "ba_tools_version": version(), "dry_run": dry, "skills": {}, "other": []}
    dest = root / ".claude/skills"
    for skill in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        target = dest / skill.name
        state = "unchanged" if same_tree(skill, target) else ("updated" if target.exists() else "added")
        report["skills"][skill.name] = state
        if state != "unchanged" and not dry:
            keep = {}
            for s in SKIP:  # keep personal state and installed dependencies across an update
                for p in target.rglob(s) if target.exists() else []:
                    tmp = root / ".ba-tools-keep" / skill.name / p.relative_to(target)
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(p), str(tmp))
                    keep[p.relative_to(target)] = tmp
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(skill, target, ignore=shutil.ignore_patterns(*SKIP))
            for rel, tmp in keep.items():
                (target / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp), str(target / rel))
    shutil.rmtree(root / ".ba-tools-keep", ignore_errors=True)

    copy = root / "docs/BA/specs/_template.md"
    if copy.parent.exists():
        if not copy.exists() or copy.read_bytes().replace(b"\r\n", b"\n") != TEMPLATE.read_bytes():
            report["other"].append("docs/BA/specs/_template.md updated")
            if not dry:
                shutil.copyfile(TEMPLATE, copy)

    prof = root / "docs/BA/specs/.ba-profile.yml"
    if prof.exists():
        text = prof.read_text(encoding="utf-8")
        new = re.sub(r"(?m)^ba_tools_version:\s*\S+", f"ba_tools_version: {version()}", text)
        if new != text:
            report["other"].append(f"profile ba_tools_version → {version()}")
            if not dry:
                prof.write_text(new, encoding="utf-8", newline="\n") if sys.version_info >= (3, 10) else prof.write_text(new, encoding="utf-8")
    else:
        report["other"].append("no project profile yet — run the ba-setup skill in `project` mode")

    conf = dest / "confluence/scripts"
    if conf.exists() and not (conf / "node_modules/marked").exists():
        report["other"].append("confluence: npm install (marked)")
        if not dry:
            npm = shutil.which("npm") or shutil.which("npm.cmd")
            if npm:
                subprocess.run([npm, "install", "--silent"], cwd=conf, check=False)
            else:
                report["other"].append("  ⚠ npm not found — run `npm install` in .claude/skills/confluence/scripts")

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(Path(args[0] if args else ".").resolve(), "--dry-run" in sys.argv)
