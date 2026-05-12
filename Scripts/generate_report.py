#!/usr/bin/env python3
"""
NSLS Society Platform Roadshow — Meeting Report Generator

Usage:
  python generate_report.py \
    --fathom-url "https://fathom.video/share/..." \
    --school "Drew University" \
    --meeting-type "Meeting 1" \
    --tier 4 \
    --csr "Zoë Wallis"

Env vars required:
  FATHOM_API_KEY      — Fathom API key
  ANTHROPIC_API_KEY   — Anthropic API key
"""

import argparse
import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path

import requests
import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FATHOM_BASE = "https://api.fathom.ai/external/v1"
REPORTS_DIR = Path("/Users/chrishigbee/Desktop/reports")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fathom_headers() -> dict:
    key = os.environ.get("FATHOM_API_KEY", "").strip()
    if not key:
        sys.exit("Error: FATHOM_API_KEY environment variable is not set.")
    return {"X-Api-Key": key}


def find_recording_id(share_url: str) -> str:
    """Paginate /meetings until we find the recording whose share_url matches."""
    headers = fathom_headers()
    cursor = None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(f"{FATHOM_BASE}/meetings", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()

        # Handle both list-style and cursor-style responses
        meetings = data if isinstance(data, list) else data.get("items", data.get("data", []))

        for m in meetings:
            candidate = m.get("share_url") or m.get("shareUrl") or ""
            if candidate.rstrip("/") == share_url.rstrip("/"):
                rid = m.get("recording_id") or m.get("recordingId") or m.get("id")
                if rid:
                    return str(rid)

        # Pagination
        if isinstance(data, dict):
            cursor = data.get("next_cursor") or data.get("nextCursor")
            if not cursor or not meetings:
                break
        else:
            break  # list response — only one page

    raise ValueError(
        f"No Fathom meeting found with share URL: {share_url}\n"
        "Tip: verify the URL or check that your API key has access to this recording."
    )


def fetch_transcript(recording_id: str) -> tuple:
    """Return (formatted_text, meeting_title, meeting_date, attendees)."""
    headers = fathom_headers()

    # Transcript
    r = requests.get(
        f"{FATHOM_BASE}/recordings/{recording_id}/transcript", headers=headers
    )
    r.raise_for_status()
    data = r.json()
    items = data.get("transcript", [])

    lines = []
    speakers_seen = set()
    for item in items:
        spk = item.get("speaker", {})
        name = spk.get("display_name") or spk.get("name") or "Unknown"
        ts = item.get("timestamp", "")
        text = item.get("text", "")
        lines.append(f"[{ts}] {name}: {text}")
        speakers_seen.add(name)

    transcript_text = "\n".join(lines)

    # Try to get meeting metadata (title, date) from the recording record
    title = f"Recording {recording_id}"
    date_str = datetime.today().strftime("%Y-%m-%d")
    try:
        mr = requests.get(f"{FATHOM_BASE}/recordings/{recording_id}", headers=headers)
        if mr.ok:
            meta = mr.json()
            title = meta.get("title") or meta.get("name") or title
            raw_date = meta.get("created_at") or meta.get("date") or meta.get("started_at") or ""
            if raw_date:
                try:
                    date_str = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                except Exception:
                    pass
    except Exception:
        pass

    return transcript_text, title, date_str, sorted(speakers_seen)


# ---------------------------------------------------------------------------
# Report generation (Claude)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a product research analyst for NSLS (National Society of Leadership and Success), a membership organization that supports student leadership and career development on college campuses. NSLS is building a new platform called Society — a modern, AI-powered student engagement and career readiness platform built on top of the existing NSLS brand, curriculum, and network.

You generate structured campus meeting reports from meeting transcripts. These reports are used internally to track feedback across a roadshow of 20-25 partner schools, identify product signals, and build a Product Council of early partners.

Your reports must be grounded entirely in what was actually said in the transcript. Do not speculate or invent details. Quote sparingly and only when the direct language is especially meaningful."""


def build_user_prompt(transcript_text: str, school: str, meeting_type: str, tier: int, csr: str) -> str:
    return f"""Generate a structured campus roadshow meeting report from the following transcript.

The report must include these eight sections, rendered as clean HTML. Use <section> tags for each section. Add class="section" to each section. Use <h2> for section titles with class="section-title". Do not return a full HTML document — return only the inner content (the sections themselves, no <html>, <head>, <body>, or <main> tags).

School: {school}
Meeting Type: {meeting_type}
Tier/Segment: {tier}
CSR: {csr}

---

**Section 1 — School Snapshot**
School type, size/culture if mentioned, chapter status (new/established), chapter type (standard/hybrid/online), advisors present, and any notable institutional context shared in the meeting. Render as a card with <div class="card">.

**Section 2 — Discovery Findings**
Three subsections:
- What They Want to Preserve (about NSLS)
- What Isn't Working (pain points, frustrations)
- School Priorities (what the institution is focused on right now)
Ground all findings in direct quotes or close paraphrases. Use <h3> for subsection titles. Use <ul> for lists.

**Section 3 — Key Themes & Signals**
The 3-5 most important insights from this meeting that should inform product decisions or rollout strategy. Number and title each theme. Use <div class="theme-card"> for each theme with an <h3 class="theme-title"> and <p> body.

**Section 4 — Society Reception**
How the advisors responded to the Society demo. Include:
- Self-reported enthusiasm score (if given) — render as <div class="enthusiasm-score">X/10</div>
- What landed well
- What raised questions or friction
- Any surprises (positive or negative)

**Section 5 — Feature-Level Feedback**
A table with columns: Feature | Signal | Notes.
Signal values: "Strong" (green), "Positive" (teal/blue), "Open Question" (amber), "Needs Care" (red).
Use <table class="feature-table"><thead>...</thead><tbody>...</tbody></table>.
For the Signal column use <span class="badge badge-strong">, <span class="badge badge-positive">, <span class="badge badge-question">, or <span class="badge badge-care"> accordingly.

**Section 6 — Advisor Profiles**
A brief profile of each advisor present: background, motivations, communication style, and potential as a pilot partner or Product Council member. Use <div class="advisor-card"> for each.

**Section 7 — Next Steps & Open Items**
Two subsections:
- Confirmed Action Items — render as checkboxes: <ul class="action-items"><li><label><input type="checkbox"> [item with owner/timing]</label></li></ul>
- Open Questions — render as <ul class="open-questions">

**Section 8 — Roadshow Metadata**
A structured two-column summary table with these exact fields:
School | Location | School Type | Chapter Status | Chapter Type | Segment | Meeting 1 Enthusiasm Score | Pilot Partner Interest | Product Council Interest | Top Pain Points | Top Feature Signals | Primary Concern | Unique Angle | Recommended Next Step | CSR

Use <table class="metadata-table"><tbody><tr><th>Field</th><td>Value</td></tr>...</tbody></table>.

---

TRANSCRIPT:
{transcript_text}"""


def generate_report_content(
    transcript_text: str, school: str, meeting_type: str, tier: int, csr: str, dry_run: bool
) -> str:
    prompt = build_user_prompt(transcript_text, school, meeting_type, tier, csr)

    if dry_run:
        print("\n=== DRY RUN — ASSEMBLED PROMPT ===")
        print(f"SYSTEM:\n{SYSTEM_PROMPT}\n")
        print(f"USER:\n{prompt[:2000]}...\n[truncated]")
        sys.exit(0)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    print("Calling Claude to generate report...")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

SHARED_CSS = """
  :root {
    --navy: #1B2A4A;
    --gold: #F5C518;
    --green: #4CAF50;
    --teal: #26A69A;
    --amber: #FFC107;
    --red: #F44336;
    --bg: #F7F8FA;
    --card: #FFFFFF;
    --text: #1a1a2e;
    --muted: #6b7280;
    --border: #e5e7eb;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
  }
  a { color: var(--navy); }
  a:hover { color: var(--gold); }

  /* Header */
  .page-header {
    background: var(--navy);
    color: white;
    padding: 2rem 2.5rem 1.5rem;
  }
  .page-header .eyebrow {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--gold);
    margin-bottom: 0.4rem;
  }
  .page-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
  }
  .page-header .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1.25rem;
    margin-top: 1rem;
    align-items: center;
  }
  .page-header .meta-chip {
    font-size: 0.8rem;
    color: rgba(255,255,255,0.75);
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .page-header .recording-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.85rem;
    background: rgba(245,197,24,0.15);
    border: 1px solid rgba(245,197,24,0.4);
    border-radius: 6px;
    color: var(--gold);
    font-size: 0.8rem;
    font-weight: 600;
    text-decoration: none;
    transition: background 0.15s;
  }
  .page-header .recording-link:hover {
    background: rgba(245,197,24,0.25);
    color: var(--gold);
  }

  /* Breadcrumb */
  .breadcrumb {
    background: white;
    border-bottom: 1px solid var(--border);
    padding: 0.6rem 2.5rem;
    font-size: 0.8rem;
    color: var(--muted);
  }
  .breadcrumb a { color: var(--navy); text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .breadcrumb span { margin: 0 0.4rem; }

  /* Main content */
  main { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }

  /* Section */
  .section {
    margin-bottom: 2.5rem;
  }
  .section-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--navy);
    padding-left: 0.85rem;
    border-left: 4px solid var(--gold);
    margin-bottom: 1rem;
  }

  /* Card */
  .card {
    background: var(--card);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04);
    padding: 1.25rem 1.5rem;
  }
  .card h3 {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.6rem;
    margin-top: 1rem;
  }
  .card h3:first-child { margin-top: 0; }
  .card ul { padding-left: 1.25rem; }
  .card li { margin-bottom: 0.3rem; font-size: 0.93rem; }
  .card p { font-size: 0.93rem; }

  /* Theme cards */
  .theme-card {
    background: var(--card);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    border-left: 3px solid var(--navy);
  }
  .theme-card .theme-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.4rem;
  }
  .theme-card p { font-size: 0.9rem; color: #374151; }

  /* Enthusiasm score */
  .enthusiasm-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background: var(--navy);
    color: var(--gold);
    font-size: 1.3rem;
    font-weight: 800;
    margin-bottom: 1rem;
  }

  /* Feature table */
  .feature-table {
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    font-size: 0.88rem;
  }
  .feature-table thead tr {
    background: var(--navy);
    color: white;
  }
  .feature-table th {
    padding: 0.7rem 1rem;
    text-align: left;
    font-weight: 600;
    font-size: 0.8rem;
    letter-spacing: 0.04em;
  }
  .feature-table td {
    padding: 0.65rem 1rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .feature-table tr:last-child td { border-bottom: none; }
  .feature-table tr:nth-child(even) { background: #fafafa; }

  /* Badges */
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge-strong   { background: #dcfce7; color: #166534; }
  .badge-positive { background: #ccfbf1; color: #0f766e; }
  .badge-question { background: #fef9c3; color: #854d0e; }
  .badge-care     { background: #fee2e2; color: #991b1b; }

  /* Advisor cards */
  .advisor-card {
    background: var(--card);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.75rem;
  }
  .advisor-card h3 {
    font-size: 1rem;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.4rem;
  }
  .advisor-card p { font-size: 0.9rem; color: #374151; }

  /* Action items / open questions */
  .action-items, .open-questions {
    list-style: none;
    padding: 0;
  }
  .action-items li, .open-questions li {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
  }
  .action-items li:last-child, .open-questions li:last-child { border-bottom: none; }
  .action-items label { display: flex; align-items: flex-start; gap: 0.5rem; cursor: pointer; }
  .action-items input[type=checkbox] { margin-top: 0.2rem; flex-shrink: 0; }

  /* Metadata table */
  .metadata-table {
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    font-size: 0.88rem;
  }
  .metadata-table th {
    padding: 0.6rem 1rem;
    text-align: left;
    font-weight: 600;
    color: var(--muted);
    font-size: 0.8rem;
    width: 38%;
    background: #f9fafb;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .metadata-table td {
    padding: 0.6rem 1rem;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .metadata-table tr:last-child th,
  .metadata-table tr:last-child td { border-bottom: none; }

  /* School index — meeting cards */
  .meeting-card {
    background: var(--card);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    padding: 1rem 1.4rem;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.15s;
  }
  .meeting-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
  .meeting-card .meeting-info h3 { font-size: 1rem; font-weight: 700; color: var(--navy); }
  .meeting-card .meeting-info p { font-size: 0.85rem; color: var(--muted); margin-top: 0.2rem; }
  .meeting-card .meeting-score {
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--gold);
    background: var(--navy);
    border-radius: 50%;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  /* Roadshow index — school rows */
  .school-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }
  .school-card {
    background: var(--card);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    padding: 1.25rem;
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.15s;
    border-top: 3px solid var(--navy);
  }
  .school-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
  .school-card h3 { font-size: 1rem; font-weight: 700; color: var(--navy); margin-bottom: 0.5rem; }
  .school-card .chip-row { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
  .chip {
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    background: #e5e7eb;
    color: #374151;
  }
  .chip.tier { background: #dbeafe; color: #1e40af; }
  .school-card p { font-size: 0.82rem; color: var(--muted); }

  /* Footer */
  footer {
    text-align: center;
    font-size: 0.75rem;
    color: var(--muted);
    padding: 2rem;
    border-top: 1px solid var(--border);
    margin-top: 3rem;
  }
"""


def make_meeting_html(
    school: str,
    meeting_type: str,
    date_str: str,
    meeting_number: int,
    fathom_url: str,
    report_content: str,
    school_slug: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{school} — {meeting_type} | NSLS Roadshow</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
{SHARED_CSS}
  </style>
</head>
<body>

<header class="page-header">
  <div class="eyebrow">NSLS Society Platform Roadshow</div>
  <h1>{school} — {meeting_type}</h1>
  <div class="meta-row">
    <span class="meta-chip">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
      {date_str}
    </span>
    <a class="recording-link" href="{fathom_url}" target="_blank">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" stroke="none"/></svg>
      View Recording
    </a>
  </div>
</header>

<nav class="breadcrumb">
  <a href="../../index.html">Roadshow Home</a>
  <span>›</span>
  <a href="../index.html">{school}</a>
  <span>›</span>
  {meeting_type}
</nav>

<main>
{report_content}
</main>

<footer>
  Generated by Society Roadshow Reporting System &nbsp;·&nbsp; {datetime.today().strftime("%B %d, %Y")}
</footer>

</body>
</html>"""


def make_school_index_html(school: str, meetings: list, school_slug: str) -> str:
    """meetings = list of dicts with keys: number, type, date, file, score, next_step"""
    meeting_cards = ""
    for m in sorted(meetings, key=lambda x: x["number"]):
        score_html = (
            f'<div class="meeting-score">{m["score"]}</div>' if m.get("score") else ""
        )
        meeting_cards += f"""
    <a class="meeting-card" href="meetings/{m['file']}">
      <div class="meeting-info">
        <h3>{m['type']} &nbsp; <span style="font-weight:400;font-size:0.85rem;color:#6b7280">{m['date']}</span></h3>
        <p>{m.get('next_step', '')}</p>
      </div>
      {score_html}
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{school} | NSLS Roadshow</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
{SHARED_CSS}
  </style>
</head>
<body>

<header class="page-header">
  <div class="eyebrow">NSLS Society Platform Roadshow</div>
  <h1>{school}</h1>
</header>

<nav class="breadcrumb">
  <a href="../index.html">Roadshow Home</a>
  <span>›</span>
  {school}
</nav>

<main>
  <section class="section">
    <h2 class="section-title">Meetings</h2>
    {meeting_cards}
  </section>

  <section class="section">
    <h2 class="section-title">Themes Across Meetings</h2>
    <div class="card">
      <p style="color:#6b7280;font-style:italic;">Will be populated after Meeting 2+.</p>
    </div>
  </section>
</main>

<footer>
  Generated by Society Roadshow Reporting System &nbsp;·&nbsp; {datetime.today().strftime("%B %d, %Y")}
</footer>

</body>
</html>"""


def make_roadshow_index_html(schools: list) -> str:
    """schools = list of dicts: name, slug, tier, meetings_count, latest_score, pilot, council, concern"""
    school_cards = ""
    for s in sorted(schools, key=lambda x: x.get("tier", 99)):
        score_display = s.get("latest_score", "—")
        pilot = s.get("pilot", "TBD")
        council = s.get("council", "TBD")
        school_cards += f"""
    <a class="school-card" href="schools/{s['slug']}/index.html">
      <h3>{s['name']}</h3>
      <div class="chip-row">
        <span class="chip tier">Tier {s.get('tier','?')}</span>
        <span class="chip">{s.get('meetings_count',0)} meeting(s)</span>
        <span class="chip">Score: {score_display}</span>
      </div>
      <p>Pilot: {pilot} &nbsp;·&nbsp; Council: {council}</p>
      <p style="margin-top:0.3rem;">{s.get('concern','')}</p>
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSLS Society Platform Roadshow</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
{SHARED_CSS}
  </style>
</head>
<body>

<header class="page-header">
  <div class="eyebrow">NSLS</div>
  <h1>Society Platform Roadshow</h1>
  <div class="meta-row">
    <span class="meta-chip">{len(schools)} school(s) tracked</span>
  </div>
</header>

<main>
  <section class="section">
    <h2 class="section-title">Schools</h2>
    <div class="school-grid">
      {school_cards}
    </div>
  </section>
</main>

<footer>
  Generated by Society Roadshow Reporting System &nbsp;·&nbsp; {datetime.today().strftime("%B %d, %Y")}
</footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_school_meta(school_dir: Path) -> dict:
    meta_path = school_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {"meetings": []}


def save_school_meta(school_dir: Path, meta: dict) -> None:
    (school_dir / "meta.json").write_text(json.dumps(meta, indent=2))


def load_roadshow_meta(reports_dir: Path) -> dict:
    meta_path = reports_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {"schools": []}


def save_roadshow_meta(reports_dir: Path, meta: dict) -> None:
    (reports_dir / "meta.json").write_text(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="NSLS Roadshow Meeting Report Generator")
    parser.add_argument("--fathom-url", required=True, help="Fathom share URL")
    parser.add_argument("--school", required=True, help="School name (e.g. 'Drew University')")
    parser.add_argument("--meeting-type", default="Discovery & Demo Meeting", help="Meeting label (e.g. 'Discovery & Demo Meeting')")
    parser.add_argument("--tier", type=int, default=3, help="School tier/segment (1-4)")
    parser.add_argument("--csr", default="", help="CSR name")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt without calling APIs")
    args = parser.parse_args()

    school_slug = slugify(args.school)
    school_dir = REPORTS_DIR / "schools" / school_slug
    meetings_dir = school_dir / "meetings"
    meetings_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Fetch transcript ---
    print(f"Looking up Fathom recording for: {args.fathom_url}")
    recording_id = find_recording_id(args.fathom_url)
    print(f"Found recording ID: {recording_id}")

    print("Fetching transcript...")
    transcript_text, meeting_title, meeting_date, attendees = fetch_transcript(recording_id)
    print(f"Transcript fetched — {len(transcript_text.splitlines())} lines, date: {meeting_date}")

    # --- 2. Generate report ---
    report_content = generate_report_content(
        transcript_text, args.school, args.meeting_type, args.tier, args.csr, args.dry_run
    )

    # --- 3. Determine meeting number ---
    existing = list(meetings_dir.glob("meeting-*.html"))
    meeting_number = len(existing) + 1
    filename = f"meeting-{meeting_number}-{meeting_date}.html"

    # --- 4. Save meeting report ---
    meeting_html = make_meeting_html(
        school=args.school,
        meeting_type=args.meeting_type,
        date_str=meeting_date,
        meeting_number=meeting_number,
        fathom_url=args.fathom_url,
        report_content=report_content,
        school_slug=school_slug,
    )
    meeting_path = meetings_dir / filename
    meeting_path.write_text(meeting_html)
    print(f"Saved meeting report: {meeting_path}")

    # --- 5. Update school meta & index ---
    school_meta = load_school_meta(school_dir)
    school_meta["name"] = args.school
    school_meta["slug"] = school_slug
    school_meta["tier"] = args.tier
    school_meta["csr"] = args.csr

    new_meeting_entry = {
        "number": meeting_number,
        "type": args.meeting_type,
        "date": meeting_date,
        "file": filename,
        "score": None,
        "next_step": "",
    }
    school_meta.setdefault("meetings", []).append(new_meeting_entry)
    save_school_meta(school_dir, school_meta)

    school_index = make_school_index_html(args.school, school_meta["meetings"], school_slug)
    (school_dir / "index.html").write_text(school_index)
    print(f"Updated school index: {school_dir / 'index.html'}")

    # --- 6. Update roadshow meta & index ---
    roadshow_meta = load_roadshow_meta(REPORTS_DIR)
    schools = roadshow_meta.setdefault("schools", [])
    school_entry = next((s for s in schools if s["slug"] == school_slug), None)
    if school_entry is None:
        school_entry = {
            "name": args.school,
            "slug": school_slug,
            "tier": args.tier,
            "csr": args.csr,
            "meetings_count": 0,
            "latest_score": None,
            "pilot": "TBD",
            "council": "TBD",
            "concern": "",
        }
        schools.append(school_entry)
    school_entry["meetings_count"] = len(school_meta["meetings"])
    save_roadshow_meta(REPORTS_DIR, roadshow_meta)

    roadshow_index = make_roadshow_index_html(schools)
    (REPORTS_DIR / "index.html").write_text(roadshow_index)
    print(f"Updated roadshow index: {REPORTS_DIR / 'index.html'}")

    print("\nDone.")
    print(f"  Meeting report : {meeting_path}")
    print(f"  School index   : {school_dir / 'index.html'}")
    print(f"  Roadshow index : {REPORTS_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
