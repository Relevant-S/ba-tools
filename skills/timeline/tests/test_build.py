"""build.py: the `upcoming:` list (checks and tidy-up) and the release lines (future releases kept)."""
import datetime as dt

import pytest
import yaml

from build import DataError, check_upcoming, release_lines

FEATURES = {"tidio", "w3w", "landing"}


def items(text):
    return yaml.safe_load(text)["upcoming"]


def test_the_three_easy_payday_events():
    out = check_upcoming(items("""
upcoming:
  - id: tidio-off
    title: Switch off Tidio on the website
    kind: deadline
    date: 2026-12-17
    needs: [tidio]
    what:
      - Acme Lending removes the Tidio chat from the website by 17 Dec.
      - Our own AI assistant must be live before then.
    who: Acme Lending, Relevant
  - id: pips-perks-v2
    title: New Pips Perks agreement — every customer signs it
    kind: planned
    after: w3w
  - id: new-brand
    title: New landing page and style guide
    kind: planned
    needs: landing
"""), FEATURES)
    assert out[0] == {"id": "tidio-off", "title": "Switch off Tidio on the website", "kind": "deadline", "date": "2026-12-17",
                      "needs": ["tidio"], "who": "Acme Lending, Relevant",
                      "what": ["Acme Lending removes the Tidio chat from the website by 17 Dec.", "Our own AI assistant must be live before then."]}
    assert out[1] == {"id": "pips-perks-v2", "title": "New Pips Perks agreement — every customer signs it", "kind": "planned", "after": "w3w"}
    assert out[2] == {"id": "new-brand", "title": "New landing page and style guide", "kind": "planned", "needs": ["landing"]}


def test_none_is_an_empty_list():
    assert check_upcoming(None, FEATURES) == []
    assert check_upcoming([], FEATURES) == []


def test_what_as_text_becomes_lines_and_who_as_list_joins():
    out = check_upcoming([{"id": "a", "title": "A", "kind": "release", "date": "2027-01-04",
                           "what": "- first\n- second\n\nthird", "who": ["Acme Lending", "Relevant"]}], FEATURES)
    assert out[0]["what"] == ["first", "second", "third"]
    assert out[0]["who"] == "Acme Lending, Relevant"
    assert out[0]["date"] == "2027-01-04"


@pytest.mark.parametrize("bad, words", [
    ([{"id": "a", "title": "A", "kind": "planned", "needs": ["nope"]}], 'upcoming item "a": "needs" names nope'),
    ([{"id": "a", "title": "A", "kind": "planned", "after": "nope"}], 'upcoming item "a": "after: nope" is not a feature'),
    ([{"id": "a", "title": "A", "kind": "planned"}, {"id": "a", "title": "B", "kind": "planned"}], 'upcoming item "a": the id is used twice'),
    ([{"id": "a", "title": "A", "kind": "planned", "date": dt.date(2026, 12, 1), "after": "w3w"}], 'upcoming item "a": has both a date and "after"'),
    ([{"id": "a", "title": "A", "kind": "milestone"}], 'upcoming item "a": kind must be deadline, release or planned'),
    ([{"id": "a", "title": "x" * 301, "kind": "planned"}], 'upcoming item "a": the title is longer than 300'),
    ([{"id": "a", "title": "A", "kind": "planned", "who": "x" * 201}], 'upcoming item "a": "who" is longer than 200'),
    ([{"id": "a", "title": "A", "kind": "planned", "what": ["x"] * 21}], 'upcoming item "a": "what" has more than 20 lines'),
    ([{"id": "a", "title": "A", "kind": "planned", "date": "17 Dec"}], 'upcoming item "a": the date "17 Dec" is not a date'),
    ([{"id": "a", "title": "A", "kind": "planned", "when": "soon"}], 'upcoming item "a": unknown field when'),
    ([{"title": "A", "kind": "planned"}], "upcoming item 1: has no id"),
    ([{"id": "a", "kind": "planned"}], 'upcoming item "a": has no title'),
    ({"id": "a"}, "upcoming: must be a list"),
])
def test_bad_data_stops_with_one_plain_line(bad, words):
    with pytest.raises(DataError) as e:
        check_upcoming(bad, FEATURES)
    assert str(e.value).startswith(words)
    assert "\n" not in str(e.value)


def test_future_releases_are_kept():
    today = dt.date(2026, 11, 8)
    rel = [
        {"name": "6.2 - Standing order", "date": "2026-09-30", "released": True},
        {"name": "6.5 - What3Words", "date": "2026-12-31", "released": False},
        {"name": "New Landing page", "date": "2026-12-31", "released": False},
        {"name": "6.1 - AI assistant", "date": None, "released": False},
        {"name": "Late, not released", "date": "2026-10-01", "released": False},
        {"name": "Today", "date": "2026-11-08", "released": False},
    ]
    assert [r["name"] for r in release_lines(rel, today)] == ["6.2 - Standing order", "Today", "6.5 - What3Words", "New Landing page"]

