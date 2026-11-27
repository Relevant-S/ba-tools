"""Refuse real client or project details in ba-tools. This repo is public: it holds generic tools and invented
examples only. Real values live in each project's own repo (its .ba-profile.yml, design profile, data files).

Run:   python -I scripts/check_no_client_data.py            # every tracked file
       python -I scripts/check_no_client_data.py --staged   # only what is about to be committed (the git hook)

It looks for shapes, not names, so the check itself gives nothing away:
  - an email whose domain is not an example one,
  - a Jira site, Slack workspace or GitHub owner that is not an example one,
  - a Figma file key, Google Drive folder id, Slack channel or user id, or Claude page link that is not a sample.

Your own words to refuse (client names, people) go in ~/.claude/ba-tools/denylist.txt, one regex per line.
That file stays on your machine and is never committed.

Exit code 1 and one line per finding when something is found. A line that must stay can end with the comment
`no-client-data: ok` (say why next to it).
"""
import pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = re.compile(r"(^|/)uv\.lock$|\.(png|jpe?g|gif|ico|docx|xlsx|pdf|woff2?)$")
OK_LINE = "no-client-data: ok"
FAKE = re.compile(r"(?i)example|sample|abcd|0000|fake|dummy|xxx|notap|somepage|test")

EMAIL_OK = re.compile(r"(?i)@([a-z0-9-]+\.)*(example\.(com|org|net)|[a-z0-9-]+\.example|example|"
                      r"relevant\.software|clientco\.com|client\.com|yourcompany\.com|x\.com)$")
GITHUB_OK = {"relevant-s", "example", "org", "anthropics", "figma", "acme-co", "northwind", "you", "your-org"}
RULES = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     lambda m: not EMAIL_OK.search(m.group(0))),
    ("Jira site", re.compile(r"\b([a-z0-9-]+)\.atlassian\.net"),
     lambda m: m.group(1) not in {"example", "yourcompany", "your-site", "acme", "id"}),
    ("Slack workspace", re.compile(r"\b([a-z0-9-]+)\.slack\.com"),
     lambda m: m.group(1) not in {"yourworkspace", "example", "app", "api"}),
    ("GitHub owner", re.compile(r"github\.com/([A-Za-z0-9_.-]+)"),
     lambda m: m.group(1).lower() not in GITHUB_OK),
    ("Figma file key", re.compile(r"(?:figma\.com/(?:design|file|board|proto)/|\bkey:\s*|figma_file:\s*|file_key:\s*)"
                                  r"([A-Za-z0-9]{15,})"),
     lambda m: not FAKE.search(m.group(1))),
    ("Google Drive id", re.compile(r"\b1[A-Za-z0-9_-]{32}\b"),
     lambda m: not FAKE.search(m.group(0)) and m.group(0).count("-") < 3 and re.search(r"[A-Z]", m.group(0))),
    ("Slack id", re.compile(r"\b[CGU]0[0-9A-Z]{8,10}\b"), lambda m: not FAKE.search(m.group(0)) and "ABCD" not in m.group(0)),
    ("Claude page link", re.compile(r"claude\.ai/(?:code/)?artifact/([A-Za-z0-9]{20,24})\b"),
     lambda m: not FAKE.search(m.group(1))),
]


def own_words():
    p = pathlib.Path.home() / ".claude" / "ba-tools" / "denylist.txt"
    if not p.exists():
        return []
    words = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return [("your denylist", re.compile(w, re.I), lambda m: True) for w in words]


def files(staged):
    if staged:
        out = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                             capture_output=True, text=True).stdout
    else:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout
    return [f for f in out.splitlines() if f and not SKIP.search(f)]


def text_of(rel, staged):
    if staged:
        raw = subprocess.run(["git", "-C", str(ROOT), "show", ":" + rel], capture_output=True).stdout
    else:
        raw = (ROOT / rel).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def main():
    staged = "--staged" in sys.argv
    rules = RULES + own_words()
    found = []
    for rel in files(staged):
        if rel == "scripts/check_no_client_data.py":
            continue
        for n, line in enumerate(text_of(rel, staged).splitlines(), 1):
            if OK_LINE in line:
                continue
            for kind, rx, bad in rules:
                for m in rx.finditer(line):
                    if bad(m):
                        found.append(f"{rel}:{n}: {kind}: {m.group(0)[:60]}")
    if found:
        print("Real client or project details found. ba-tools is public: use invented values "
              "(example.com, Acme, SampleFileKey…), or keep the real ones in the project's own repo.")
        print("\n".join(found))
        sys.exit(1)
    print("No client details found.")


if __name__ == "__main__":
    main()
