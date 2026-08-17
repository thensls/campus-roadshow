#!/usr/bin/env python3
"""
Sync the Campus Roadshow site into the Campus Discovery CRM (Airtable).

The site is the source of truth; Airtable is the query layer. This script is
idempotent — it upserts, so it is safe to re-run after every school addition.

    python3 Scripts/sync_airtable.py              # dry run (default)
    python3 Scripts/sync_airtable.py --execute    # actually write

Supersedes the one-shot backfill_*.py scripts, which create unconditionally and
would duplicate Quotes and Executive Findings on a second run.

Tables synced: Target Schools, Meetings, Quotes, Executive Findings, Contacts
(including Primary Contact links, which is what makes the Champion Potential
lookup populate on Target Schools), and Product Insights attribution.

Product Insights mirrors the ideas grid (decision 2026-08-12) — unmatched cards
are created. Five legacy records from an older coarse taxonomy carry no
attribution and are reported, never modified. Concerns & Objections is
deliberately not synced: its useful fields are human triage decisions the
reports do not contain. See MAINTENANCE.md.
"""
import os, re, sys, json, time, html as htmllib, unicodedata
from pathlib import Path
from datetime import datetime

import requests

BASE = "app5rj9bOGQNFoIoD"
TBL = {"schools": "tbleaeYm3UEINl1oU", "meetings": "tblLMsmz7pQOpeQr8",
       "quotes": "tblBwzqpUmDZeDjyc", "findings": "tblkIEzMirsfzvHQn",
       "contacts": "tbljDWMCZLjSgrkKw", "insights": "tblW3dZOVKNjN1692"}
SITE = "https://roadshow.nsls.org"

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "report" / "index.html"

EXECUTE = "--execute" in sys.argv
KEY = os.environ.get("AIRTABLE_API_KEY")
if not KEY:
    sys.exit("AIRTABLE_API_KEY not set — run: source ~/.zshrc")
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

stats = {"create": 0, "update": 0, "skip": 0, "error": 0}


# ── helpers ───────────────────────────────────────────────────────────────
def text(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).replace("&", "and")
    s = re.sub(r"\b(university|college|the|of|at|community|state|technical|and)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# Known site-name <-> Airtable-name mismatches. Without these the fuzzy match
# misses and the sync creates a duplicate record.
#   UTRGV: Airtable holds a typo ("Rio Grand Valley"), the site is correct.
NAME_ALIASES = {
    "University of Texas, Rio Grande Valley": "University of Texas, Rio Grand Valley",
    "University at Albany": "UAlbany",
}

# Ideas-grid card -> existing Product Insights record under a different name.
# Confirmed same concept: both carry First Discussed = Cassandra Gonzalez ·
# Drew University and the identical downstream chain.
INSIGHT_ALIASES = {
    "Career Readiness Score": "Career Readiness Score & Outcomes Dashboard",
}

# Substring matching is deliberately NOT used. It produced two data-corrupting
# matches in testing — "Texas A&M University" -> "Texas A&M Corpus Christi", and
# "Coastal Carolina University — Graduate" -> "Coastal Carolina University".
# Those are distinct schools tracked separately. Add an explicit alias instead.


def find_school(name, by_name):
    """exact -> alias -> conservative fuzzy. Returns (record, how)."""
    n = norm(name)
    if n in by_name:
        return by_name[n], "exact"
    alias = NAME_ALIASES.get(name)
    if alias and norm(alias) in by_name:
        return by_name[norm(alias)], "alias"
    import difflib
    close = difflib.get_close_matches(n, [k for k in by_name if k], n=1, cutoff=0.94)
    if close:
        return by_name[close[0]], "fuzzy"
    return None, "none"


def fetch_all(tid):
    out, off = [], None
    while True:
        p = {"pageSize": 100}
        if off:
            p["offset"] = off
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{tid}", headers=H, params=p)
        r.raise_for_status()
        j = r.json()
        out += j["records"]
        off = j.get("offset")
        if not off:
            return out


def write(tid, fields, rec_id=None, label=""):
    """PATCH when rec_id given, else POST. Honours --execute."""
    fields = sanitize(fields, label)
    verb = "update" if rec_id else "create"
    if not EXECUTE:
        stats[verb] += 1
        print(f"    [{verb.upper():6s}] {label}")
        return None
    url = f"https://api.airtable.com/v0/{BASE}/{tid}" + (f"/{rec_id}" if rec_id else "")
    fn = requests.patch if rec_id else requests.post
    r = fn(url, headers=H, json={"fields": fields})
    if r.status_code != 200:
        stats["error"] += 1
        print(f"    [ERROR ] {label}: {r.status_code} {r.text[:160]}")
        return None
    stats[verb] += 1
    print(f"    [{verb.upper():6s}] {label}")
    time.sleep(0.22)
    return r.json()


def changed(rec, fields):
    """True if any field differs from what Airtable already holds.
    Compares post-sanitise, or a mapped value (Online -> Virtual) would look
    different forever and every run would re-write every record."""
    fields = {k: v for k, v in fields.items()
              if not (k in ALLOWED and v and
                      SELECT_FIXUPS.get(k, {}).get(v, v) not in ALLOWED[k])}
    fields = {k: (SELECT_FIXUPS.get(k, {}).get(v, v) if k in ALLOWED else v)
              for k, v in fields.items()}
    cur = rec.get("fields", {})
    for k, v in fields.items():
        if isinstance(v, list):
            if sorted(cur.get(k, []) or []) != sorted(v):
                return True
        elif str(cur.get(k, "") or "").strip() != str(v or "").strip():
            return True
    return False


# ── site parsing ──────────────────────────────────────────────────────────
RAW = INDEX.read_text()

INST_MAP = [
    ("r1", "R1"), ("research university", "R1"),
    ("private online", "Online University"), ("online", "Online University"),
    ("public 2-year", "Community College"), ("2-year", "Community College"),
    ("technical", "Technical College"),
    ("private 4-year", "Private 4-Year"), ("public 4-year", "Public 4-Year"),
]


def inst_type(raw):
    r = (raw or "").lower()
    for frag, val in INST_MAP:
        if frag in r:
            return val
    return None


ICON = {"✅": "Yes", "🤔": "Maybe", "❌": "No", "❓": None}

# Airtable singleSelect options. A value outside these sets makes Airtable reject
# the WHOLE record with INVALID_MULTIPLE_CHOICE_OPTIONS, losing every other field
# on it — so sanitise before sending rather than letting one bad value fail 13
# good ones. The site says Chapter Type "Online"; Airtable calls that "Virtual".
def norm_person(n):
    """Normalise a person's name for matching. Deliberately conservative —
    people dedupe far worse than institutions and there is already one
    duplicate pair in Contacts."""
    n = unicodedata.normalize("NFKD", (n or "").lower())
    n = re.sub(r"\b(dr|prof|mr|mrs|ms|phd|edd)\b", " ", n)
    return re.sub(r"[^a-z]", "", n)


ALLOWED = {
    "Chapter Type": {"In-Person", "Virtual", "Hybrid", "TBD"},
    "Chapter Status": {"Established", "New", "Inactive", "TBD"},
    "Pilot Partner": {"Yes", "Maybe", "No"},
    "Product Council Interest": {"Yes", "No", "Maybe"},
    "Outreach Status": {"Not Contacted", "Reached Out", "Scheduled", "Completed", "Declined"},
    "Institution Type": {"R1", "Four-Year Public", "Two-Year", "Online", "Other",
                         "Private 4-Year", "Community College", "Public 4-Year",
                         "Online University", "Technical College"},
    "Meeting Type": {"Discovery", "Follow-up", "Product Demo", "Check-in",
                     "Society Connect", "Other"},
    "Champion Potential": {"Strong", "Moderate", "Low"},
    "Excitement Level": {"High", "Medium", "Low"},
}
SELECT_FIXUPS = {"Chapter Type": {"Online": "Virtual", "Virtual": "Virtual"}}


def sanitize(fields, label=""):
    """Map known aliases onto valid options; drop anything still invalid."""
    out = {}
    for k, v in fields.items():
        if k in ALLOWED and v:
            v = SELECT_FIXUPS.get(k, {}).get(v, v)
            if v not in ALLOWED[k]:
                print(f"    [WARN  ] {label}: dropping {k}={v!r} (not a valid option)")
                continue
        out[k] = v
    return out


def parse_schools():
    out = []
    for m in re.finditer(
            r'<a class="school-card" href="schools/([^/]+)/index\.html"([^>]*)>(.*?)</a>',
            RAW, re.S):
        slug, attrs, body = m.group(1), m.group(2), m.group(3)

        def attr(n):
            a = re.search(rf'data-{n}="([^"]*)"', attrs)
            return a.group(1) if a else ""

        name = text(re.search(r"<h3>(.*?)</h3>", body, re.S).group(1))
        date_m = re.search(r'class="meeting-date">([^<]+)<', body)
        sub = re.search(r'class="school-sub">(.*?)</div>', body, re.S)
        location = text(sub.group(1)).split("·")[0].strip() if sub else ""

        stats_ = dict()
        for s in re.finditer(r'<div class="school-stat">(.*?)</div>\s*</div>', body, re.S):
            # [^<]* not (.*?)< — the captured block ends at the label text with no
            # trailing "<", so requiring one makes every stat silently drop.
            v = re.search(r'stat-val">([^<]*)', s.group(1), re.S)
            l = re.search(r'stat-lbl">([^<]*)', s.group(1), re.S)
            if v and l:
                stats_[text(l.group(1))] = text(v.group(1))

        prio = re.search(r"<strong>Top priority:</strong>(.*?)</div>", body, re.S)
        sig = re.search(r"<strong>Key signal:</strong>(.*?)</div>", body, re.S)
        exc = stats_.get("Excitement", "")
        num = re.match(r"([\d.]+)", exc.replace("/10", "").split("-")[0])

        out.append({
            "slug": slug, "name": name, "location": location,
            "school_type": attr("school-type"),
            "chapter_status": attr("chapter-status") or "TBD",
            "chapter_type": attr("chapter-type") or "TBD",
            "date": date_m.group(1).strip() if date_m else None,
            "excitement": int(float(num.group(1))) if num else None,
            "pilot": ICON.get(stats_.get("Pilot Partner", "").strip()),
            "council": ICON.get(stats_.get("Prod. Council", "").strip()),
            "top_priority": text(prio.group(1)) if prio else "",
            "key_signal": text(sig.group(1)) if sig else "",
            "completed": "status-chip completed" in body,
        })
    return out


def parse_quotes():
    out = []
    for i, (t, a) in enumerate(re.findall(
            r'<div class="quote-card">\s*<div class="quote-text">(.*?)</div>\s*'
            r'<div class="quote-attribution">(.*?)</div>', RAW, re.S), 1):
        q = text(t).strip("“”\"'")
        attr = text(a)
        parts = [p.strip() for p in re.split(r"·|&middot;", attr) if p.strip()]
        out.append({"text": q, "advisor": parts[0] if parts else attr,
                    "school": parts[-1] if len(parts) > 1 else "", "sort": i})
    return out


def parse_ideas():
    """Ideas grid -> Product Insights. Only the factual fields: name and
    attribution. Excitement Level, Feature Category and Implementation
    Complexity are human judgements with no source on the site — writing them
    would be fabrication, so they are left alone."""
    out = []
    for c in re.split(r'<div class="idea-card"', RAW)[1:]:
        nm = re.search(r'idea-name">([^<]*)', c)
        if not nm:
            continue
        people = [text(p) for p in re.findall(r'idea-attr-person">([^<]*)', c)]
        people = [re.sub(r"\s*·\s*", " · ", p) for p in people]
        out.append({"name": text(nm.group(1)),
                    "first": people[0] if people else "",
                    "also": "; ".join(people[1:])})
    return out


# Section 6 "Feature-Level Feedback" tables name features in free text — 381
# distinct labels across 44 reports, only 3 of which exactly match an ideas-grid
# card. Matching is therefore by keyword family, one pattern per card. A label
# may match more than one card ("Career Readiness Score (Advisor Dashboard)"
# genuinely speaks to both) and that is intended.
FEATURE_PATTERNS = {
    "Career Readiness Score": r"readiness score",
    "Administrator Dashboard": r"(advisor|admin|administrator|institutional|staff)[^|]{0,26}dashboard",
    "School Agent": r"(school|campus)[- ]?\w*\s*(ai )?(agent|intelligence)|school-trained ai|campus agent",
    "Multi-Semester Analytics": r"multi-?semester|multi-?year|cross-?year|cross-?semester|longitudinal|multi-?cohort|year-over-year|academic year",
    "FOL Micro-Learning & Modular Content": r"(fol|foundations of leadership)|modular.{0,24}(video|content)|micro-?learning|short-?form|video content",
    "Handshake Integration": r"handshake",
    "Personality Assessment Enrichment": r"personality|strengthsfinder|cliftonstrengths|personal insights",
    "Platform-Driven Engagement Nudges": r"nudge|reminder|notification|accountability engine|task reminder",
    "Student Email Preferences": r"email[^|]{0,26}(field|preference|primary|login|authentication|formatting)|multi-?email|magic link",
    "Gamification & Friendly Engagement Nudges": r"gamification|streak|confetti|badge",
    "Alumni & Lifelong Membership Product": r"(alumni|lifelong)[^|]{0,30}(membership|product|subscription|access)|post-?graduation access",
    "Non-Member On-Ramp": r"non-?member|non-nsls|campus-?wide (access|deployment)|membership funnel",
    "Member Drop-off Analytics": r"drop-?off",
    "School-Specific Onboarding Questions": r"onboarding question",
    "Peer Chapter Benchmarking": r"benchmark",
    "Quick-Pulse Student Feedback": r"quick-?pulse|pulse.{0,10}survey|mobile survey",
    "Student ID Field in the Platform": r"student id",
    "Affinity-Based SNT Groupings": r"affinity",
    "In-Platform Messaging & Event Communication Hub": r"(in-?app|in-?platform|bulk|centralized|segmented)[^|]{0,22}(messag|chat|communication|email)|event (management|calendar)|in-app event",
    "AI Study & Career Prep Toolkit": r"resume|interview prep|study",
    "Skill-Level Outcome Data & NACE Competency Reporting": r"nace|competenc|skill-?level outcome|outcomes report",
    "Entry-Level Pathways & Reverse-Engineered Career Steps": r"entry-?level|reverse-?engineer",
    "Shareable Progress Summary for Career Services Handoff": r"career services[^|]{0,30}(integration|shared|dashboard|involvement|team)|progress summary|cross-depart",
    "Student-Initiated & On-Demand Group Formation": r"on-?demand[^|]{0,20}group|student-?initiated|cross-(institutional|campus|school|chapter)",
    "Campus Engagement Platform Integration": r"alamo experience|engagure|engkura|eagle hub|campus groups|co-?curricular platform|engagement platform",
    "In-Platform Events & Speaker Broadcasts": r"broadcast|speaker|national event|campus event|in-app event|event (management|calendar)|regional leadership summit",
    "SIS & Academic-System Integration": r"\bsis\b|banner|hero ico|ready education|hullabaloo|attendance credit|lms",
}
SIGNALS = {"Strong", "Positive", "Open Question", "Needs Care"}


def feature_signals():
    """(card -> [(school, signal)]) from every report's Section 6 table."""
    hits = {}
    for f in sorted((ROOT / "report" / "schools").glob("*/meetings/*.html")):
        h = f.read_text()
        i = h.find('id="s6"')
        if i < 0:
            continue
        school = f.parts[-3]
        for row in re.findall(r"<tr>(.*?)</tr>", h[i:i + 6000], re.S):
            cells = [text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            if len(cells) < 2 or cells[1] not in SIGNALS:
                continue
            for card, pat in FEATURE_PATTERNS.items():
                if re.search(pat, cells[0], re.I):
                    hits.setdefault(card, []).append((school, cells[1]))
    return hits


def grade_excitement(pairs):
    """Breadth-aware: how much a feature matters across the roadshow, not how
    warmly one school reacted. A lone Strong mention is Low, not High."""
    if not pairs:
        return None
    sigs = [s for _, s in pairs]
    schools = len({s for s, _ in pairs})
    n = len(sigs)
    strong = sum(1 for s in sigs if s == "Strong")
    warm = strong + sum(1 for s in sigs if s == "Positive")
    if schools >= 5 and strong / n >= 0.45:
        return "High"
    if schools >= 2 and warm / n >= 0.5:
        return "Medium"
    return "Low"


def parse_concerns(school):
    """'What Raised Questions or Friction' bullets from a school's meeting
    reports. Yields the factual fields only — Severity Level, Concern Category,
    Resolution Status and Follow-Up Actions are human triage decisions that the
    report does not contain."""
    out = []
    d = ROOT / "report" / "schools" / school["slug"] / "meetings"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("meeting-*.html")):
        h = f.read_text()
        m = re.search(r"What Raised Questions or Friction(.*?)(?:<h[23]|Surprises)", h, re.S)
        if not m:
            continue
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S):
            t = text(li)
            if len(t) > 40:
                out.append({"desc": t, "school": school["name"],
                            "date": dm.group(1) if dm else None})
    return out


def parse_findings():
    out = []
    # NB: matches modifier classes too — the WGU finding is "exec-finding risk".
    # Matching only the bare class silently drops it and reports it as an orphan.
    for i, blk in enumerate(re.split(r'<div class="exec-finding(?: [^"]*)?">', RAW)[1:], 1):
        hl = re.search(r'exec-finding-headline">(.*?)</div>', blk, re.S)
        if not hl:
            continue
        body = re.search(r'exec-finding-text">(.*?)</div>', blk, re.S)
        icon = re.search(r'exec-finding-icon">(.*?)</div>', blk, re.S)
        chips = re.findall(r'exec-school-chip">(.*?)</span>', blk, re.S)
        out.append({"headline": text(hl.group(1)), "body": text(body.group(1)) if body else "",
                    "icon": text(icon.group(1)) if icon else "",
                    "chips": ", ".join(text(c) for c in chips), "sort": i})
    return out


def parse_advisors(school):
    """Advisors from a school's hub page, plus the school-level champion
    potential and the survey respondent (who becomes Primary Contact)."""
    hub = ROOT / "report" / "schools" / school["slug"] / "index.html"
    if not hub.exists():
        return [], None, None
    h = hub.read_text()

    advisors = []
    for m in re.finditer(
            r'<div class="attendee"[^>]*>.*?<div class="name">(.*?)</div>\s*'
            r'<div class="role">(.*?)</div>', h, re.S):
        nm, role = text(m.group(1)), text(m.group(2))
        if nm and nm not in [a["name"] for a in advisors]:
            advisors.append({"name": nm, "role": role})

    champ = None
    cm = re.search(r'Champion Potential.*?>(Strong|Moderate|Low)<', h, re.S)
    if cm:
        champ = cm.group(1)

    # Survey respondent -> Primary Contact ("derived from survey respondent
    # data", per the Airtable field description).
    respondent = None
    sv = ROOT / "report" / "schools" / school["slug"] / "survey.html"
    if sv.exists():
        rm = re.search(r'<h2[^>]*>([^<]+?)\s*&mdash;', sv.read_text())
        if rm:
            respondent = text(rm.group(1))
    return advisors, champ, respondent


def parse_meetings(school):
    d = ROOT / "report" / "schools" / school["slug"] / "meetings"
    out = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("meeting-*.html")):
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
        h = f.read_text()
        fath = re.search(r'https://fathom\.video/calls/\d+', h)
        out.append({
            "name": f"Discovery — {school['name']}",
            "date": dm.group(1) if dm else None,
            "fathom": fath.group(0) if fath else "",
            "url": f"{SITE}/schools/{school['slug']}/{f.parent.name}/{f.name}",
            "content": (re.search(r"<main.*?</main>", h, re.S).group(0)
                        if re.search(r"<main.*?</main>", h, re.S) else ""),
            "file": f.name,
        })
    return out


# ── sync ──────────────────────────────────────────────────────────────────
def main():
    mode = "EXECUTE" if EXECUTE else "DRY RUN"
    print(f"\n{'='*74}\n  Campus Roadshow → Airtable sync   [{mode}]\n{'='*74}")

    schools = parse_schools()
    print(f"\nSite: {len(schools)} schools, {len(parse_quotes())} quotes, "
          f"{len(parse_findings())} findings")

    # ---- Target Schools ----
    print(f"\n─── Target Schools ───")
    existing = fetch_all(TBL["schools"])
    by_name = {norm(r["fields"].get("School Name", "")): r for r in existing}
    school_rec = {}

    name_notes, claimed = [], {}
    for s in schools:
        rec, how = find_school(s["name"], by_name)
        if rec and how != "exact":
            at_name = rec["fields"].get("School Name", "")
            name_notes.append(f"{how:9s} site={s['name']!r}  airtable={at_name!r}")
        if rec:
            # Two site schools resolving to one Airtable record means one would
            # overwrite the other. Refuse rather than corrupt.
            if rec["id"] in claimed:
                sys.exit(f"\nABORT: '{s['name']}' and '{claimed[rec['id']]}' both match "
                         f"Airtable record {rec['id']} "
                         f"({rec['fields'].get('School Name','')!r}).\n"
                         f"Add an explicit entry to NAME_ALIASES, or create the missing "
                         f"Airtable record, then re-run.")
            claimed[rec["id"]] = s["name"]

        f = {"Location": s["location"],
             "Chapter Status": s["chapter_status"], "Chapter Type": s["chapter_type"],
             "Key Signal": s["key_signal"][:900], "Top Priority": s["top_priority"][:250],
             "Roadshow Report URL": f"{SITE}/schools/{s['slug']}/index.html"}
        if inst_type(s["school_type"]):
            f["Institution Type"] = inst_type(s["school_type"])
        if s["excitement"]:
            f["Enthusiasm Level"] = s["excitement"]
        if s["pilot"]:
            f["Pilot Partner"] = s["pilot"]
        if s["council"]:
            f["Product Council Interest"] = s["council"]
        if s["completed"]:
            f["Outreach Status"] = "Completed"
        if s["date"]:
            try:
                f["Interview Date"] = datetime.strptime(s["date"], "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

        if rec:
            # Deliberately does NOT write School Name on update. The site is not
            # always the better source — it has "Austin Peay University" where
            # Airtable correctly has "Austin Peay State University".
            if changed(rec, f):
                write(TBL["schools"], f, rec["id"], s["name"])
            else:
                stats["skip"] += 1
            school_rec[s["slug"]] = rec["id"]
        else:
            r = write(TBL["schools"], {**f, "School Name": s["name"]}, None,
                      f"{s['name']}  (new)")
            school_rec[s["slug"]] = r["id"] if r else None

    if name_notes:
        print("\n  Name matches that were not exact — verify these are the same school:")
        for n in name_notes:
            print("    ·", n)

    # ---- Meetings ----
    print(f"\n─── Meetings ───")
    ex_m = fetch_all(TBL["meetings"])
    # Keyed by Roadshow Report URL first — it is unique per meeting FILE.
    # (school, date) is NOT unique: four schools have meeting-1 and meeting-2 on
    # the same day, and keying on the pair makes both files claim one record and
    # overwrite each other on every run.
    by_url, by_sd = {}, {}
    for r in ex_m:
        fl = r["fields"]
        if fl.get("Roadshow Report URL"):
            by_url[fl["Roadshow Report URL"].rstrip("/")] = r
        by_sd.setdefault(
            (norm(str(fl.get("School", "")) or str(fl.get("Meeting Name", "")).split("—")[-1]),
             str(fl.get("Meeting Date", ""))[:10]), []).append(r)
    # Two passes: reserve every exact URL match across the whole run BEFORE any
    # (school, date) fallback, or meeting-1's fallback can steal the record that
    # holds meeting-2's URL.
    claimed_m = set()
    for s in schools:
        for mt in parse_meetings(s):
            r = by_url.get(mt["url"].rstrip("/"))
            if r:
                claimed_m.add(r["id"])

    for s in schools:
        for mt in parse_meetings(s):
            rec = by_url.get(mt["url"].rstrip("/"))
            if not rec:
                # fall back to (school, date), skipping records already claimed
                # by an earlier file so meeting-2 cannot steal meeting-1's record
                for cand in by_sd.get((norm(s["name"]), mt["date"] or ""), []):
                    if cand["id"] not in claimed_m:
                        rec = cand
                        break
            if rec:
                claimed_m.add(rec["id"])
            # "School" is singleLineText, NOT a record link — sending a record
            # id array fails with INVALID_VALUE_FOR_COLUMN.
            f = {"School": s["name"], "Roadshow Report URL": mt["url"],
                 "Report Content": mt["content"][:95000]}
            if mt["date"]:
                f["Meeting Date"] = mt["date"]
            if mt["fathom"]:
                f["Fathom Recording"] = mt["fathom"]
            label = f"{s['name']} · {mt['date']}"
            if rec:
                # Meeting Name and Type are NOT overwritten on update — existing
                # records carry human-set values ("Society Presentation — UTK",
                # type "Society Connect") that this script cannot infer.
                if changed(rec, f):
                    write(TBL["meetings"], f, rec["id"], label)
                else:
                    stats["skip"] += 1
            else:
                write(TBL["meetings"],
                      {**f, "Meeting Name": mt["name"], "Meeting Type": "Discovery"},
                      None, f"{label}  (new)")

    # ---- Quotes ----
    print(f"\n─── Quotes ───")
    ex_q = fetch_all(TBL["quotes"])
    q_key = {norm(r["fields"].get("Quote Text", ""))[:70]: r for r in ex_q}
    for q in parse_quotes():
        k = norm(q["text"])[:70]
        rec = q_key.get(k)
        f = {"Quote Text": q["text"], "Advisor Name": q["advisor"],
             "School Name": q["school"], "Show on Index": True, "Sort Order": q["sort"],
             "Quote Label": f"{q['advisor']} — {q['text'][:40]}…"}
        label = f"{q['advisor'][:26]:28s} {q['text'][:44]}…"
        if rec:
            if changed(rec, f):
                write(TBL["quotes"], f, rec["id"], label)
            else:
                stats["skip"] += 1
        else:
            write(TBL["quotes"], f, None, label + "  (new)")

    # ---- Executive Findings ----
    print(f"\n─── Executive Findings ───")
    ex_f = fetch_all(TBL["findings"])
    f_by_sort = {r["fields"].get("Sort Order"): r for r in ex_f}
    site_findings = parse_findings()
    for fd in site_findings:
        rec = f_by_sort.get(fd["sort"])
        f = {"Headline": fd["headline"], "Body Text": fd["body"], "Icon": fd["icon"],
             "School Chips": fd["chips"], "Sort Order": fd["sort"]}
        label = f"#{fd['sort']} {fd['headline'][:56]}"
        if rec:
            if changed(rec, f):
                write(TBL["findings"], f, rec["id"], label)
            else:
                stats["skip"] += 1
        else:
            write(TBL["findings"], f, None, label + "  (new)")

    orphans = [r for sort, r in f_by_sort.items()
               if sort and sort > len(site_findings)]
    for o in orphans:
        print(f"    [ORPHAN] #{o['fields'].get('Sort Order')} "
              f"{str(o['fields'].get('Headline',''))[:60]} — no longer on the site, "
              f"left in place for review")

    # ---- Product Insights (mirror of the ideas grid) ----
    # Decision 2026-08-12: Product Insights mirrors the ideas grid, so unmatched
    # cards are created rather than reported. Aliases cover concepts Airtable
    # named differently before that decision.
    print(f"\n─── Product Insights ───")
    ex_p = fetch_all(TBL["insights"])
    by_feat = {norm(r["fields"].get("Feature Name", "")): r for r in ex_p}
    sig = feature_signals()
    site_keys = set()
    for idea in parse_ideas():
        alias = INSIGHT_ALIASES.get(idea["name"])
        rec = by_feat.get(norm(idea["name"])) or (by_feat.get(norm(alias)) if alias else None)
        f = {"First Discussed": idea["first"], "Also Discussed": idea["also"]}
        # Derived from 439 Section 6 signals across 44 reports. Existing values
        # date from when the base held ~19 schools, so the derived value wins.
        pairs = sig.get(idea["name"], [])
        grade = grade_excitement(pairs)
        if grade:
            f["Excitement Level"] = grade
        # Times Mentioned feeds Priority Score = (Excitement x Times Mentioned x
        # Adoption Driver) / Complexity. Derive it so it cannot go stale — a
        # hand-maintained number feeding an automatic score is the drift pattern
        # MAINTENANCE.md warns about. Only written when signals exist: writing 0
        # for a card with no Section 6 label would zero its Priority Score.
        if pairs:
            f["Times Mentioned"] = len(pairs)
        if rec:
            site_keys.add(norm(rec["fields"].get("Feature Name", "")))
            # Feature Name is not rewritten — Airtable's longer form is kept
            # deliberately (see INSIGHT_ALIASES).
            if changed(rec, f):
                write(TBL["insights"], f, rec["id"], idea["name"][:52])
            else:
                stats["skip"] += 1
        else:
            # Feature Category / Implementation Complexity have no site source —
            # left blank for triage. Excitement Level is derived (see above).
            site_keys.add(norm(idea["name"]))
            write(TBL["insights"], {**f, "Feature Name": idea["name"]}, None,
                  idea["name"][:52] + "  (new)")

    legacy = [r["fields"].get("Feature Name") for r in ex_p
              if norm(r["fields"].get("Feature Name", "")) not in site_keys]
    if legacy:
        print("    Airtable records with no ideas-grid card — legacy coarse taxonomy, "
              "no attribution. Retire or move to a separate view; not touched here:")
        for l in legacy:
            print(f"      · {l}")

    # ---- Contacts + Primary Contact + Champion Potential ----
    print(f"\n─── Contacts ───")
    ex_c = fetch_all(TBL["contacts"])
    by_person = {}
    for r in ex_c:
        by_person.setdefault(norm_person(r["fields"].get("Full Name", "")), []).append(r)

    for s in schools:
        advisors, champ, respondent = parse_advisors(s)
        if not advisors:
            continue
        sid = school_rec.get(s["slug"])
        primary = None
        for a in advisors:
            key = norm_person(a["name"])
            cands = by_person.get(key, [])
            if len(cands) > 1:
                print(f"    [AMBIG ] {a['name']} ({s['name']}): {len(cands)} contacts "
                      f"share this name — skipped, resolve by hand")
                continue
            is_primary = (respondent and norm_person(respondent) == key) or \
                         (not respondent and a is advisors[0])
            f = {"Full Name": a["name"], "Job Title": a["role"][:200]}
            if sid:
                f["School Affiliation"] = [sid]
            # School-level judgement, so attach it to the primary contact only —
            # do not duplicate it onto an advisor it wasn't made about.
            if champ and is_primary:
                f["Champion Potential"] = champ
            label = f"{a['name'][:26]:28s} {s['name'][:26]}"
            if cands:
                rec = cands[0]
                f.pop("Full Name")           # never rename an existing person
                if changed(rec, f):
                    write(TBL["contacts"], f, rec["id"], label)
                else:
                    stats["skip"] += 1
                if is_primary:
                    primary = rec["id"]
            else:
                r = write(TBL["contacts"], f, None, label + "  (new)")
                if r:
                    by_person.setdefault(key, []).append(r)
                    if is_primary:
                        primary = r["id"]

        if primary and sid:
            cur = next((r for r in existing if r["id"] == sid), None)
            if not cur or (cur["fields"].get("Primary Contact") or [None])[0] != primary:
                write(TBL["schools"], {"Primary Contact": [primary]}, sid,
                      f"{s['name']} → Primary Contact")

    print(f"\n{'='*74}")
    print(f"  create {stats['create']}   update {stats['update']}   "
          f"unchanged {stats['skip']}   errors {stats['error']}")
    if not EXECUTE:
        print("  DRY RUN — nothing written. Re-run with --execute to apply.")
    print(f"{'='*74}\n")


if __name__ == "__main__":
    main()
