import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SL = os.path.join(ROOT, "project", "slides")
os.makedirs(SL, exist_ok=True)

NAVY, CREAM, WHITE, BORDER = "#15213B", "#F6F4EF", "#FFFFFF", "#E6E2D9"
ORANGE, ORANGE_TXT, TINT = "#F2A541", "#B8660A", "#FFF4E0"
BLUE, PURPLE, CORAL, GREEN, SLATE = "#3B82F6", "#7C3AED", "#EF5B5B", "#0F9D76", "#475569"
BODY, MUTED, ONDARK_BODY = "#2B3547", "#5F6673", "#C5CEDC"
F = "font-family:Poppins, Arial, sans-serif"
MONO = "font-family:'JetBrains Mono', 'Courier New', monospace"
TOTAL = 18

order, sections, n = [], {}, [0]


def foot(dark=False):
    c = "#8C95A6" if dark else MUTED
    return (f'<p style="position:absolute; left:128px; bottom:64px; width:900px; font-size:24px; color:{c}">Relevant BA method  |  BA guide</p>'
            f'<p style="position:absolute; right:128px; bottom:64px; width:300px; font-size:24px; color:{c}; text-align:right">{n[0]} / {TOTAL}</p>')


def slide(sid, body, notes="", bg=CREAM, dark=False, section=None, layout=None, footer=True):
    n[0] += 1
    order.append(sid)
    if section:
        sections[f"s{len(sections) + 1}"] = {"description": section, "start": sid}
    lay = layout or "display:flex; flex-direction:column; gap:32px"
    html = (f'<section id="{sid}" data-transition="fade" style="background:{bg}; color:{WHITE if dark else NAVY}; {F}; '
            f'padding:128px 128px 160px; {lay}">\n{body}\n{foot(dark) if footer else ""}\n'
            + (f"<aside>{notes}</aside>\n" if notes else "") + "</section>\n")
    open(os.path.join(SL, f"{sid}.html"), "w", encoding="utf-8", newline="\n").write(html)


def head(eb, title, lead=None):
    h = (f'<div style="display:flex; flex-direction:column; gap:12px">'
         f'<div style="display:flex; align-items:center; gap:20px"><div style="width:72px; height:8px; background:{ORANGE}"></div>'
         f'<p style="font-size:24px; font-weight:500; letter-spacing:1px; text-transform:uppercase; color:{MUTED}">{eb}</p></div>'
         f'<h2 style="font-size:72px; font-weight:700; line-height:1.1; color:{NAVY}">{title}</h2></div>')
    if lead:
        h += f'<p style="font-size:28px; line-height:1.45; color:{MUTED}">{lead}</p>'
    return h


def card(inner, extra="", pad="28px 36px"):
    return f'<div style="display:flex; flex-direction:column; gap:8px; background:{WHITE}; border:1px solid {BORDER}; border-radius:20px; padding:{pad}; {extra}">{inner}</div>'


def t(text, size=28, w=600, c=NAVY, extra=""):
    return f'<p style="font-size:{size}px; font-weight:{w}; line-height:1.3; color:{c}; {extra}">{text}</p>'


def bullets(items, dot=ORANGE, size=26, c=BODY, gap=14):
    rows = "".join(
        f'<div style="display:flex; gap:16px; align-items:flex-start"><div style="width:12px; height:12px; border-radius:50%; background:{dot}; flex:none; transform:translateY(14px)"></div>'
        f'<p style="font-size:{size}px; line-height:1.4; color:{c}">{i}</p></div>' for i in items)
    return f'<div style="display:flex; flex-direction:column; gap:{gap}px">{rows}</div>'


def callout(text):
    return f'<p style="font-size:26px; font-weight:500; color:{NAVY}; background:{TINT}; border:2px solid {ORANGE}; border-radius:16px; padding:18px 28px">{text}</p>'


# 1 ── cover
bars = "".join(f'<div style="width:80px; height:12px; background:{c}"></div>' for c in (BLUE, PURPLE, CORAL, GREEN))
slide("cover",
      f'<div style="display:flex; gap:12px">{bars}</div>'
      f'<div style="display:flex; flex-direction:column; gap:8px"><h1 style="font-size:128px; font-weight:700; line-height:1.05; color:{WHITE}">Our BA approach</h1>'
      f'<p style="font-size:52px; font-weight:300; line-height:1.2; color:{ONDARK_BODY}">A guide for Business Analysts at Relevant</p></div>'
      f'<div style="display:flex; flex-direction:column; gap:12px; padding-top:80px"><p style="font-size:30px; color:{ORANGE}">AI-assisted, spec-first, feature by feature</p>'
      f'<p style="font-size:26px; color:#8C95A6">What it is, how it differs from classical business analysis, and how to get productive in two weeks</p></div>',
      "A guide for a BA joining the team. It sits next to the setup manual in ba-tools, which covers the connections step by step.",
      bg=NAVY, dark=True, section="The approach and how it differs",
      layout="display:flex; flex-direction:column; gap:40px; justify-content:center")

# 2 ── the big idea
slide("idea",
      head("The big idea", "What is our BA approach?") +
      '<div style="display:flex; gap:56px; flex:1">'
      '<div style="flex:1; display:flex; flex-direction:column; gap:32px">'
      + t("Classical business analysis turns meetings into one big requirements document. We work feature by feature: every client signal is captured, sorted, written into a checked spec, agreed with the client question by question, and only then handed to development.", 30, 400, BODY, "line-height:1.5") +
      bullets(["Claude Code does the legwork: pulling calls and emails, drafting, checking the code",
               "One spec template for every project, with a gate that refuses to call a spec ready on trust",
               "One page per feature where the client answers the open questions",
               "The same toolset in every project; only a settings file differs"]) + '</div>'
      f'<div style="width:520px; display:flex; flex-direction:column; gap:24px; background:{NAVY}; border-radius:24px; padding:48px; align-self:flex-start">'
      f'<p style="font-size:24px; font-weight:500; letter-spacing:1px; text-transform:uppercase; color:{ORANGE}">The mindset shift</p>'
      f'<p style="font-size:40px; font-weight:700; line-height:1.2; color:{WHITE}">The BA decides. The tools do the legwork.</p>'
      f'<p style="font-size:26px; line-height:1.45; color:{ONDARK_BODY}">Nothing reaches the client, Jira or git without your yes. Claude drafts, checks and asks; you judge what is true for this business.</p></div></div>',
      "The one idea to leave with: the process is stricter than classical BA, and the tools make that strictness cheap.")

# 3 ── classical vs ours, mapped
rows = [
    ("Meeting notes written from memory", "Calls, emails and Slack threads pulled in automatically"),
    ("Sorting the asks in your head", "A triage report you approve item by item"),
    ("One big requirements document", "One spec per feature: thin first, then full"),
    ("Peer review, if time allows", "A ready gate of eight checks before any hand-off"),
    ("Designer works from the finished document", "A concept per feature, drawn from the design system"),
    ("Client signs off the whole document", "A clarification page per feature, one question at a time"),
    ("Requirements pasted into Jira", "The ticket links the spec; one PRD per phase"),
]
rr = "".join(card(
    f'<div style="display:flex; align-items:center; gap:32px"><p style="width:640px; font-size:27px; font-weight:600; color:{NAVY}">{a}</p>'
    f'<x-shape kind="arrow-right" style="width:60px; height:26px; background:{ORANGE}"></x-shape>'
    f'<p style="flex:1; font-size:27px; color:{BODY}">{b}</p></div>', pad="16px 28px") for a, b in rows)
slide("mapped",
      head("Classical BA, mapped", "What changes for you") +
      f'<div style="display:flex; gap:32px"><p style="width:668px; font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}">Classical BA</p>'
      f'<p style="padding-left:104px; font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}">Our approach</p></div>'
      f'<div style="display:flex; flex-direction:column; gap:10px">{rr}</div>',
      "Same craft, stricter process, better tools. Nothing on the left is wrong — it just leaves quality to whoever has time.")

# 4 ── five stages
stages = [
    (BLUE, "1", "Capture", "Automatic", ["Client calls from Fireflies", "Client emails", "Slack threads"], "only the client's"),
    (PURPLE, "2", "Triage", "You approve", ["New spec", "Change to a ticket", "Dashboard item or note"], "each item, one by one"),
    (CORAL, "3", "Specify", "ba-spec", ["Thin spec first", "Edge cases and code check", "The ready gate"], ""),
    (GREEN, "4", "Agree", "With the client", ["Clarification page", "Figma concept", "Answers into the spec"], ""),
    (SLATE, "5", "Hand off", "Tracker, not spec", ["Jira ticket with a link", "or the phase PRD", "then development"], ""),
]
sc = "".join(
    f'<div style="flex:1; display:flex; flex-direction:column; background:{WHITE}; border:1px solid {BORDER}; border-radius:20px; overflow:hidden">'
    f'<div style="display:flex; gap:16px; align-items:center; background:{c}; padding:24px 24px"><p style="font-size:56px; font-weight:700; color:{WHITE}">{num}</p>'
    f'<div style="display:flex; flex-direction:column"><p style="font-size:30px; font-weight:700; color:{WHITE}">{name}</p><p style="font-size:24px; color:{WHITE}">{sub}</p></div></div>'
    f'<div style="padding:28px 24px">{bullets(items, c, 24, BODY, 16)}</div></div>'
    for c, num, name, sub, items, _ in stages)
slide("stages",
      head("How work flows", "The five stages") +
      f'<div style="display:flex; gap:20px; flex:1">{sc}</div>' +
      callout("Stages 2 to 4 are your home turf. Stage 5 is where the developers — and BMad's own tools — take over."),
      "Walk the cards left to right. Capture is automatic; everything after it needs a BA decision.")

# 5 ── right-sized specs
sizes = [
    (GREEN, "xs", "A label, a field, a bug fix", "Need, Rules, Out of scope, Decisions, the ready checklist", "Under 60 lines"),
    (BLUE, "s", "A small flow change, a price or a text change", "Need to Open questions, Existing code, the checklist", "Under 150 lines"),
    (PURPLE, "m", "A screen, a set of rules", "As s, plus UX — and data, roles or NFRs when they apply", "Under 250 lines"),
    (CORAL, "l", "A module, a new money flow, a new surface", "All 16 sections", "Under 400 lines"),
]
zc = "".join(card(
    f'<p style="font-size:56px; font-weight:700; color:{NAVY}">{s}</p>'
    f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}; padding-top:4px">When</p>{t(w, 26, 400, BODY)}'
    f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}; padding-top:4px">Sections</p>{t(sec, 26, 400, BODY)}'
    f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}; padding-top:4px">Length</p>{t(l, 26, 600, NAVY)}',
    f"flex:1; border-top:10px solid {c}") for c, s, w, sec, l in sizes)
slide("sizes",
      head("One template, every project", "Right-sized specs") +
      f'<div style="display:flex; gap:24px">{zc}</div>' +
      t("16 sections; the size of the change decides how many you write. Bigger than l? Split it. Running long? Cut — “n/a” is a whole answer.", 26, 500, MUTED),
      "The most common beginner mistake is writing every section for a one-line change. Pick the size first.",
      section="The spec and its gate")

# 6 ── inside a spec
secs = [("Need", "the problem and the outcome"), ("Business value", "why it is worth doing"), ("Rules", "numbered, each with a source"),
        ("Edge cases", "ten rows, every one answered"), ("Out of scope", "and deliberate removals"), ("Decisions", "who, when, and the quote"),
        ("Conflicts", "what it was checked against"), ("Assumptions", "confirmed or only assumed"), ("Open", "only others' questions"),
        ("Data model", "real fields, any migration"), ("Roles", "every role, and the denied view"), ("Non-functional", "speed, audit, privacy"),
        ("UX", "the frames, and what is left"), ("Existing code", "read at a named commit"), ("Slicing", "pieces with value alone"),
        ("Ready checklist", "the gate")]
new = {"Edge cases", "Existing code"}
cc = "".join(card(
    f'<div style="display:flex; gap:16px; align-items:center"><div style="width:48px; height:48px; border-radius:50%; background:{ORANGE if name in new else CORAL}; display:flex; align-items:center; justify-content:center; flex:none">'
    f'<p style="font-size:24px; font-weight:700; color:{WHITE}">{i}</p></div>'
    f'<div style="display:flex; flex-direction:column"><p style="font-size:26px; font-weight:700; color:{NAVY}">{name}</p><p style="font-size:24px; color:{BODY}">{d}</p></div></div>',
    f"border:2px solid {ORANGE}; background:{TINT}" if name in new else "", pad="14px 20px") for i, (name, d) in enumerate(secs, 1))
slide("inside",
      head("The spec", "Inside a spec") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:16px">{cc}</div>' +
      t("Highlighted: the two sections classical specs skip — and the ones that most often change the work.", 26, 500, MUTED),
      "Edge cases and existing code are separate steps in the ba-spec skill, so they cannot be quietly skipped.")

# 7 ── the ready gate
checks = ["No open questions — or each one knowingly accepted", "Every assumption confirmed or accepted", "Every edge case answered, or marked n/a", "The conflict check actually run",
          "Every rule has a source", "A design for every screen, or the gap listed", "Code checked at a named commit", "Size and destination set"]
gc = "".join(card(f'<div style="display:flex; gap:16px; align-items:center"><x-icon name="CheckCircle" style="color:{GREEN}; width:40px; height:40px"></x-icon>{t(c, 26, 500, NAVY)}</div>', pad="20px 24px") for c in checks)
slide("gate",
      head("Quality before hand-off", "The ready gate") +
      '<div style="display:flex; gap:40px">'
      f'<div style="flex:1; display:grid; grid-template-columns:1fr 1fr; gap:16px">{gc}</div>'
      f'<div style="width:480px; display:flex; flex-direction:column; gap:20px; background:{NAVY}; border-radius:24px; padding:44px; align-self:flex-start">'
      f'<p style="font-size:24px; font-weight:500; letter-spacing:1px; text-transform:uppercase; color:{ORANGE}">If a box will not tick</p>'
      f'<p style="font-size:34px; font-weight:700; line-height:1.25; color:{WHITE}">Say so in the spec.</p>'
      f'<p style="font-size:26px; line-height:1.45; color:{ONDARK_BODY}">Which box, why it was accepted, who decided, and the date. A blocker you can name is a decision; one let through silently is not.</p></div></div>',
      "Before the gate existed, five specs had been filed with open questions still on them.")

# 8 ── working with the client
crow = [
    (BLUE, "Design", "A Figma concept, one screen per question", "Comments on the frames", "Extra input to the spec"),
    (PURPLE, "Questions", "The clarification page for the feature", "Picks options and writes notes, on the call", "Dated decisions in the spec"),
    (CORAL, "Settled feature", "A feature brief on Confluence, if the project uses it", "Reads the requirements, comments", "Extra input; answers still go on the page"),
    (GREEN, "Hand-off", "Nothing new — the spec stays internal", "Accepts the working feature later", "A ticket, or the phase PRD"),
]
cr = "".join(
    f'<div style="display:flex; align-items:center; gap:24px; background:{WHITE}; border:1px solid {BORDER}; border-left:10px solid {c}; border-radius:16px; padding:18px 28px">'
    f'<p style="width:280px; font-size:28px; font-weight:700; color:{NAVY}">{a}</p><p style="width:520px; font-size:25px; color:{BODY}">{b}</p>'
    f'<p style="width:400px; font-size:25px; color:{BODY}">{r}</p><p style="flex:1; font-size:25px; font-weight:600; color:{NAVY}">{g}</p></div>'
    for c, a, b, r, g in crow)
hdr = "".join(f'<p style="width:{w}; font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}">{h}</p>'
              for h, w in [("Stage", "280px"), ("What the client sees", "520px"), ("Client's role", "400px"), ("Where it lands", "auto")])
slide("client",
      head("When the client is involved", "Working with the client", "The clarification page is where the client answers. Everything else shows them the requirements.") +
      f'<div style="display:flex; gap:24px; padding:0 38px">{hdr}</div>'
      f'<div style="display:flex; flex-direction:column; gap:12px">{cr}</div>',
      "Rule of thumb: the client approves the what and the why, question by question; the team owns the how.",
      section="The client, new projects and the tools")

# 9 ── good practice
gp = [
    ("Answers live in the spec", "The page is a surface. Every answer goes into the spec's decisions, dated."),
    ("One page, one link", "Republish each round to the same link, then move the share pin."),
    ("Say what each option costs", "Name the consequence, not just the choice. Mark our recommendation as ours."),
    ("Never invent the client's words", "Every rule names its source. A guess is labelled and becomes a question."),
    ("Only ask what they must answer", "If the BA can decide it, decide it and log it. Short lists get answers."),
    ("Nothing leaves without a yes", "Claude drafts pages, tickets and messages; a BA reviews and sends them."),
]
gc2 = "".join(
    f'<div style="display:flex; flex-direction:column; gap:10px; background:{WHITE}; border:1px solid {BORDER}; border-left:10px solid {GREEN}; border-radius:16px; padding:20px 32px">'
    f'{t(a, 30, 700, NAVY)}{t(b, 25, 400, BODY, "line-height:1.4")}</div>' for a, b in gp)
slide("practice",
      head("How to present and agree", "Client cooperation: good practice") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px">{gc2}</div>' +
      callout("Check the contract and NDA before feeding client files or transcripts into AI tools."),
      "Every one of these came from a real correction on a live project.")

# 10 ── new projects
chain = [("Brief", "BMad", False), ("Thin specs", "ours", True), ("Design ⇄ client", "ours", True), ("Full spec ⇄ client", "ours", True),
         ("Ready gate", "ours", True), ("PRD, phase N", "BMad", False), ("Build", "developers", False)]
ch = ""
for i, (a, who, ours) in enumerate(chain):
    fill, tc, sc_ = (NAVY, WHITE, ORANGE) if ours else (WHITE, NAVY, MUTED)
    ch += (f'<div style="flex:1; display:flex; flex-direction:column; gap:8px; align-items:center; justify-content:center; background:{fill}; border:1px solid {BORDER}; border-radius:18px; padding:24px 12px; height:170px">'
           f'<p style="font-size:26px; font-weight:700; line-height:1.2; color:{tc}; text-align:center">{a}</p><p style="font-size:24px; color:{sc_}; text-align:center">{who}</p></div>')
    if i < len(chain) - 1:
        ch += f'<x-shape kind="arrow-right" style="width:32px; height:18px; background:{MUTED}"></x-shape>'
slide("newproject",
      head("A brand-new client", "Feature by feature, then phase by phase") +
      f'<div style="display:flex; align-items:center; gap:10px">{ch}</div>' +
      '<div style="display:flex; gap:48px">'
      '<div style="flex:1">' + bullets([
          "BMad writes the whole PRD first; we agree each feature with the client first",
          "Features with no screens skip the design step",
          "Triage starts once there are specs to compare new asks against",
          "Each phase gets its own PRD, built from that phase's ready specs"]) + '</div>'
      f'<div style="width:560px; display:flex; flex-direction:column; gap:16px; background:{NAVY}; border-radius:24px; padding:40px">'
      f'<p style="font-size:24px; font-weight:500; letter-spacing:1px; text-transform:uppercase; color:{ORANGE}">On a live product too</p>'
      f'<p style="font-size:26px; line-height:1.45; color:{ONDARK_BODY}">Same shape: one PRD per phase, combined from that phase\'s ready specs. Small fixes can still go straight to a Jira ticket. Nobody keeps one big PRD up to date.</p></div></div>',
      "Dark boxes are ours, white boxes are BMad or the developers. A long-running project's old whole-system PRD stays frozen at its last release.")

# 10b ── where the answers live
truth = [
    (BLUE, "How it works today", "The code", "Ask Claude — it reads the code on the development branch. No document is kept in step with it."),
    (PURPLE, "Why it works that way", "The specs", "Each spec keeps the rules, the dated decisions and who made them."),
    (CORAL, "What a field is called", "The data dictionary", "Every table and field: type, required, min and max, the label on screen. Generated from the code."),
    (GREEN, "Which messages go out", "The messages catalogue", "Every email, in-app, push and SMS message, with its trigger and recipients. A spec names one by its id, like M-012."),
]
tc2 = "".join(card(
    f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{MUTED}">{q}</p>'
    f'<p style="font-size:34px; font-weight:700; color:{c}">{a}</p>{t(d, 25, 400, BODY, "line-height:1.4")}',
    f"border-top:10px solid {c}", pad="24px 32px") for c, q, a, d in truth)
slide("truth",
      head("No single big document", "Where the answers live") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px">{tc2}</div>' +
      callout("Client files — the SOW, their spreadsheets, recordings — go in <b>docs/BA/reference/</b>, listed in its README. Recordings stay out of git."),
      "BMad itself stopped writing whole-system documents: agents read the code more accurately than prose about it.")

# 11 ── toolchain
def io(name, desc, c):
    return card(t(name, 30, 700, c) + t(desc, 25, 400, BODY, "line-height:1.4"), pad="24px 32px")
slide("toolchain",
      head("How it works on our projects", "Our toolchain") +
      '<div style="display:flex; gap:28px; align-items:center">'
      f'<div style="width:480px; display:flex; flex-direction:column; gap:16px"><p style="font-size:24px; text-transform:uppercase; color:{MUTED}">Inputs</p>'
      + io("Fireflies", "Client calls, kept by the client's email addresses", BLUE)
      + io("Gmail", "Threads from the client's addresses", BLUE)
      + io("Slack", "Threads in the project's client channels", BLUE) + '</div>'
      f'<x-shape kind="arrow-right" style="width:48px; height:24px; background:{BLUE}"></x-shape>'
      f'<div style="flex:1; display:flex; flex-direction:column; gap:20px; background:{NAVY}; border-radius:24px; padding:44px">'
      f'<p style="font-size:24px; font-weight:500; letter-spacing:1px; text-transform:uppercase; color:{ORANGE}">Source of truth</p>'
      f'<p style="font-size:44px; font-weight:700; color:{WHITE}">Project repo</p>'
      f'<p style="font-size:26px; line-height:1.45; color:{ONDARK_BODY}">Specs, triage reports, clarification pages and the project settings file. Worked on in Claude Code, with every change in git.</p></div>'
      f'<x-shape kind="arrow-right" style="width:48px; height:24px; background:{PURPLE}"></x-shape>'
      f'<div style="width:480px; display:flex; flex-direction:column; gap:16px"><p style="font-size:24px; text-transform:uppercase; color:{MUTED}">Outputs</p>'
      + io("Jira", "A ticket with a short description and the spec link", PURPLE)
      + io("Clarification pages", "Listed on the dashboard; the client answers there", PURPLE)
      + io("Figma", "Concepts drawn from the design system", PURPLE) + '</div></div>'
      + bullets(["Edit the spec first, then publish. Never edit only the copy."]),
      "Everything flows through the repo. Nothing the client sees is ever edited anywhere else first.")

# 12 ── the skills
skills = [
    ("ba-spec", "A spec in the template, through the gate to Jira", True),
    ("intake-and-triage", "Sorts new calls, emails and threads into actions", True),
    ("fetch-fireflies · -gmail · -slack · -jira-backlog", "Pull in the client's calls, emails, threads and old tickets", False),
    ("clarification-page", "Builds the page the client answers questions on", False),
    ("figma-build", "Draws screens and concepts from the design system", False),
    ("ba-setup", "Checks your keys, the project and the defaults", False),
    ("jira · confluence · feature-brief", "Ticket helpers; client briefs and pages on Confluence", False),
    ("data-dictionary · messages", "The lookup tables: every field and label; every message sent", False),
    ("bmad-product-brief · bmad-prd", "BMad's brief and PRD, for new projects and phases", False),
    ("ba-dashboard", "Your starting page: every feature, its clarification page", False),
]
kc = "".join(
    f'<div style="display:flex; flex-direction:column; gap:4px; background:{TINT if main else WHITE}; border:{"2px solid " + ORANGE if main else "1px solid " + BORDER}; border-radius:16px; padding:12px 28px">'
    f'<div style="display:flex; justify-content:space-between; align-items:center"><p style="font-size:27px; font-weight:700; color:{NAVY}">{name}</p>'
    + (f'<p style="font-size:24px; font-weight:500; color:{ORANGE_TXT}">YOUR MAIN SKILL</p>' if main else "") +
    f'</div><p style="font-size:25px; color:{BODY}">{d}</p></div>' for name, d, main in skills)
slide("skills",
      head("Who does what", "Meet the skills") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px">{kc}</div>' +
      t("Ask for a skill in plain words — “write a spec for…”, “triage the new calls”. Stuck in BMad? Ask bmad-help.", 26, 500, MUTED),
      "The first two are where a BA spends most of the week. The last two are BMad's own, used on new projects and phase PRDs.")

# 13 ── getting set up
slide("setup",
      head("Hands-on", "Getting set up") +
      '<div style="display:flex; gap:56px">'
      '<div style="width:960px; display:flex; flex-direction:column; gap:24px">'
      f'<div style="display:flex; flex-direction:column; gap:18px; background:{NAVY}; border-radius:24px; padding:40px 44px">'
      f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{ORANGE}">Install (once per project)</p>'
      f'<p style="{MONO}; font-size:28px; line-height:1.5; color:{WHITE}">uv run --with pyyaml python<br>C:/dev/ba-tools/scripts/install.py &lt;project&gt;</p>'
      f'<p style="font-size:25px; line-height:1.45; color:{ONDARK_BODY}">Needs Git, Node and uv. The setup manual in ba-tools walks every step, including each tool\'s key.</p></div>'
      + card(f'<p style="font-size:24px; font-weight:500; text-transform:uppercase; color:{GREEN}">Your lifesaver</p>'
             f'<p style="{MONO}; font-size:32px; color:{NAVY}">ba-setup</p>'
             + t("Type it any time. It checks everything and tells you what is missing.", 26, 400, BODY), pad="32px 44px") + '</div>'
      '<div style="flex:1; display:flex; flex-direction:column; gap:20px">' + t("Good habits", 36, 700, NAVY) +
      bullets(["Start a fresh chat for each task", "Never paste a key into the chat", "Commit after each step; every push is asked for",
               "When ba-tools updates, pull it and re-run the install"]) + '</div></div>',
      "Setup takes about two hours of a BA's time, spread over a day or two while access requests come through.",
      section="Getting productive")

# 14 ── first two weeks
def week(c, title, sub, days):
    rows = "".join(f'<div style="display:flex; gap:24px"><p style="width:150px; font-size:26px; font-weight:700; color:{c}">{d}</p><p style="flex:1; font-size:26px; line-height:1.4; color:{BODY}">{x}</p></div>' for d, x in days)
    return (f'<div style="flex:1; display:flex; flex-direction:column; background:{WHITE}; border:1px solid {BORDER}; border-radius:20px; overflow:hidden">'
            f'<div style="display:flex; justify-content:space-between; align-items:center; background:{c}; padding:26px 36px"><p style="font-size:36px; font-weight:700; color:{WHITE}">{title}</p><p style="font-size:26px; color:{WHITE}">{sub}</p></div>'
            f'<div style="display:flex; flex-direction:column; gap:22px; padding:36px">{rows}</div></div>')
slide("weeks",
      head("Suggested plan", "Your first two weeks") +
      '<div style="display:flex; gap:40px; flex:1">'
      + week(BLUE, "Week 1", "Learn and set up", [("Day 1", "Read this guide and the setup manual; bookmark the project dashboard"), ("Day 2", "Run ba-setup until every row is green"),
                                                  ("Day 3", "Shadow a client call and its triage"), ("Day 4–5", "Write a small spec with ba-spec, paired")])
      + week(GREEN, "Week 2", "Real work, paired", [("Day 6–7", "Pull in and triage a call yourself"), ("Day 8", "Build a clarification page for real questions"),
                                                    ("Day 9", "Take a spec through the ready gate to a ticket"), ("Day 10", "Retro: where the tools helped, where you steered")])
      + '</div>',
      "Pair on everything client-facing in week 2. The retro is the most useful day: bring what surprised you.")

# 15 ── why we changed
ev = [
    (CORAL, "0 of 90", "earlier specs, on two projects, had an edge-case section"),
    (CORAL, "3% · 6%", "of them said what a user without permission sees"),
    (PURPLE, "29 → 5", "candidate features, then specs, from the same two calls once triaged"),
    (PURPLE, "5", "specs already filed with open questions, before the ready gate"),
    (BLUE, "6 of 50", "recent calls kept by the client filter in a live test"),
    (GREEN, "206 → 242", "requirements in one product's PRD after catching up on what shipped"),
]
evc = "".join(card(f'<p style="font-size:72px; font-weight:700; line-height:1.1; color:{c}">{num}</p>' + t(d, 26, 400, BODY, "line-height:1.4"), pad="32px 36px") for c, num, d in ev)
slide("evidence",
      head("From our own projects", "Why we work this way") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:20px">{evc}</div>' +
      t("Every number comes from our own client projects (names left out) — none is borrowed.", 26, 500, MUTED),
      "The first two numbers are why the edge-case list exists. The next two are why triage and the gate exist.")

# 16 ── pitfalls
pf = [
    ("Rubber-stamping the draft", "Fluent text is not correct text. Read every rule and check its source."),
    ("Editing the template in a project", "It is a copy from ba-tools. Put project facts in the settings file."),
    ("Pasting the spec into Jira", "The ticket goes stale the day the spec changes. Link it instead."),
    ("Skipping the code check", "It is where a spec turns out smaller than it looked — or wrong."),
    ("Asking what you could decide", "Decide it, log it as yours, and keep the client's list short."),
    ("A key in the chat", "Chats are stored. Keys go in your settings file, nowhere else."),
]
pc = "".join(
    f'<div style="display:flex; flex-direction:column; gap:10px; background:{WHITE}; border:1px solid {BORDER}; border-left:10px solid {CORAL}; border-radius:16px; padding:26px 32px">'
    f'{t(a, 30, 700, NAVY)}{t(b, 25, 400, BODY, "line-height:1.4")}</div>' for a, b in pf)
slide("pitfalls",
      head("Learn from others", "Tips and common pitfalls") +
      f'<div style="display:grid; grid-template-columns:1fr 1fr; gap:20px">{pc}</div>',
      "Each of these has happened at least once on our projects.")

# 17 ── resources
res = [
    ("The toolset", "Skills, the template, the setup manual and the flows", "github.com/Relevant-S/ba-tools"),
    ("The setup manual", "Every connection, step by step", "docs/new-ba-onboarding.md"),
    ("The project dashboard", "Every feature, its clarification page, what waits on whom", "tools.dashboard.url"),
    ("Your onboarding buddy", "Questions, pairing, reviews of your first specs", "the lead BA"),
]
rc = "".join(card(
    f'<div style="display:flex; justify-content:space-between; align-items:center; gap:32px"><div style="display:flex; flex-direction:column; gap:4px">{t(a, 30, 700, NAVY)}{t(b, 25, 400, MUTED)}</div>'
    f'<p style="{MONO}; font-size:26px; color:{BLUE}; text-align:right">{link}</p></div>', pad="22px 36px") for a, b, link in res)
slide("resources",
      head("Keep these handy", "Resources") +
      f'<div style="display:flex; flex-direction:column; gap:14px">{rc}</div>' +
      f'<p style="font-size:48px; font-weight:700; color:{ORANGE_TXT}; text-align:right">Welcome aboard!</p>',
      "End here and open the setup manual together.")

assert n[0] == TOTAL, n[0]
deck = {
    "v": 4,
    "createdOnFiles": {"v": 1, "at": "2026-09-24T16:14:06Z"},
    "title": "Our BA approach — a guide for BAs",
    "order": order,
    "sections": sections,
    "faces": {
        "poppins": {"family": "Poppins", "href": "https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap"},
        "jetbrains-mono": {"family": "JetBrains Mono", "href": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap"},
    },
    "designSystems": [],
}
json.dump(deck, open(os.path.join(ROOT, "project", "deck.json"), "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
print(len(order), "slides:", ", ".join(order))
