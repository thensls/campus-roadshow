#!/usr/bin/env python3
"""
link_timestamps.py — Find Fathom transcript timestamps for Drew University hub bullets
and update the hub HTML with deep links to the recording.

Usage:
  FATHOM_API_KEY=<your_key> python link_timestamps.py

  Add --dry-run to print found timestamps without modifying the HTML.

Output:
  - Prints each bullet point with the found timestamp and confidence score
  - Updates NSLS Roadshow - Drew University.html with small ▶ timestamp links
"""

import os
import re
import sys
import argparse
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SHARE_URL  = "https://fathom.video/calls/607089519"
FATHOM_BASE = "https://api.fathom.ai/external/v1"
HUB_FILE   = "/Users/chrishigbee/Desktop/NSLS Roadshow - Drew University.html"

# Each bullet: the exact <strong> text as it appears in the HTML, plus keyword
# phrases to match against transcript segments (case-insensitive).
# Keywords are weighted — earlier in the list = higher weight.
BULLETS = [
    {
        "strong": "Physical invitation with envelope",
        "keywords": [
            "envelope", "actual envelope", "mailed", "physical invitation",
            "kids now don't get mail", "don't get mail", "invitation letter",
        ],
    },
    {
        "strong": "Speaker broadcasts",
        "keywords": [
            "speaker broadcast", "broadcast", "speaker clips", "clips",
            "inspirational", "speaker series",
        ],
    },
    {
        "strong": "Clarity track demo",
        "keywords": [
            "clarity track", "clarity", "don't know what to do with my life",
            "what to do with my life", "career direction", "undecided",
        ],
    },
    {
        "strong": "SNT visibility in the platform",
        "keywords": [
            "snt", "group roster", "see which students", "small networking team",
            "who's in which", "group visibility", "meeting history",
        ],
    },
    {
        "strong": "Email / identity fragmentation",
        "keywords": [
            "handshake", "email fragmentation", "personal email", "institutional email",
            "any email", "school email", "reconcile", "sync", "manually",
        ],
    },
    {
        "strong": "SNT management entirely manual",
        "keywords": [
            "color-coded", "color coded", "spreadsheet", "paper", "manually track",
            "do these kids actually meet", "don't know if they meet",
        ],
    },
    {
        "strong": "No demographic data",
        "keywords": [
            "marketing major", "how many marketing", "demographic", "major level",
            "major-level", "can't tell", "cannot answer", "faculty asked",
        ],
    },
    {
        "strong": "LTD video content not built for live delivery",
        "keywords": [
            "excruciating", "facilitation guide", "in person", "in-person",
            "watching that video", "virtual", "covid", "wrote our own",
        ],
    },
    {
        "strong": "Key Signal",
        "html_anchor": "callout",   # this one targets the callout strong, not a list item
        "keywords": [
            "ai skeptic", "ethical objection", "environmental", "principled",
            "letter to", "admissions", "ai use", "avoid", "not a fan of ai",
        ],
    },
]

# ---------------------------------------------------------------------------
# Fathom helpers
# ---------------------------------------------------------------------------

def fathom_headers():
    key = os.environ.get("FATHOM_API_KEY", "").strip()
    if not key:
        sys.exit("Error: FATHOM_API_KEY environment variable is not set.")
    return {"X-Api-Key": key}


def find_recording_id(share_url: str) -> str:
    headers = fathom_headers()
    cursor = None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{FATHOM_BASE}/meetings", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        meetings = data if isinstance(data, list) else data.get("items", data.get("data", []))
        for m in meetings:
            candidate = m.get("share_url") or m.get("shareUrl") or ""
            if candidate.rstrip("/") == share_url.rstrip("/"):
                rid = m.get("recording_id") or m.get("recordingId") or m.get("id")
                if rid:
                    return str(rid)
        if isinstance(data, dict):
            cursor = data.get("next_cursor") or data.get("nextCursor")
            if not cursor or not meetings:
                break
        else:
            break
    raise ValueError(f"No Fathom meeting found with share URL: {share_url}")


def fetch_transcript_items(recording_id: str) -> list:
    """Return raw transcript items from Fathom API."""
    headers = fathom_headers()
    r = requests.get(
        f"{FATHOM_BASE}/recordings/{recording_id}/transcript", headers=headers
    )
    r.raise_for_status()
    data = r.json()
    return data.get("transcript", data.get("items", []))


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

def to_seconds(ts):
    """Convert various timestamp formats to seconds (float)."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        ts = ts.strip()
        # HH:MM:SS or MM:SS
        parts = ts.split(":")
        try:
            parts = [float(p) for p in parts]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            if len(parts) == 1:
                return parts[0]
        except ValueError:
            pass
    return None


def fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def score_segment(text: str, keywords: list) -> int:
    """Score a transcript segment against keywords. Higher = better match."""
    text_lower = text.lower()
    score = 0
    for i, kw in enumerate(keywords):
        if kw.lower() in text_lower:
            # Higher-weighted keywords (earlier in list) score more
            score += max(10 - i, 1)
    return score


def find_best_timestamp(items, keywords):
    """
    Slide a window over transcript items to find the segment where keyword
    density is highest. Returns (start_seconds, best_score).
    Window size = 5 consecutive utterances.
    """
    WINDOW = 5
    best_score = 0
    best_ts = None

    for i in range(len(items)):
        window_text = " ".join(
            item.get("text", "") for item in items[i : i + WINDOW]
        )
        score = score_segment(window_text, keywords)
        if score > best_score:
            best_score = score
            # Use the start time of the first item in the window
            item = items[i]
            ts = (
                item.get("start_time")
                or item.get("start_offset")
                or item.get("startTime")
                or item.get("timestamp")
            )
            best_ts = to_seconds(ts)

    return best_ts, best_score


# ---------------------------------------------------------------------------
# HTML patching
# ---------------------------------------------------------------------------

def make_ts_link(share_url: str, seconds: float, label: str) -> str:
    ts_url = f"{share_url}?t={int(seconds)}"
    return (
        f' <a href="{ts_url}" target="_blank" '
        f'style="display:inline-flex;align-items:center;gap:3px;font-size:11px;'
        f'font-weight:600;color:var(--muted);text-decoration:none;'
        f'background:#F0F4FF;border:1px solid #D8E4FF;border-radius:4px;'
        f'padding:1px 6px;margin-left:4px;vertical-align:middle;white-space:nowrap;" '
        f'title="Jump to this moment in the recording">'
        f'&#9654; {label}</a>'
    )


def patch_html(html: str, results: list) -> str:
    for r in results:
        if r["seconds"] is None:
            print(f"  [SKIP] {r['strong']!r} — no timestamp found (score={r['score']})")
            continue

        link = make_ts_link(SHARE_URL, r["seconds"], fmt_time(r["seconds"]))
        strong_text = r["strong"]

        if r.get("html_anchor") == "callout":
            # Callout: patch the <strong> tag that contains the signal text
            old = f"<strong>&#x26A0;&#xFE0F; {strong_text}"
            new = f"<strong>&#x26A0;&#xFE0F; {strong_text}{link}"
            if old in html:
                html = html.replace(old, new, 1)
                print(f"  [OK]   {strong_text!r} → {fmt_time(r['seconds'])} (score={r['score']})")
            else:
                print(f"  [MISS] Callout anchor not found for {strong_text!r}")
        else:
            # List item: patch the </strong> immediately after the bullet label
            old = f"<strong>{strong_text}</strong>"
            new = f"<strong>{strong_text}</strong>{link}"
            if old in html:
                html = html.replace(old, new, 1)
                print(f"  [OK]   {strong_text!r} → {fmt_time(r['seconds'])} (score={r['score']})")
            else:
                print(f"  [MISS] Could not find <strong>{strong_text}</strong> in HTML")

    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Link Fathom timestamps to hub page bullets")
    parser.add_argument("--dry-run", action="store_true", help="Print timestamps without modifying HTML")
    args = parser.parse_args()

    print("Finding recording ID from share URL...")
    recording_id = find_recording_id(SHARE_URL)
    print(f"  Recording ID: {recording_id}")

    print("Fetching transcript...")
    items = fetch_transcript_items(recording_id)
    print(f"  {len(items)} transcript segments loaded")

    print("\nScoring bullet points against transcript:")
    results = []
    for bullet in BULLETS:
        seconds, score = find_best_timestamp(items, bullet["keywords"])
        results.append({**bullet, "seconds": seconds, "score": score})
        label = fmt_time(seconds) if seconds is not None else "not found"
        print(f"  {bullet['strong']!r:50s} → {label}  (score={score})")

    if args.dry_run:
        print("\n--dry-run: HTML not modified.")
        return

    print(f"\nPatching HTML: {HUB_FILE}")
    with open(HUB_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    patched = patch_html(html, results)

    with open(HUB_FILE, "w", encoding="utf-8") as f:
        f.write(patched)

    print("\nDone. Reload the page to see timestamp links.")


if __name__ == "__main__":
    main()
