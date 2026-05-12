#!/usr/bin/env python3
"""
Backfill 6 new Target Schools fields from HTML source files.

Fields to populate:
  fldLgOnqcl0f0reSa  Location
  fldbmpQT2BuixH5jE  Chapter Status  (singleSelect)
  fldtMyRIwF18MIu2H  Chapter Type    (singleSelect)
  fldfSCHsKe3A2L5GH  Pilot Partner   (singleSelect: Yes/Maybe/No)
  flde3iaMHLarZEmKn  Key Signal
  fld8CxDjblCkhjBkV  Top Priority

Source:
  - Location, Chapter Status, Chapter Type, Top Priority, Key Signal → index.html school cards
  - Pilot Partner → each school's hub page (index.html)
"""

import os, re, html, time, requests

BASE_ID   = "app5rj9bOGQNFoIoD"
TABLE_ID  = "tbleaeYm3UEINl1oU"
API_KEY   = os.environ["AIRTABLE_API_KEY"]
HEADERS   = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
ROOT      = os.path.expanduser("~/Desktop/Campus Roadshow/report")

# Map school card href slug → Airtable Target Schools record ID
SLUG_TO_RECORD = {
    "university-of-north-texas":                    "recx0lJHx32QIM1G0",
    "university-of-nevada-las-vegas":               "recrUWHzIIrhYjt68",
    "dartmouth-college":                             "rec3NYvAPa9OINLxl",
    "muskingum-university":                          "recr63DLoYVZzxA7P",
    "coastal-carolina-university":                   "rectUbkpwbMAKdTZf",
    "university-of-tennessee-knoxville":             "recgRPTHazNsUw1A7",
    "arapahoe-community-college":                    "recskxIekBJtnu8FO",
    "gonzaga-university":                            "reckvRdtDTU8APIjc",
    "florida-agricultural-and-mechanical-university":"recroX0PfKqZi8rFw",
    "texas-am-corpus-christi":                       "recWxsbdXjVhGin9P",
    "texas-lutheran-university":                     "recnp929tLn96uD2M",
    "central-wyoming-community-college":             "recKYHNiAfFNiNtlt",
    "madison-area-technical-college":                "rechU5JkHaCV42uwq",
    "south-piedmont-community-college":              "recDQLrzobXjQi6Bf",
    "austin-peay-state-university":                  "rec3FNVSKBZuSaYUp",
    "western-governors-university":                  "recA8WgynkEu6ENEP",
    "mott-community-college":                        "reclkpqZt967oCa7n",
    "st-john-s-university":                          "recSyLHcW5S605rfb",
    "utrgv":                                         "recBj5EDpqDc7pAgB",
    "drew-university":                               "recy9X7mP1Kp6cQsF",
}


def strip_tags(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def extract_index_data():
    """Parse index.html for all school cards. Returns dict: slug → field values."""
    with open(os.path.join(ROOT, "index.html")) as f:
        content = f.read()

    pattern = re.compile(
        r'<a class="school-card"\s+href="schools/([^/"]+)/index\.html"'
        r'[^>]*data-chapter-status="([^"]*)"'
        r'[^>]*data-chapter-type="([^"]*)"'
        r'[^>]*>.*?'
        r'<div class="school-sub">(.*?)</div>.*?'
        r'<strong>Top priority:</strong>(.*?)</div>.*?'
        r'<strong>Key signal:</strong>(.*?)</div>',
        re.DOTALL
    )

    results = {}
    for m in pattern.finditer(content):
        slug, ch_status, ch_type, sub, top_pri, key_sig = m.groups()
        sub_text = strip_tags(sub)
        # Location is the part before the first "·"
        location = sub_text.split('·')[0].strip().rstrip('  ') if '·' in sub_text else sub_text
        location = re.sub(r'\s+', ' ', location)

        results[slug] = {
            "location":    location,
            "ch_status":   ch_status,
            "ch_type":     ch_type,
            "top_priority": strip_tags(top_pri),
            "key_signal":  strip_tags(key_sig),
        }
    return results


def get_pilot_partner(slug):
    """Read school hub page and extract Pilot Partner Interest value."""
    hub_path = os.path.join(ROOT, "schools", slug, "index.html")
    if not os.path.exists(hub_path):
        return None

    with open(hub_path) as f:
        content = f.read()

    # Look for the Pilot Partner stat tile
    m = re.search(
        r'<div class="label">Pilot Partner Interest</div>\s*'
        r'<div class="value"[^>]*>(.*?)</div>',
        content, re.DOTALL
    )
    if not m:
        return None

    raw = strip_tags(m.group(1))
    # Normalize to singleSelect values: Yes / Maybe / No
    if "✅" in raw or "Yes" in raw:
        return "Yes"
    elif "🤔" in raw or "Maybe" in raw or "Unsure" in raw or "Considering" in raw:
        return "Maybe"
    elif "❌" in raw or "No" in raw:
        return "No"
    return None


def normalize_chapter_type(ch_type):
    """Map HTML value to Airtable singleSelect option."""
    mapping = {
        "In-Person": "In-Person",
        "Online":    "Virtual",
        "Hybrid":    "Hybrid",
        "TBD":       "TBD",
    }
    return mapping.get(ch_type, "TBD")


def normalize_chapter_status(ch_status):
    """Map HTML value to Airtable singleSelect option."""
    valid = {"Established", "New", "Inactive", "TBD"}
    return ch_status if ch_status in valid else "TBD"


def airtable_patch(record_id, fields):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}/{record_id}"
    resp = requests.patch(url, headers=HEADERS, json={"fields": fields})
    resp.raise_for_status()
    return resp.json()


def main():
    print("Extracting data from index.html...")
    index_data = extract_index_data()
    print(f"  Found {len(index_data)} school cards\n")

    success = 0
    for slug, data in sorted(index_data.items()):
        record_id = SLUG_TO_RECORD.get(slug)
        if not record_id:
            print(f"[SKIP] {slug} — no Airtable record mapping")
            continue

        pilot = get_pilot_partner(slug)
        fields = {
            "fldLgOnqcl0f0reSa": data["location"],
            "fldbmpQT2BuixH5jE": normalize_chapter_status(data["ch_status"]),
            "fldtMyRIwF18MIu2H": normalize_chapter_type(data["ch_type"]),
            "flde3iaMHLarZEmKn": data["key_signal"],
            "fld8CxDjblCkhjBkV": data["top_priority"],
        }
        if pilot:
            fields["fldfSCHsKe3A2L5GH"] = pilot

        print(f"[{slug}]")
        print(f"  loc={data['location']!r}  status={data['ch_status']}  type={data['ch_type']}  pilot={pilot}")
        print(f"  priority={data['top_priority'][:60]!r}")
        try:
            airtable_patch(record_id, fields)
            print(f"  ✓ Updated {record_id}")
            success += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")

        time.sleep(0.25)

    print(f"\n{'='*60}")
    print(f"Done: {success}/{len(index_data)} schools updated")


if __name__ == "__main__":
    main()
