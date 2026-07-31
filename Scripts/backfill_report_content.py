#!/usr/bin/env python3
"""
Backfill Report Content field in Airtable Meetings table.

For each existing meeting HTML file, extracts the <main>...</main> section
and stores it in the Report Content field (fldfRzBbWS26V042J).
Creates new Airtable records for meeting files that don't have one yet.
"""

import os
import re
import json
import time
import requests
from pathlib import Path

BASE_ID = "app5rj9bOGQNFoIoD"
MEETINGS_TABLE_ID = "tblLMsmz7pQOpeQr8"
REPORT_CONTENT_FIELD = "fldfRzBbWS26V042J"

API_KEY = os.environ.get("AIRTABLE_API_KEY")
if not API_KEY:
    raise SystemExit("AIRTABLE_API_KEY not set")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

REPORTS_ROOT = str(Path(__file__).parent.parent / "report" / "schools")

# Mapping from (school_dir, meeting_filename) → Airtable record ID
# Only for records that already exist
EXISTING_RECORDS = {
    ("arapahoe-community-college",          "meeting-1-2026-04-10.html"): "recxxlnYchZCPoeCU",
    ("austin-peay-state-university",         "meeting-1-2026-04-03.html"): "recB8AsFojxhSoxpW",
    ("central-wyoming-community-college",   "meeting-1-2026-04-03.html"): "rec9MBbmIod0pAsUn",
    ("coastal-carolina-university",          "meeting-1-2026-04-10.html"): "recuVZinlRQRldQMl",
    ("drew-university",                       "meeting-1-2026-03-22.html"): "recbyeis7desu0S6Z",
    ("florida-agricultural-and-mechanical-university", "meeting-1-2026-04-10.html"): "rectxSEYbTrD1cRPS",
    ("gonzaga-university",                    "meeting-1-2026-04-10.html"): "recWVnJxQYL6uUDNU",
    ("madison-area-technical-college",        "meeting-1-2026-04-03.html"): "recGCZ8CEyU2ZgVkB",
    ("mott-community-college",               "meeting-1-2026-03-23.html"): "recr1wPUpV2v2tTFj",
    ("muskingum-university",                 "meeting-1-2026-04-16.html"): "rec5jVuj2b5q0zTFq",
    ("south-piedmont-community-college",     "meeting-1-2026-04-03.html"): "reckobF2NfWAzcQsH",
    ("st-john-s-university",                 "meeting-1-2026-03-23.html"): "rec1QvlcyDXpiF5HR",
    ("texas-lutheran-university",            "meeting-1-2026-04-03.html"): "rec0jMMChtMEDew7w",
    ("university-of-tennessee-knoxville",    "meeting-1-2026-04-10.html"): "rec12nS1Xjbrj5m3V",
    ("utrgv",                                 "meeting-1-2026-03-23.html"): "recWLpe54W9UKGKYb",
    ("western-governors-university",          "meeting-1-2026-03-24.html"): "recC5WZ3seph8FCXx",
}

# For files that need new Airtable records: (school_dir, filename) → (Meeting Name, School text, Date)
NEW_RECORDS_NEEDED = {
    ("central-wyoming-community-college",   "meeting-2-2026-04-03.html"): ("Discovery — Central Wyoming College (2)", "Central Wyoming College", "2026-04-03"),
    ("madison-area-technical-college",       "meeting-2-2026-04-03.html"): ("Discovery — Madison Area Technical College (2)", "Madison Area Technical College", "2026-04-03"),
    ("south-piedmont-community-college",     "meeting-2-2026-04-03.html"): ("Discovery — South Piedmont Community College (2)", "South Piedmont Community College", "2026-04-03"),
    ("texas-lutheran-university",            "meeting-2-2026-04-03.html"): ("Discovery — Texas Lutheran University (2)", "Texas Lutheran University", "2026-04-03"),
    ("western-governors-university",          "meeting-1-2026-04-03.html"): ("Discovery — Western Governors University (April 3)", "Western Governors University", "2026-04-03"),
    ("texas-am-corpus-christi",              "meeting-1-2026-04-08.html"): ("Discovery — Texas A&M Corpus Christi", "Texas A&M Corpus Christi", "2026-04-08"),
    ("university-of-nevada-las-vegas",        "meeting-1-2026-04-21.html"): ("Discovery — University of Nevada, Las Vegas", "University of Nevada, Las Vegas", "2026-04-21"),
    ("university-of-north-texas",             "meeting-1-2026-04-23.html"): ("Discovery — University of North Texas", "University of North Texas", "2026-04-23"),
}


def extract_main(html_content):
    """Extract the <main>...</main> section from an HTML file."""
    match = re.search(r'(<main[\s\S]*?</main>)', html_content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def airtable_patch(record_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{MEETINGS_TABLE_ID}/{record_id}"
    resp = requests.patch(url, headers=HEADERS, json={"fields": fields})
    resp.raise_for_status()
    return resp.json()


def airtable_create(fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{MEETINGS_TABLE_ID}"
    resp = requests.post(url, headers=HEADERS, json={"fields": fields})
    resp.raise_for_status()
    return resp.json()


def process_file(school_dir, filename):
    html_path = os.path.join(REPORTS_ROOT, school_dir, "meetings", filename)
    if not os.path.exists(html_path):
        print(f"  ✗ File not found: {html_path}")
        return False

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    main_html = extract_main(content)
    if not main_html:
        print(f"  ✗ Could not find <main> in {html_path}")
        return False

    key = (school_dir, filename)

    if key in EXISTING_RECORDS:
        record_id = EXISTING_RECORDS[key]
        print(f"  Updating record {record_id} for {school_dir}/{filename}...")
        airtable_patch(record_id, {REPORT_CONTENT_FIELD: main_html})
        print(f"  ✓ Updated ({len(main_html):,} chars)")
        return True

    elif key in NEW_RECORDS_NEEDED:
        meeting_name, school_text, meeting_date = NEW_RECORDS_NEEDED[key]
        print(f"  Creating new record for {school_dir}/{filename}...")
        result = airtable_create({
            "fldJOXtLsixi5I2Qn": meeting_name,       # Meeting Name
            "fldEE2fY4uGPIpgGl": meeting_date,        # Meeting Date
            "fldi2RSAOwucIsYS2": school_text,          # School
            "fld1BMSXodL5mSp1F": "Discovery",          # Meeting Type
            REPORT_CONTENT_FIELD: main_html,
        })
        new_id = result.get("id", "???")
        print(f"  ✓ Created {new_id} ({len(main_html):,} chars)")
        return True

    else:
        print(f"  ✗ No Airtable mapping for {school_dir}/{filename}")
        return False


def main():
    all_files = []
    for d in sorted(os.listdir(REPORTS_ROOT)):
        meetings_dir = os.path.join(REPORTS_ROOT, d, "meetings")
        if not os.path.isdir(meetings_dir):
            continue
        for f in sorted(os.listdir(meetings_dir)):
            if f.startswith("meeting-") and f.endswith(".html"):
                all_files.append((d, f))

    print(f"Found {len(all_files)} meeting HTML files\n")

    success = 0
    for school_dir, filename in all_files:
        print(f"\n[{school_dir}] {filename}")
        ok = process_file(school_dir, filename)
        if ok:
            success += 1
        time.sleep(0.25)  # stay under Airtable rate limit (5 req/s)

    print(f"\n{'='*60}")
    print(f"Done: {success}/{len(all_files)} files processed successfully")


if __name__ == "__main__":
    main()
