"""dashboard.py check(): a feature's `open` and `tickets` must be lists.

Run: uv run --with pytest --with pyyaml pytest skills/ba-dashboard/tests
"""
import subprocess
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))
from dashboard import check  # noqa: E402

FEATURE = {"area": "Credit scorecard", "id": "scorecard", "prod": "AcmeLending", "stage": "spec", "who": "Sam",
           "since": "2026-10-01", "s": "The scorecard."}


def data(**over):
    return {"features": [dict(FEATURE, **over)], "awaiting": [], "todos": [], "agenda": []}


def test_open_as_a_list_passes():
    assert check(data(open=["Do we start with Ephrem's numbers?", "Who sets seniority?"], tickets=["ACME-1"])) == []


def test_no_open_and_no_tickets_pass():
    assert check(data()) == []


def test_open_as_one_block_of_text_is_refused():
    # What the 11 Nov scorecard row looked like: the questions written as one folded YAML string.
    d = yaml.safe_load("open: Do we start the parallel run? What does Uniformed score?\n  Who sets seniority?")
    problems = check(data(open=d["open"]))
    assert len(problems) == 1
    assert "features[0] 'Credit scorecard' → open must be a list" in problems[0]
    assert "every character" in problems[0]


def test_tickets_as_text_is_refused():
    problems = check(data(tickets="ACME-1695, ACME-1696"))
    assert len(problems) == 1 and "tickets must be a list" in problems[0]


def test_a_question_that_is_not_text_is_refused_and_a_blank_line_is_fine():
    problems = check(data(open=["A real question?", "", {"q": "x"}]))
    assert len(problems) == 1
    assert "not a line of text" in problems[0]


def test_the_map_build_stops_on_open_as_text(tmp_path):
    ba = tmp_path / "docs/BA"
    (ba / "specs").mkdir(parents=True)
    (ba / "dashboard.yaml").write_text(yaml.safe_dump(dict(data(open="One block. Of text?"), updated="2026-11-11")),
                                       encoding="utf-8")
    (ba / "specs/.ba-profile.yml").write_text("products: [{name: AcmeLending, jira_project: ACME}]\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(SKILL / "map/build.py"), "--root", str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0
    assert "open must be a list" in r.stderr
