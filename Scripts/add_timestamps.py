#!/usr/bin/env python3
"""
add_timestamps.py — Add Fathom timestamp links to existing meeting reports.

Reads each meeting-N-YYYY-MM-DD.html, fetches the Fathom transcript, asks
Claude which content fragments should get timestamp links, then injects them.

Usage:
    python add_timestamps.py                            # all reports
    python add_timestamps.py --slug mott-community-college
    python add_timestamps.py --file path/to/meeting.html
    python add_timestamps.py --dry-run                  # print plan, no writes
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests
import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Config / paths
# ─────────────────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).parent
REPORT_DIR  = SCRIPTS_DIR.parent / "report"
SCHOOLS_DIR = REPORT_DIR / "schools"

MIN_SCORE = 3   # minimum keyword-match score to accept a timestamp

# Import shared helpers from generate_school.py (safe — main() is guarded)
sys.path.insert(0, str(SCRIPTS_DIR))
import generate_school as _gs

fathom_headers      = _gs.fathom_headers
fetch_transcript    = _gs.fetch_transcript
transcript_to_text  = _gs.transcript_to_text
find_best_timestamp = _gs.find_best_timestamp
ts_link_html        = _gs.ts_link_html
fmt_time            = _gs.fmt_time
find_recording_id   = _gs.find_recording_id


# ─────────────────────────────────────────────────────────────────────────────
# Claude
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a research assistant helping annotate NSLS campus meeting reports "
    "with Fathom recording timestamps. Your output must be valid JSON only — "
    "no markdown, no commentary."
)


def call_claude(prompt: str, max_tokens: int = 4096) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("Error: ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────name───────────────────────────────────────────────────

def extract_calls_url(html: str) -> Optional[str]:
    """Pull the Fathom recording URL from the recording-link anchor."""
    m = re.search(r'class="recording-link"\s+href="(https://fathom\.video/[^"]+)"', html)
    return m.group(1) if m else None


def already_annotated(html: str) -> bool:
    """Return True if the content section already has timestamp ?t= links."""
    content_start = html.find('<div class="content">')
    if content_start == -1:
        return False
    return '?t=' in html[content_start:]


def extract_content_html(html: str) -> str:
    """Return the HTML inside <div class="content">…</div>."""
    start = html.find('<div class="content">')
    if start == -1:
        return html
    start += len('<div class="content">')
    end = html.rfind('</div>\n</main>')
    return html[start:end] if end != -1 else html[start:]


def build_annotation_prompt(content_html: str, transcript_text: str, school_name: str) -> str:
    # Trim transcript to ~12 000 chars to stay within context
    trans_excerpt = transcript_text[:12000]
    # Trim report to ~12 000 chars
    report_excerpt = content_html[:12000]

    return f"""You are annotating a meeting report for {school_name} with timestamps from the Fathom recording.

MEETING REPORT HTML (excerpt):
{report_excerpt}

TRANSCRIPT (excerpt — timestamps in seconds or HH:MM:SS):
{trans_excerpt}

Return a JSON array of annotations. Each item:
{{
  "fragment": "exact verbatim text (25–90 chars) from the HTML right before the timestamp should appear — must be unique in the document, must not span HTML tags",
  "keywords": ["3 to 5 words/phrases that appear verbatim in the transcript at this moment"],
  "label": "brief note on what this timestamp marks (for debugging)"
}}

Rules:
- Only annotate specific claims traceable to a distinct transcript moment: advisor quotes, named pain points, feature requests, specific numbers or stories, explicit reactions to a demo feature.
- Do NOT annotate: section headings, generic background facts, metadata fields (School Type, Advisors Present, etc.), or any text that already has a link.
- Choose "fragment" to end naturally: at the end of a sentence, just before " — ", or just before a closing paren. Never mid-word.
- "keywords" must be words likely to appear in the transcript (not paraphrases).
- Aim for 8–18 annotations per report. Omit low-confidence matches.
- Return ONLY the JSON array. No markdown fences, no commentary."""


def get_annotations(content_html: str, transcript_text: str, school_name: str) -> list:
    prompt = build_annotation_prompt(content_html, transcript_text, school_name)
    raw = call_claude(prompt, max_tokens=3000)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"    [WARN] Claude returned unparseable JSON: {e}")
        print(f"    Raw: {raw[:300]}")
        return []


def inject_timestamps(html: str, annotations: list, items: list, calls_url: str) -> tuple[str, int]:
    """Apply timestamp links to html. Returns (updated_html, count_injected)."""
    injected = 0
    for ann in annotations:
        fragment = ann.get("fragment", "").strip()
        keywords = ann.get("keywords", [])
        if not fragment or not keywords:
            continue

        # Skip if fragment not found (case-sensitive)
        if fragment not in html:
            # Try stripping HTML entities or whitespace variations — give up if still missing
            continue

        secs, score = find_best_timestamp(items, keywords)
        if secs is None or score < MIN_SCORE:
            print(f"    [skip] low score ({score}) — {ann.get('label', fragment[:40])}")
            continue

        link = ts_link_html(calls_url, secs)
        # Only inject once (first occurrence)
        html = html.replace(fragment, fragment + link, 1)
        print(f"    [+] {fmt_time(secs)}  (score={score})  {ann.get('label', fragment[:40])!r}")
        injected += 1

    return html, injected


# ─────────────────────────────────────────────────────────────────────────────
# Per-file entry point
# ─────────────────────────────────────────────────────────────────────────────

def process_file(path, dry_run: bool = False) -> bool:
    print(f"\n{'─'*60}")
    print(f"  {path.relative_to(REPORT_DIR)}")

    html = path.read_text(encoding="utf-8")

    if already_annotated(html):
        print("  [SKIP] already has timestamp links")
        return False

    fathom_url = extract_calls_url(html)
    if not fathom_url:
        print("  [SKIP] could not find Fathom recording URL")
        return False

    print(f"  Recording URL: {fathom_url}")

    # Resolve the API recording ID via the meetings list (calls URL ≠ recordings API ID)
    print("  Resolving recording ID…")
    try:
        recording_id, _, _, calls_url = find_recording_id(fathom_url)
    except Exception as e:
        print(f"  [ERROR] Could not resolve recording ID: {e}")
        return False

    print(f"  Recording ID: {recording_id}  →  {calls_url}")

    # Fetch transcript
    print("  Fetching transcript…")
    try:
        items = fetch_transcript(recording_id)
    except Exception as e:
        print(f"  [ERROR] Fathom fetch failed: {e}")
        return False
    print(f"  Transcript: {len(items)} segments")

    if not items:
        print("  [SKIP] empty transcript")
        return False

    transcript_text = transcript_to_text(items)

    # Extract school name from title tag
    title_m = re.search(r"<title>([^<]+?) &mdash;", html)
    school_name = title_m.group(1) if title_m else path.parent.parent.name

    # Ask Claude for annotations
    print("  Calling Claude for annotations…")
    content_html = extract_content_html(html)
    annotations  = get_annotations(content_html, transcript_text, school_name)
    print(f"  Claude suggested {len(annotations)} annotations")

    if dry_run:
        for ann in annotations:
            print(f"    › {ann.get('label', '')} — fragment: {ann.get('fragment','')[:60]!r}")
        return False

    # Inject
    updated_html, count = inject_timestamps(html, annotations, items, calls_url)
    if count == 0:
        print("  No timestamps injected (all low-score or fragments not found)")
        return False

    path.write_text(updated_html, encoding="utf-8")
    print(f"  [OK] Wrote {count} timestamp links → {path.name}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def collect_reports(slug: Optional[str] = None) -> list:
    if slug:
        school_dir = SCHOOLS_DIR / slug
        return sorted(school_dir.glob("meetings/*.html"))
    return sorted(SCHOOLS_DIR.glob("*/meetings/*.html"))


def main():
    parser = argparse.ArgumentParser(description="Add Fathom timestamps to meeting reports")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--slug",  help="Process a single school by slug (e.g. mott-community-college)")
    group.add_argument("--file",  help="Process a single HTML file by path")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args()

    if args.file:
        files = [Path(args.file)]
    else:
        files = collect_reports(args.slug)

    if not files:
        print("No meeting reports found.")
        sys.exit(1)

    print(f"Found {len(files)} meeting report(s) to process")
    updated = 0
    for f in files:
        if process_file(f, dry_run=args.dry_run):
            updated += 1

    print(f"\n{'='*60}")
    print(f"Done. {updated}/{len(files)} report(s) updated.")


if __name__ == "__main__":
    main()
