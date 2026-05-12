#!/usr/bin/env python3
"""
fix_timestamp_links.py — One-time migration to fix broken Fathom timestamp deep-links
in all hub pages.

Background:
  Timestamp links were generated as /share/XXXX?t=N but Fathom only supports ?t=
  deep-linking on /calls/XXXXXXX URLs. This script finds every /share/XXXX?t=N
  occurrence, looks up the corresponding /calls/ ID via the Fathom API, and rewrites
  the links in place.

Usage:
  python fix_timestamp_links.py [--dry-run]
"""

import os
import re
import sys
import argparse
import requests
from pathlib import Path

FATHOM_BASE = "https://api.fathom.ai/external/v1"
REPORT_DIR  = Path(__file__).parent.parent / "report"


def fathom_headers():
    key = os.environ.get("FATHOM_API_KEY", "").strip()
    if not key:
        sys.exit("Error: FATHOM_API_KEY environment variable is not set.")
    return {"X-Api-Key": key}


def get_share_to_calls_map(share_urls: set) -> dict:
    """
    Given a set of /share/XXXX URLs, return a dict mapping each to its
    /calls/{recording_id} equivalent.
    """
    headers  = fathom_headers()
    mapping  = {}
    cursor   = None
    remaining = set(share_urls)

    print(f"Looking up {len(remaining)} share URL(s) via Fathom API...")

    while remaining:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{FATHOM_BASE}/meetings", headers=headers, params=params)
        r.raise_for_status()
        data     = r.json()
        meetings = data if isinstance(data, list) else data.get("items", data.get("data", []))

        for m in meetings:
            share = (
                m.get("share_url") or m.get("shareUrl") or ""
            ).rstrip("/")
            if share in remaining:
                # Use the "url" field which is the correct public /calls/ URL
                calls_url = m.get("url") or m.get("callUrl") or ""
                if not calls_url:
                    # Fallback: shouldn't be needed but keep for safety
                    rid = m.get("recording_id") or m.get("recordingId") or m.get("id")
                    calls_url = f"https://fathom.video/calls/{rid}" if rid else ""
                if calls_url:
                    mapping[share] = calls_url
                    remaining.discard(share)
                    print(f"  {share}  →  {calls_url}")

        if not remaining:
            break

        if isinstance(data, dict):
            cursor = data.get("next_cursor") or data.get("nextCursor")
            if not cursor or not meetings:
                break
        else:
            break

    for url in remaining:
        print(f"  [WARN] Could not resolve: {url}")

    return mapping


def fix_file(path: Path, mapping: dict, dry_run: bool) -> int:
    """Replace /share/XXXX?t=N links with /calls/ID?t=N in a single file.
    Returns number of replacements made."""
    html = path.read_text(encoding="utf-8")
    original = html

    for share_url, calls_url in mapping.items():
        # Match share URL used as timestamp link base (with ?t=)
        pattern = re.escape(share_url) + r'(\?t=\d+)'
        replacement = calls_url + r'\1'
        html = re.sub(pattern, replacement, html)

    count = sum(
        len(re.findall(re.escape(su) + r'\?t=\d+', original))
        for su in mapping
    )

    if html != original:
        if not dry_run:
            path.write_text(html, encoding="utf-8")
        status = "[DRY RUN]" if dry_run else "[FIXED]"
        print(f"  {status}  {path.relative_to(REPORT_DIR)}  ({count} link(s) updated)")
    else:
        print(f"  [SKIP]   {path.relative_to(REPORT_DIR)}  (no share timestamp links found)")

    return count


def main():
    parser = argparse.ArgumentParser(description="Fix broken Fathom /share/?t= links → /calls/?t=")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = parser.parse_args()

    # Find all hub index.html files
    hub_files = list(REPORT_DIR.glob("schools/*/index.html"))
    print(f"Found {len(hub_files)} hub pages to scan.\n")

    # Collect all unique /share/ URLs used in timestamp links
    share_url_pattern = re.compile(r'(https://fathom\.video/share/[A-Za-z0-9_\-]+)\?t=\d+')
    share_urls_found  = set()

    for f in hub_files:
        html = f.read_text(encoding="utf-8")
        for m in share_url_pattern.finditer(html):
            share_urls_found.add(m.group(1))

    if not share_urls_found:
        print("No /share/?t= timestamp links found — nothing to fix.")
        return

    print(f"Found {len(share_urls_found)} unique /share/ URL(s) with timestamp links:")
    for u in sorted(share_urls_found):
        print(f"  {u}")
    print()

    # Resolve each to a /calls/ URL
    mapping = get_share_to_calls_map(share_urls_found)

    if not mapping:
        print("\nNo mappings resolved — exiting.")
        return

    print(f"\nPatching {len(hub_files)} file(s)...")
    total = 0
    for f in hub_files:
        total += fix_file(f, mapping, args.dry_run)

    action = "Would update" if args.dry_run else "Updated"
    print(f"\nDone. {action} {total} timestamp link(s) across {len(hub_files)} file(s).")
    if args.dry_run:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
