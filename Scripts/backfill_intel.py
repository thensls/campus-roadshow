#!/usr/bin/env python3
"""
Backfill three Airtable tables from index.html:
  1. Product Insights  — First Discussed, Also Discussed
  2. Quotes            — all quote cards
  3. Executive Findings — all finding blocks
"""

import os, re, html as hl, time, requests

BASE_ID = "app5rj9bOGQNFoIoD"
API_KEY = os.environ["AIRTABLE_API_KEY"]
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
INDEX   = os.path.expanduser("~/Desktop/Campus Roadshow/report/index.html")

with open(INDEX) as f:
    RAW = f.read()

def strip(s):
    s = hl.unescape(re.sub(r'<[^>]+>', '', s))
    # collapse whitespace / fix &nbsp; middot runs
    s = re.sub(r'\xa0', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()

def patch(table_id, record_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}/{record_id}"
    r = requests.patch(url, headers=HEADERS, json={"fields": fields})
    r.raise_for_status()
    return r.json()

def create(table_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    r = requests.post(url, headers=HEADERS, json={"fields": fields})
    r.raise_for_status()
    return r.json()

# ──────────────────────────────────────────────
# 1. PRODUCT INSIGHTS
# ──────────────────────────────────────────────
PI_TABLE = "tblW3dZOVKNjN1692"
PI_FIRST_FIELD  = "fldMTVXG5tIg17hWh"
PI_ALSO_FIELD   = "fldEvvdIxXdGJmqVk"

# Airtable record IDs — keys are pre-normalized (lowercase, spaces/hyphens removed)
# normalize_key("Career Readiness Score") → "careerreadinessscore"
FEATURE_RECORDS = {
    "careerreadinessscore&outcomesdashboard": "recdU2avC4gH8OhhU",
    "folmicrolearning&modularcontent":        "reciaEzSJbrhwG34n",
    "schoolagent":                            "recWQ8Ul4h3TT6gi0",
    "administratordashboard":                 "recdDIk5Eu4ZwIqWM",
    "handshakeintegration":                   "recVP4dN9NHagJ8UA",
    "multisemesteranalytics":                 "rec9BGavE5qVKgKqS",
    "platformdrivenengagementnudges":         "rec6gKNCnjxuezgkY",
    "studentemailpreferences":                "rec6z5S9DtdKaBehQ",
    "gamification&friendlyengagementnudges":  "recoY9fbiJH3WxTm5",
    "personalityassessmentenrichment":        "recZMBYO9RevYTiPJ",
    "alumni&lifelongmembershipproduct":       "recOCqEv7wqJNYfKW",
    "nonmemberonramp":                        "recH0lOG3eBvlbbmy",
    "memberdropoffanalytics":                 "recyOTKj6bs8BUwtx",
    "schoolspecificonboardingquestions":      "rec7y5lrKrU8p6UHk",
    "peerchapterbenchmarking":                "recKCKpcy1s71ipwp",
    "quickpulsestudentfeedback":              "reclcBcO1FDONOpe8",
    "studentidfieldintheplatform":            "recerqSND5wdAXLrE",
    "affinitybasedsntgroupings":              "recknqPXkp2Kt8a36",
    "inplatformmessaging&eventcommunicationhub": "recJhhotYY96P9YU7",
    "aistudy&careerpreptoolkit":              "reckEeQhEuVk5N6ev",
    "automatedsntmanagement":                 "rec9ut1IL6TrlgPQ4",
    # alias — HTML uses shorter name
    "careerreadinessscore":                   "recdU2avC4gH8OhhU",
    # no Airtable record yet
    "skillleveloutcomedata&nacecompetencyreporting": None,
}

def normalize_key(name):
    n = hl.unescape(name.lower())
    n = re.sub(r'[–—]', '-', n)
    n = re.sub(r'[\s\-]+', '', n)       # remove all spaces/hyphens
    n = re.sub(r'[&]', '&', n)
    return n

def fix_attr(raw):
    """Turn 'Person &nbsp;·&nbsp; School' into 'Person · School'."""
    s = hl.unescape(re.sub(r'<[^>]+>', '', raw))
    s = re.sub(r'\xa0', ' ', s)
    s = re.sub(r'\s*·\s*', ' · ', s)
    s = re.sub(r' {2,}', ' ', s)
    return s.strip()

def backfill_product_insights():
    print("\n═══ 1. PRODUCT INSIGHTS ═══")
    # Split into idea-card blocks
    blocks = re.split(r'(?=<div class="idea-card">)', RAW)
    success = 0
    for block in blocks:
        if '<div class="idea-card">' not in block[:30]:
            continue
        name_m  = re.search(r'<div class="idea-name">(.*?)</div>', block)
        first_m = re.search(
            r'<span class="idea-attr-label">First discussed</span>\s*'
            r'<span class="idea-attr-person">(.*?)</span>', block, re.DOTALL)
        if not name_m:
            continue

        raw_name = strip(name_m.group(1))
        key = normalize_key(raw_name)

        record_id = FEATURE_RECORDS.get(key)
        if record_id is None:
            if key in FEATURE_RECORDS:
                print(f"  [SKIP] {raw_name} — no Airtable record")
            else:
                print(f"  [MISS] {raw_name!r} — key={key!r} not in map")
            continue

        first_str = fix_attr(first_m.group(1)) if first_m else ""

        # collect "Also discussed" people
        also_section = re.search(
            r'<span class="idea-attr-label secondary">Also discussed</span>(.*?)(?:</div>|$)',
            block, re.DOTALL)
        also_list = []
        if also_section:
            people = re.findall(r'<span class="idea-attr-person">(.*?)</span>',
                                also_section.group(1), re.DOTALL)
            also_list = [fix_attr(p) for p in people]

        fields = {}
        if first_str:
            fields[PI_FIRST_FIELD] = first_str
        if also_list:
            fields[PI_ALSO_FIELD] = "\n".join(also_list)

        print(f"  {raw_name}")
        print(f"    First: {first_str}")
        if also_list:
            print(f"    Also:  {'; '.join(also_list)}")
        patch(PI_TABLE, record_id, fields)
        print(f"    ✓ {record_id}")
        success += 1
        time.sleep(0.25)

    print(f"  Done: {success} records updated")


# ──────────────────────────────────────────────
# 2. QUOTES
# ──────────────────────────────────────────────
QUOTES_TABLE  = "tblBwzqpUmDZeDjyc"
Q_TEXT_FIELD  = "fldu9xVw4aLtZNaxi"
Q_NAME_FIELD  = "fldXkSPkLA6Y3lgaw"
Q_SCHOOL_FIELD= "fldZcxA4zksBavqDz"
Q_SHOW_FIELD  = "fldV9Km2ORv50x17S"
Q_SORT_FIELD  = "fldInrcbIh9NLlv2e"
Q_LABEL_FIELD = "fldvxWEXCCWAJFBJY"

def backfill_quotes():
    print("\n═══ 2. QUOTES ═══")
    pairs = re.findall(
        r'<div class="quote-card">\s*'
        r'<div class="quote-text">(.*?)</div>\s*'
        r'<div class="quote-attribution">(.*?)</div>',
        RAW, re.DOTALL
    )
    for i, (text, attr) in enumerate(pairs, 1):
        quote_text = strip(text).strip('""“”‘’')
        attr_clean  = strip(attr)
        # Split attribution into name · school (split on ·)
        parts = [p.strip() for p in attr_clean.split('·')]
        advisor_name = parts[0] if parts else attr_clean
        school_name  = parts[-1] if len(parts) > 1 else ""
        # Strip role suffix from advisor name (everything after comma if present)
        label = f"{advisor_name} — {quote_text[:40]}…"

        print(f"  #{i} {advisor_name} / {school_name}")
        print(f"     {quote_text[:80]!r}")
        result = create(QUOTES_TABLE, {
            Q_LABEL_FIELD:  label,
            Q_TEXT_FIELD:   quote_text,
            Q_NAME_FIELD:   advisor_name,
            Q_SCHOOL_FIELD: school_name,
            Q_SHOW_FIELD:   True,
            Q_SORT_FIELD:   i,
        })
        print(f"     ✓ Created {result['id']}")
        time.sleep(0.25)

    print(f"  Done: {len(pairs)} quotes created")


# ──────────────────────────────────────────────
# 3. EXECUTIVE FINDINGS
# ──────────────────────────────────────────────
EF_TABLE       = "tblkIEzMirsfzvHQn"
EF_HEADLINE    = "fldxCSJJkVvycneS5"
EF_BODY        = "fldG1tFP7z0ggJyqt"
EF_ICON        = "fldZQ5Jf8DIv1jSyI"
EF_CHIPS       = "fldnBp3CAulexEH0V"
EF_SORT        = "fld9buIFpmp4WL4AJ"

def backfill_exec_findings():
    print("\n═══ 3. EXECUTIVE FINDINGS ═══")
    # Find each exec-finding block
    blocks = re.findall(
        r'<div class="exec-finding[^"]*">(.*?)</div>\s*</div>\s*</div>',
        RAW, re.DOTALL
    )

    for i, block in enumerate(blocks, 1):
        icon_m     = re.search(r'<div class="exec-finding-icon">(.*?)</div>', block, re.DOTALL)
        headline_m = re.search(r'<div class="exec-finding-headline">(.*?)</div>', block, re.DOTALL)
        body_m     = re.search(r'<div class="exec-finding-text">(.*?)</div>', block, re.DOTALL)
        chips_m    = re.findall(r'<span class="exec-school-chip">(.*?)</span>', block, re.DOTALL)

        if not headline_m:
            continue

        icon     = strip(icon_m.group(1)) if icon_m else ""
        headline = strip(headline_m.group(1))
        body     = strip(body_m.group(1)) if body_m else ""
        chips_str= ", ".join(strip(c) for c in chips_m)

        print(f"  #{i} [{icon}] {headline[:70]}")
        result = create(EF_TABLE, {
            EF_HEADLINE: headline,
            EF_BODY:     body,
            EF_ICON:     icon,
            EF_CHIPS:    chips_str,
            EF_SORT:     i,
        })
        print(f"     ✓ Created {result['id']}")
        time.sleep(0.25)

    print(f"  Done: {len(blocks)} findings created")


if __name__ == "__main__":
    backfill_product_insights()
    backfill_quotes()
    backfill_exec_findings()
    print("\n✅ All backfills complete.")
