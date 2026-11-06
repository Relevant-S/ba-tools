"""Tracker plug-ins for the timeline build.

A plug-in is a module here named after the tracker (`jira.py`, `github_bmad.py`) with a class `Tracker`
that extends `Base`. The shared build calls these methods; each has a do-nothing default, so a project with
no tracker (`tracker: none`) still gets a page built from the dashboard and its recorded features.

`ctx` (given to __init__) holds: `ba` (the project's docs/BA folder), `repo` (the docs repo root), `here` (the
folder of the timeline data file), `tl` (the timeline data file), `dash` (dashboard.yaml), `data` (the dashboard's
built data), `start`, `today`, `product` (the product settings) and `add_pin(day, kind, who=None, subject=None)`.
"""


class Base:
    name = "none"
    title = "the tracker"          # "Jira", "GitHub" — used in "See all in …" and guess notes
    work_link = ""                 # base link for a work item id

    def __init__(self, ctx):
        self.ctx = ctx

    def prepare(self, dashboard_features):
        """Read what the tracker needs, once, before any row is built. `dashboard_features` = the dashboard's
        built feature dicts on this timeline (with their `tickets`)."""

    def feature(self, f, out, first):
        """Fill a dashboard feature's stage data from the tracker, in place: `stages`, `stage`, `doneDate`,
        `basis` ("tracker" or "code"), `basisNote`, `work`, `tags`. `f` = the dashboard's built feature,
        `first` = the earliest day the dashboard knows of it. Not called for recorded features."""

    def feature_work(self, f):
        """The work items of a dashboard feature whose stage dates are recorded by hand (its tickets or stories)."""
        return []

    def work_items(self, ids):
        """[{id, title, status, url, done}] for these work item ids (a recorded request's `jira:` list)."""
        return [{"id": i, "title": "", "status": "", "done": None} for i in ids or []]

    def tags_of_work(self, work):
        """The releases or phases these work items are planned for."""
        return []

    def extra_rows(self, on_dashboard):
        """{area: [feature rows]} — work that is not on the dashboard: old Jira stories, specs, MVP stories.
        Each row has `origin` ("old-work" or "spec") and the usual feature fields."""
        return {}

    def add_requests(self, rows_by_id):
        """Add changes and bugs under their features (`requests`), in place."""

    def releases(self, default):
        """The release lines. `default` = the dashboard's released releases for this product."""
        return default

    def area_link(self, area):
        """{url, label} for "see all in the tracker" in the area panel, or None."""
        return None

    def footer(self):
        """What the page is built from, for the footer (after "Built <date> from …")."""
        return "the BA dashboard, the timeline data file and the intake files."
