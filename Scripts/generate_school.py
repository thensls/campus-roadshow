#!/usr/bin/env python3
"""
generate_school.py — Full NSLS Roadshow school generator.

Steps:
  1. Fetch transcript from Fathom (by calls URL or share URL)
  2. Claude generates meeting report HTML (8 sections, updated CSS)
  3. Claude generates hub page data as JSON (stats, advisors, highlights, actions + keywords)
  4. Keyword-match hub bullets/actions to Fathom timestamps
  5. Optionally fetch Airtable survey data for Survey Highlights section
  6. Write hub page + meeting report with current cream-theme CSS
  7. Insert school card into NSLS Roadshow.html (--update-index)

Usage
-----
  python3 Scripts/generate_school.py \\
    --name "Mott Community College" \\
    --location "Flint, MI" \\
    --type "Community College · Public 2-Year" \\
    --fathom-url "https://fathom.video/calls/602086664" \\
    --csr "Zoë Wallis" \\
    --tier 3 \\
    [--date 2026-03-25]          # override; default = date from Fathom metadata
    [--slug mott-community-college]
    [--meeting-num 1]
    [--airtable-id recXXXXXXXX]  # Airtable survey record ID (optional)
    [--update-index]             # auto-insert card into NSLS Roadshow.html
    [--dry-run]                  # print prompts, skip API calls

Env vars required:
  FATHOM_API_KEY
  ANTHROPIC_API_KEY

Env vars optional:
  AIRTABLE_API_KEY   (needed only with --airtable-id)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

FATHOM_BASE      = "https://api.fathom.ai/external/v1"
AIRTABLE_BASE    = "https://api.airtable.com/v0"
AIRTABLE_BASE_ID = "app5rj9bOGQNFoIoD"
AIRTABLE_TABLE   = "Survey%20Responses"

SCRIPTS_DIR = Path(__file__).parent
PROJECT     = SCRIPTS_DIR.parent / "report"
INDEX_FILE  = PROJECT / "index.html"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def to_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fmt_date(date_str: str) -> str:
    """'2026-03-25' → 'March 25, 2026'"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return date_str


# ─────────────────────────────────────────────────────────────────────────────
# Fathom API
# ─────────────────────────────────────────────────────────────────────────────

def fathom_headers() -> dict:
    key = os.environ.get("FATHOM_API_KEY", "").strip()
    if not key:
        sys.exit("Error: FATHOM_API_KEY is not set.")
    return {"X-Api-Key": key}


def find_recording_id(url: str) -> tuple:
    """Find Fathom recording ID by searching meetings for matching share/calls URL.
    Returns (recording_id, duration_label, meeting_date) — all three sourced from
    the meetings list so we don't need a separate /recordings/{id} call."""
    headers = fathom_headers()

    # First try: search through meetings list
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
            candidates = [
                m.get("share_url") or "",
                m.get("shareUrl") or "",
                m.get("url") or "",
            ]
            if url.rstrip("/") in [c.rstrip("/") for c in candidates if c]:
                # Use the public "url" field (/calls/XXXXXXXXX) — NOT recording_id
                # which is an internal integer that produces broken URLs
                calls_url = m.get("url") or ""
                rid = m.get("recording_id") or m.get("recordingId") or m.get("id")
                if calls_url or rid:
                    # Compute duration from start/end timestamps
                    duration_label = "? min"
                    try:
                        t0 = m.get("recording_start_time") or ""
                        t1 = m.get("recording_end_time") or ""
                        if t0 and t1:
                            dt0 = datetime.fromisoformat(t0.replace("Z", "+00:00"))
                            dt1 = datetime.fromisoformat(t1.replace("Z", "+00:00"))
                            mins = int((dt1 - dt0).total_seconds()) // 60
                            duration_label = f"{mins} min"
                    except Exception:
                        pass
                    # Extract meeting date
                    meeting_date = datetime.today().strftime("%Y-%m-%d")
                    try:
                        raw = m.get("recording_start_time") or m.get("scheduled_start_time") or ""
                        if raw:
                            meeting_date = datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    # recording_id is the internal integer used for transcript fetch only
                    # calls_url (from m["url"]) is the correct ID for ?t= timestamp links
                    return_id = str(rid) if rid else re.search(r"/calls/(\d+)", calls_url or "").group(1) if calls_url else ""
                    return return_id, duration_label, meeting_date, calls_url
        if isinstance(data, dict):
            cursor = data.get("next_cursor") or data.get("nextCursor")
            if not cursor or not meetings:
                break
        else:
            break

    # Fallback: extract numeric ID from URL path (e.g. /calls/602086664)
    m = re.search(r"/(?:calls|recordings?)/(\d+)", url)
    if m:
        candidate_id = m.group(1)
        calls_url = f"https://fathom.video/calls/{candidate_id}"
        print(f"  [fallback] Using ID extracted from URL: {candidate_id}")
        return candidate_id, "? min", datetime.today().strftime("%Y-%m-%d"), calls_url

    raise ValueError(f"Could not find Fathom recording for URL: {url}")


def fetch_transcript(recording_id: str) -> list:
    """Return transcript items (raw dicts with text, speaker, start_time etc.)."""
    headers = fathom_headers()
    r = requests.get(f"{FATHOM_BASE}/recordings/{recording_id}/transcript", headers=headers)
    r.raise_for_status()
    data = r.json()
    return data.get("transcript", data.get("items", []))


def transcript_to_text(items: list) -> str:
    """Format transcript items as readable text for Claude."""
    lines = []
    for item in items:
        spk = item.get("speaker") or {}
        name = spk.get("display_name") or spk.get("name") or "Unknown"
        ts = item.get("timestamp") or item.get("start_time") or item.get("startTime") or ""
        text = item.get("text", "")
        lines.append(f"[{ts}] {name}: {text}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Timestamp matching (from link_timestamps.py)
# ─────────────────────────────────────────────────────────────────────────────

def to_seconds(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        parts = ts.strip().split(":")
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
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def find_best_timestamp(items: list, keywords: list):
    """Slide a 5-utterance window over transcript items; return (start_seconds, best_score)."""
    WINDOW = 5
    best_score = 0
    best_ts = None
    for i in range(len(items)):
        window_text = " ".join(item.get("text", "") for item in items[i: i + WINDOW]).lower()
        score = sum(max(10 - j, 1) for j, kw in enumerate(keywords) if kw.lower() in window_text)
        if score > best_score:
            best_score = score
            best_ts = to_seconds(
                items[i].get("start_time")
                or items[i].get("start_offset")
                or items[i].get("startTime")
                or items[i].get("timestamp")
            )
    return best_ts, best_score


def ts_link_html(fathom_url: str, seconds: float) -> str:
    t = int(seconds)
    label = fmt_time(seconds)
    return (
        f'<a href="{fathom_url}?t={t}" target="_blank" '
        f'style="display:inline-flex;align-items:center;gap:3px;font-size:11px;font-weight:600;'
        f'color:var(--muted);text-decoration:none;background:rgba(242,218,78,0.1);'
        f'border:1px solid rgba(242,218,78,0.3);border-radius:4px;padding:1px 6px;'
        f'margin-left:4px;vertical-align:middle;white-space:nowrap;" '
        f'title="Jump to this moment in the recording">&#9654; {label}</a>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Airtable API (optional)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_airtable_survey(record_id: str):
    key = os.environ.get("AIRTABLE_API_KEY", "").strip()
    if not key:
        print("  [WARN] AIRTABLE_API_KEY not set — skipping survey data")
        return None
    url = f"{AIRTABLE_BASE}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}/{record_id}"
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"})
    if not r.ok:
        print(f"  [WARN] Airtable returned HTTP {r.status_code} — skipping survey data")
        return None
    return r.json().get("fields", {})


AIRTABLE_TARGET_SCHOOLS_TABLE = "tbleaeYm3UEINl1oU"
AIRTABLE_CONTACTS_TABLE       = "tbljDWMCZLjSgrkKw"
AIRTABLE_FIELD_CHAMPION       = "fldndR3wgvRe3YhhL"   # Target Schools: Champion Potential
AIRTABLE_FIELD_ENTHUSIASM     = "fldK5ESh0vx5I6GZk"   # Target Schools: Enthusiasm Level
AIRTABLE_CONTACT_FIELD_CHAMP  = "fldRLccslcgEdiz37"   # Contacts: Champion Potential


def push_school_to_airtable(record_id: str, hub: dict, contact_ids: Optional[list] = None) -> None:
    """Push champion_potential and enthusiasm_score to the Target Schools record.
    If contact_ids is provided (same order as hub['advisors']), also push
    per-advisor champion_potential to each Contact record.
    """
    key = os.environ.get("AIRTABLE_API_KEY", "").strip()
    if not key:
        print("  [WARN] AIRTABLE_API_KEY not set — skipping Airtable push")
        return

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # ── School-level push ─────────────────────────────────────────────────────
    school_fields: dict = {}

    cp = hub.get("champion_potential", "").strip()
    if cp in ("Strong", "Moderate", "Low"):
        school_fields[AIRTABLE_FIELD_CHAMPION] = cp

    es_raw = hub.get("excitement_score", "")
    m = re.match(r"(\d+)", str(es_raw))
    if m:
        school_fields[AIRTABLE_FIELD_ENTHUSIASM] = int(m.group(1))

    if school_fields:
        url = f"{AIRTABLE_BASE}/{AIRTABLE_BASE_ID}/{AIRTABLE_TARGET_SCHOOLS_TABLE}/{record_id}"
        r = requests.patch(url, json={"fields": school_fields}, headers=headers)
        if r.ok:
            print(f"  ✓ Target Schools updated: champion={school_fields.get(AIRTABLE_FIELD_CHAMPION, '—')}  enthusiasm={school_fields.get(AIRTABLE_FIELD_ENTHUSIASM, '—')}")
        else:
            print(f"  [WARN] Target Schools push failed HTTP {r.status_code}: {r.text[:200]}")
    else:
        print("  [WARN] No valid fields to push to Airtable Target Schools")

    # ── Per-advisor push to Contacts ──────────────────────────────────────────
    if not contact_ids:
        return

    advisors = hub.get("advisors", [])
    for i, contact_id in enumerate(contact_ids):
        if not contact_id:
            continue
        advisor = advisors[i] if i < len(advisors) else {}
        advisor_cp = advisor.get("champion_potential", "").strip()
        if advisor_cp not in ("Strong", "Moderate", "Low"):
            print(f"  [SKIP] Advisor {i+1} ({advisor.get('name','?')}): no valid champion_potential")
            continue
        url = f"{AIRTABLE_BASE}/{AIRTABLE_BASE_ID}/{AIRTABLE_CONTACTS_TABLE}/{contact_id}"
        r = requests.patch(url, json={"fields": {AIRTABLE_CONTACT_FIELD_CHAMP: advisor_cp}}, headers=headers)
        if r.ok:
            print(f"  ✓ Contact {advisor.get('name','?')} ({contact_id}): champion_potential = {advisor_cp}")
        else:
            print(f"  [WARN] Contact push failed for {contact_id} HTTP {r.status_code}: {r.text[:200]}")


# ─────────────────────────────────────────────────────────────────────────────
# Claude prompts
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a product research analyst for NSLS (National Society of Leadership and Success). NSLS is building a new platform called Society — an AI-powered student engagement and career readiness platform. You generate structured campus meeting reports used internally to track feedback, identify product signals, and build a Product Council of early partners. Ground all output in what was actually said in the transcript. Do not speculate or invent details."""


def build_report_prompt(transcript: str, school: str, location: str, school_type: str, csr: str, tier: int, advisor_names: str = "") -> str:
    focus_line = f"\nFocus specifically on contributions from: {advisor_names}\nIgnore other schools' advisors unless directly relevant to {school}'s discussion." if advisor_names else ""
    return f"""Generate a structured HTML meeting report from this transcript.

School: {school}
Location: {location}
School Type: {school_type}
CSR: {csr}
Tier/Segment: {tier}{focus_line}

Return ONLY the inner HTML sections — no <html>, <head>, <body>, or <main> tags.
Each section must use: <section class="section" id="sN"> where N is 1-8.
Each section title must use: <h2 class="section-title">Section N — Title</h2>

---

Section 1 — School Snapshot
Overview: school type, culture, chapter status (new/established/semester), chapter type (standard/hybrid/online), advisors present, notable context. Render in <div class="card">.

Section 2 — Advisor Profiles
One <div class="advisor-card"> per advisor:
<div class="advisor-card">
  <h3>Name</h3>
  <p><strong>Role:</strong> ...</p>
  <p><strong>Background:</strong> ...</p>
  <p><strong>Motivations:</strong> ...</p>
  <p><strong>Communication Style:</strong> ...</p>
  <p><strong>Pilot Partner / Product Council Potential:</strong> ...</p>
</div>

Section 3 — Discovery Findings
Three <h3> subsections: "What They Want to Preserve", "What Isn't Working", "School Priorities".
Use <ul> lists under each.

Section 4 — Key Themes & Signals
3–5 themes in <div class="theme-card"><h3 class="theme-title">N. Title</h3><p>...</p></div>.

Section 5 — Society Reception
Include enthusiasm score as <div class="enthusiasm-score">X/10</div> (if given).
Then <h3> subsections: "What Landed Well", "What Raised Questions or Friction", "Surprises".

Section 6 — Feature-Level Feedback
Table: Feature | Signal | Notes
<table class="feature-table"><thead>...</thead><tbody>...</tbody></table>
Signal badge classes: badge-strong (strong), badge-positive (positive), badge-question (open question), badge-care (needs care).

Section 7 — Next Steps & Open Items
Action items as:
<ul class="action-items">
  <li>
    <div class="action-number">N</div>
    <div>Action text <span class="owner-tag">Owner Name</span></div>
  </li>
</ul>
Open questions as <ul class="open-questions"><li>...</li></ul>

Section 8 — Roadshow Metadata
<table class="metadata-table"><tbody> with rows for:
School, Location, School Type, Chapter Status, Chapter Type, Segment, Enthusiasm Score,
Pilot Partner Interest, Product Council Interest, Top Pain Points, Key Signal, CSR.

---

TRANSCRIPT:
{transcript}"""


def build_hub_prompt(transcript: str, school: str, location: str, school_type: str, csr: str, report_html: str, advisor_names: str = "") -> str:
    focus_line = f"\nFocus specifically on contributions from: {advisor_names}\nIgnore other schools' advisors unless directly relevant to {school}." if advisor_names else ""
    return f"""Analyze this meeting transcript and return structured JSON for the school hub page.

School: {school}
Location: {location}
Type: {school_type}{focus_line}

Return ONLY valid JSON matching this exact schema (no markdown, no explanation):

{{
  "excitement_score": "9/10",
  "excitement_advisor": "Advisor Name",
  "pilot_interest_value": "✅ Yes",
  "pilot_interest_detail": "who confirmed; who TBD",
  "product_council_value": "🤔 Unsure",
  "product_council_detail": "brief detail",
  "what_matters_most": "Top survey/meeting priority phrase",
  "what_matters_most_sub": "Source: Advisor Name",
  "school_about": [
    {{"icon": "🎭", "text": "Sentence about school culture or context.", "keywords": ["word1", "word2"]}}
  ],
  "chapter_status": [
    {{"icon": "🆕", "text": "Chapter status bullet.", "keywords": []}}
  ],
  "advisors": [
    {{
      "initials": "KG",
      "color": "navy",
      "name": "Full Name",
      "role": "Title / Role",
      "note": "1–2 sentence profile summary.",
      "champion_potential": "Strong"
    }}
  ],
  "whats_working": [
    {{
      "icon": "💌",
      "label": "Short feature label",
      "detail": "Why it landed or what reaction it got.",
      "keywords": ["word1", "word2", "phrase"]
    }}
  ],
  "whats_not_working": [
    {{
      "icon": "📧",
      "label": "Short pain point label",
      "detail": "Description of the problem.",
      "keywords": ["word1", "word2"]
    }}
  ],
  "champion_potential": "Strong",
  "key_signal_title": "Signal Title",
  "key_signal_body": "2–3 sentence description of the most actionable or distinctive signal.",
  "key_signal_keywords": ["keyword1", "keyword2"],
  "action_items": [
    {{
      "text": "Action item description.",
      "owners": ["Owner Name"],
      "keywords": ["keyword1"]
    }}
  ]
}}

For "keywords" arrays: provide 3–6 words or short phrases that would appear in the transcript near the relevant moment. These are used for timestamp matching.
For "color" on advisors: use "navy" for the primary advisor, "gold" for secondary.
For pilot_interest_value / product_council_value: use emoji + word (e.g. "✅ Yes", "❌ No", "🤔 Unsure", "❓ TBD").
For "champion_potential" (both top-level and per-advisor): use exactly "Strong", "Moderate", or "Low". Strong = advisor proactively volunteered to advocate, drive adoption, or involve others; Moderate = expressed interest but conditional or passive; Low = evaluating only, no advocacy signals. The top-level champion_potential should reflect the strongest individual advisor at the school.
Base all values on what was actually said in the transcript.

MEETING REPORT (for context):
{report_html[:3000]}

TRANSCRIPT:
{transcript}"""


def call_claude(system: str, user: str, max_tokens: int = 8192) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        sys.exit("Error: ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Airtable survey → hub section HTML
# ─────────────────────────────────────────────────────────────────────────────

def render_survey_section(fields: dict, at_id: str, name: str) -> str:
    """Render the Survey Highlights section from Airtable fields."""
    if not fields:
        return ""

    respondent = fields.get("Respondent Name") or fields.get("Name") or "Survey Respondent"
    survey_href = f"../../executive-summary.html?id={at_id}"

    # Try to extract priority rankings
    rank_items = []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i in range(1, 6):
        val = fields.get(f"Priority {i}") or fields.get(f"Rank {i}") or fields.get(f"priority_{i}")
        if val:
            rank_items.append((medals[i - 1], str(val)))

    rank_html = ""
    if rank_items:
        rank_html = "<ul class=\"finding-list\">"
        for icon, text in rank_items:
            rank_html += f"<li><span class=\"icon\">{icon}</span><span>{text}</span></li>"
        rank_html += "</ul>"
    else:
        rank_html = "<p style=\"color:var(--muted);font-style:italic;\">Survey rankings not yet available.</p>"

    # Key quote
    quote_text = (
        fields.get("Key Concern")
        or fields.get("Missing Capability")
        or fields.get("Open Response")
        or ""
    )
    quote_html = ""
    if quote_text:
        quote_html = f"""<div class="quote" style="margin-top:16px;">
  &ldquo;{quote_text}&rdquo;
  <cite>&mdash; {respondent}, Survey</cite>
</div>"""

    return f"""
  <!-- ─── Survey Highlights ─────────────────────────────────── -->
  <h2 class="section-header">
    Survey Highlights &mdash; {respondent}
    <a href="{survey_href}" target="_blank">Full Survey Results &rsaquo;</a>
  </h2>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">What Matters Most?</div>
      {rank_html}
    </div>
    <div class="card">
      <div class="card-title">Key Survey Signals</div>
      {quote_html or '<p style="color:var(--muted);font-style:italic;">No open responses recorded.</p>'}
    </div>
  </div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Hub HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_hub_html(s: dict, hub: dict, airtable_html: str, has_local_survey: bool = False) -> str:
    name        = s["name"]
    location    = s["location"]
    school_type = s["school_type"]
    fathom_url  = s["fathom_url"]
    duration    = s["duration"]
    date        = s["date"]
    num         = s["meeting_num"]
    slug        = s["slug"]
    at_id       = s.get("airtable_id", "")

    report_href = f"meetings/meeting-{num}-{date}.html"
    survey_href = "survey.html"
    survey_hide = ""

    # ── Stat tiles ────────────────────────────────────────────────────────────
    def _stat(cls, label, value, sub):
        return f"""<div class="stat-tile {cls}">
      <div class="label">{label}</div>
      <div class="value" style="font-size:{'30px' if len(str(value)) < 6 else '18px'};padding-top:{'0' if len(str(value)) < 6 else '6px'};line-height:1.2;">{value}</div>
      <div class="sub">{sub}</div>
    </div>"""

    stats_html = (
        _stat("highlight", "Excitement Score",
              hub.get("excitement_score", "?/10"),
              hub.get("excitement_advisor", "")) +
        _stat("green", "Pilot Partner Interest",
              hub.get("pilot_interest_value", "❓ TBD"),
              hub.get("pilot_interest_detail", "")) +
        _stat("blue", "Product Council",
              hub.get("product_council_value", "❓ TBD"),
              hub.get("product_council_detail", "")) +
        _stat("red", "What Matters Most?",
              hub.get("what_matters_most", "—"),
              hub.get("what_matters_most_sub", "")) +
        _stat("purple", "Champion Potential",
              hub.get("champion_potential", "—"),
              "Likelihood to drive Society adoption")
    )

    # ── School & chapter snapshot ─────────────────────────────────────────────
    def _fi_items(lst):
        return "".join(
            f'<li><span class="icon">{item.get("icon","•")}</span><span>'
            f'{item.get("text","")}'
            + (f' {item.get("_ts_link","")}' if item.get("_ts_link") else "")
            + f'</span></li>'
            for item in lst
        )

    about_html    = _fi_items(hub.get("school_about", []))
    chapter_html  = _fi_items(hub.get("chapter_status", []))

    # ── Advisors ──────────────────────────────────────────────────────────────
    def _advisor(a):
        return f"""<div class="card">
      <div class="attendee" style="padding-top:0;">
        <div class="avatar {a.get('color','navy')}">{a.get('initials','?')}</div>
        <div class="attendee-info">
          <div class="name">{a.get('name','')}</div>
          <div class="role">{a.get('role','')}</div>
          <div class="note">{a.get('note','')}</div>
        </div>
      </div>
    </div>"""

    advisors_html = "\n".join(_advisor(a) for a in hub.get("advisors", []))

    # ── Meeting highlights ────────────────────────────────────────────────────
    def _highlight(item):
        ts = f' {item["_ts_link"]}' if item.get("_ts_link") else ""
        return (
            f'<li><span class="icon">{item.get("icon","•")}</span>'
            f'<span><strong>{item.get("label","")}</strong>{ts}'
            f' &mdash; {item.get("detail","")}</span></li>'
        )

    working_html     = "".join(_highlight(i) for i in hub.get("whats_working", []))
    not_working_html = "".join(_highlight(i) for i in hub.get("whats_not_working", []))

    # ── Key signal ────────────────────────────────────────────────────────────
    ks_title = hub.get("key_signal_title", "Key Signal")
    ks_body  = hub.get("key_signal_body", "")
    ks_ts    = hub.get("_key_signal_ts_link", "")

    # ── Action items ──────────────────────────────────────────────────────────
    def _action(idx, item):
        owners = "".join(f'<span class="owner-tag">{o}</span>' for o in item.get("owners", []))
        ts = f' {item["_ts_link"]}' if item.get("_ts_link") else ""
        return f"""<li>
        <input type="checkbox">
        <div class="action-number">{idx}</div>
        <div>{item.get("text","")}{ts} {owners}</div>
      </li>"""

    actions_html = "\n".join(_action(i + 1, a) for i, a in enumerate(hub.get("action_items", [])))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NSLS Society Roadshow — {name}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  <style>
    :root {{
      --navy:#1A3550; --gold:#F2DA4E; --light:#F2E9E2; --border:rgba(30,20,20,0.1);
      --text:#1E1414; --muted:#6B6357; --card:#E8DDD5; --yellow:#F2DA4E;
      --white:#FFFDF8; --black:#1E1414; --blue:#4a4faa; --purple:#4a4faa;
    }}
    *{{box-sizing:border-box;margin:0;padding:0;}}
    a{{color:#1A3550;text-decoration:none;}} a:hover{{color:#C96058;}}
    body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#F2E9E2;color:var(--black);line-height:1.6;}}
    h1,h2{{font-family:'Cigars',Georgia,'Times New Roman',serif;}}
    .header{{background:#F2E9E2;border-bottom:2px solid #1A3550;padding:48px 40px 9px;}}
    .header-meta{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;}}
    .badge{{transition:color .2s;background:transparent;border:1px solid rgba(36,59,82,0.35);border-radius:20px;padding:4px 14px;font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;color:#243B52;}}
    a.badge:hover{{color:#C96058;}}
    .header h1{{font-size:32px;font-weight:700;margin-bottom:6px;color:#1A3550;}}
    .header h2{{font-size:18px;font-weight:400;color:#6B6357;margin-bottom:20px;}}
    .recording-link{{display:inline-flex;align-items:center;gap:8px;background:#C96058;color:#FFFDF8;text-decoration:none;padding:10px 22px;border-radius:8px;font-weight:600;font-size:14px;transition:opacity .2s;}}
    .recording-link:hover{{opacity:0.88;color:#FFFDF8;}}
    .container{{max-width:1200px;margin:0 auto;padding:40px 32px;}}
    .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:24px;}}
    @media(max-width:900px){{.grid-2{{grid-template-columns:1fr;}}}}
    .card{{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:28px;}}
    .card-title{{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:16px;display:flex;align-items:center;gap:8px;}}
    .card-title::after{{content:'';flex:1;height:1px;background:var(--border);}}
    .stat-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:32px;}}
    @media(max-width:900px){{.stat-grid{{grid-template-columns:1fr 1fr;}}}}
    .stat-tile{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px 24px;}}
    .stat-tile .label{{font-size:11px;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);font-weight:600;margin-bottom:6px;}}
    .stat-tile .value{{font-weight:700;color:var(--navy);line-height:1;font-family:'Cigars',Georgia,serif;}}
    .stat-tile .sub{{font-size:12px;color:var(--muted);margin-top:4px;}}
    .stat-tile.highlight{{border-left:4px solid #C96058;}}
    .stat-tile.green{{border-left:4px solid #3a8a40;}}
    .stat-tile.red{{border-left:4px solid #C96058;}}
    .stat-tile.blue{{border-left:4px solid var(--navy);}}
    .section-header{{font-size:20px;font-weight:700;color:var(--navy);margin:40px 0 20px;padding-bottom:10px;border-bottom:2px solid var(--navy);font-family:'Cigars',Georgia,serif;display:flex;align-items:baseline;justify-content:space-between;gap:16px;}}
    .section-header a{{font-size:13px;font-weight:600;color:var(--muted);text-decoration:none;white-space:nowrap;}}
    .section-header a:hover{{color:var(--navy);text-decoration:underline;}}
    .attendee{{display:flex;align-items:flex-start;gap:14px;padding:12px 0;border-bottom:1px solid var(--border);}}
    .attendee:last-child{{border-bottom:none;padding-bottom:0;}}
    .avatar{{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;flex-shrink:0;color:#fff;}}
    .avatar.navy{{background:#1A3550;}} .avatar.gold{{background:#C8A000;}} .avatar.muted{{background:var(--muted);}}
    .attendee-info .name{{font-weight:600;font-size:15px;}}
    .attendee-info .role{{font-size:13px;color:var(--muted);margin-top:2px;}}
    .attendee-info .note{{font-size:12px;color:var(--text);margin-top:4px;font-style:italic;}}
    .finding-list{{list-style:none;}}
    .finding-list li{{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--border);font-size:14px;line-height:1.5;align-items:flex-start;}}
    .finding-list li:last-child{{border-bottom:none;}}
    .finding-list .icon{{font-size:16px;flex-shrink:0;margin-top:1px;}}
    .quote{{border-left:4px solid #1A3550;background:rgba(26,53,80,0.06);border-radius:0 8px 8px 0;padding:14px 18px;margin:12px 0;font-style:italic;color:var(--text);font-size:14px;}}
    .quote cite{{display:block;font-style:normal;font-size:12px;color:var(--muted);margin-top:6px;font-weight:600;}}
    .signal-chip{{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:600;background:#E2E4F3;color:#4a4faa;border:1px solid #C8CBE8;}}
    .signal-chip.top{{background:rgba(201,96,88,0.12);color:#C96058;border-color:rgba(201,96,88,0.3);}}
    .callout{{background:rgba(26,53,80,0.06);border:1px solid rgba(26,53,80,0.2);border-left:4px solid #1A3550;border-radius:8px;padding:16px 20px;font-size:14px;line-height:1.65;margin-top:20px;}}
    .callout strong{{color:#1A3550;}}
    .action-list{{list-style:none;}}
    .action-list li{{display:flex;gap:12px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--border);font-size:14px;}}
    .action-list li:last-child{{border-bottom:none;}}
    .action-list input[type=checkbox]{{margin-top:5px;flex-shrink:0;cursor:pointer;width:15px;height:15px;}}
    .action-number{{background:#C96058;color:#FFFDF8;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;}}
    .owner-tag{{display:inline-block;background:#E2E4F3;color:#4a4faa;border:1px solid #C8CBE8;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;margin-left:6px;}}
    .footer{{text-align:center;color:#6B6357;font-size:12px;padding:40px 32px;border-top:1px solid rgba(30,20,20,0.1);margin-top:20px;background:#F2E9E2;}}
  </style>
</head>
<body>

<div class="header">
  <div style="max-width:1200px;margin:0 auto;padding:0 8px;">
    <div class="header-meta">
      <a href="../../index.html" class="badge" style="text-decoration:none;">NSLS Society Roadshow</a>
      <span class="badge" id="last-updated-badge">Latest Update: {fmt_date(date)}</span>
    </div>
    <h1>{name}</h1>
    <h2>{location} &nbsp;&middot;&nbsp; {school_type}</h2>
    <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">
      <a class="recording-link" href="../../index.html" style="background:#243B52;border:1px solid #243B52;color:#FFFDF8;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        Roadshow Home
      </a>
      <a class="recording-link" href="{fathom_url}" target="_blank">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Watch Fathom Recording &mdash; {duration}
      </a>
      <a class="recording-link" href="{report_href}" style="background:#243B52;border:1px solid #243B52;color:#FFFDF8;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Discovery &amp; Demo Meeting &mdash; Report
      </a>
      <a class="recording-link" href="{survey_href}"{survey_hide} style="background:#243B52;border:1px solid #243B52;color:#FFFDF8;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        Survey Results
      </a>
    </div>
  </div>
</div>

<div class="container">

  <div class="stat-grid">{stats_html}</div>

  <h2 class="section-header">School &amp; Chapter Snapshot</h2>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">About {name}</div>
      <ul class="finding-list">{about_html}</ul>
    </div>
    <div class="card">
      <div class="card-title">Chapter Status</div>
      <ul class="finding-list">{chapter_html}</ul>
    </div>
  </div>

  <h2 class="section-header">Advisors
    <a href="{report_href}#advisor-profiles">Full Advisor Profiles in Meeting Report &rsaquo;</a>
  </h2>
  <div class="grid-2">{advisors_html}</div>

  <h2 class="section-header">Meeting Highlights
    <a href="{report_href}">Full Meeting Report &rsaquo;</a>
  </h2>
  <div class="grid-2" style="margin-bottom:20px;">
    <div class="card">
      <div class="card-title">&#x2705; What&#x27;s Working / What Landed</div>
      <ul class="finding-list">{working_html}</ul>
    </div>
    <div class="card">
      <div class="card-title">&#x274C; What Isn&#x27;t Working</div>
      <ul class="finding-list">{not_working_html}</ul>
    </div>
  </div>

  <div class="callout">
    <strong>&#x26A0;&#xFE0F; Key Signal{ks_ts} &mdash; {ks_title}:</strong> {ks_body}
  </div>

{airtable_html}

  <h2 class="section-header">Action Items</h2>
  <div class="card">
    <ul class="action-list">{actions_html}</ul>
  </div>

</div>

<div class="footer">
  NSLS Society Platform Roadshow &nbsp;&middot;&nbsp; {name} &nbsp;&middot;&nbsp; {fmt_date(date)}<br>
  Source: <a href="{fathom_url}" target="_blank">Fathom Recording</a> &nbsp;&middot;&nbsp; Generated for NSLS Product &amp; Development Teams
</div>

<script>
document.getElementById('last-updated-badge').textContent =
  'Latest Update: ' + new Date().toLocaleDateString('en-US', {{ month: 'long', day: 'numeric', year: 'numeric' }});
</script>
<script src="/auth-chip.js"></script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Meeting report HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

REPORT_CSS = """
  :root {
    --navy:#1A3550; --gold:#F2DA4E; --red:#C96058; --bg:#F2E9E2; --card:#E8DDD5;
    --text:#1E1414; --muted:#6B6357; --border:rgba(30,20,20,0.1);
    --yellow:#F2DA4E; --white:#FFFDF8; --black:#1E1414; --purple:#4a4faa;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  a{color:#1A3550;} a:hover{color:#C96058;}
  body{font-family:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#F2E9E2;color:var(--black);line-height:1.6;}
  h1,h2{font-family:'Cigars',Georgia,'Times New Roman',serif;}
  .page-header{background:#F2E9E2;border-bottom:2px solid #1A3550;padding:2rem 0 0.56rem;}
  .page-header .header-inner{max-width:1180px;margin:0 auto;padding:0 1.5rem;}
  .page-header .header-pills{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;}
  .page-header .header-pill{transition:color .2s;background:transparent;border:1px solid rgba(36,59,82,0.35);border-radius:20px;padding:4px 14px;font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;color:#243B52;}
  .page-header a.header-pill:hover{color:#C96058;}
  .page-header .header-buttons{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px;}
  .page-header .header-btn{display:inline-flex;align-items:center;gap:8px;background:#243B52;border:1px solid #243B52;color:#FFFDF8;border-radius:8px;padding:8px 18px;font-weight:600;font-size:14px;text-decoration:none;transition:background 0.15s;}
  .page-header .header-btn:hover{background:#1a2d3e;color:#FFFDF8;}
  .page-header h1{font-size:1.75rem;font-weight:700;color:#1A3550;margin-bottom:0.5rem;}
  .page-header .recording-link{display:inline-flex;align-items:center;gap:0.4rem;padding:0.4rem 0.85rem;background:#C96058;border:1px solid #C96058;border-radius:6px;color:#FFFDF8;font-size:0.8rem;font-weight:600;text-decoration:none;transition:opacity 0.15s;}
  .page-header .recording-link:hover{opacity:0.88;color:#FFFDF8;}
  main{max-width:1180px;margin:0 auto;padding:2rem 1.5rem 4rem;display:flex;align-items:flex-start;gap:2rem;}
  .content{flex:1;min-width:0;}
  .toc-sidebar{width:185px;flex-shrink:0;position:sticky;top:1.5rem;}
  .toc-nav{background:var(--card);border-radius:8px;border:1px solid var(--border);padding:0.9rem 1rem;}
  .toc-nav .toc-heading{font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);margin-bottom:0.65rem;padding-bottom:0.5rem;border-bottom:1px solid var(--border);}
  .toc-nav a{display:block;font-size:0.78rem;color:var(--text);text-decoration:none;padding:0.28rem 0.5rem;border-radius:4px;line-height:1.4;margin-bottom:0.05rem;}
  .toc-nav a:hover{background:rgba(30,20,20,0.05);color:var(--navy);}
  .section-accordion>summary{list-style:none;cursor:pointer;user-select:none;display:flex;align-items:center;justify-content:space-between;font-size:20px;font-weight:700;color:var(--navy);padding-bottom:10px;border-bottom:2px solid var(--navy);margin-bottom:1rem;font-family:'Cigars',Georgia,serif;}
  .section-accordion>summary::-webkit-details-marker{display:none;}
  .section-accordion>summary::after{content:"▸ Show";font-size:0.78rem;font-weight:600;color:var(--muted);flex-shrink:0;margin-left:0.75rem;}
  details[open].section-accordion>summary::after{content:"▾ Hide";}
  .section{margin-bottom:2.5rem;}
  .section-title{font-size:20px;font-weight:700;color:var(--navy);padding-bottom:10px;border-bottom:2px solid var(--navy);margin-bottom:1rem;font-family:'Cigars',Georgia,serif;}
  .card{background:var(--card);border-radius:8px;border:1px solid var(--border);padding:1.25rem 1.5rem;}
  .card h3{font-size:0.95rem;font-weight:700;color:var(--navy);margin-bottom:0.6rem;margin-top:1rem;}
  .card h3:first-child{margin-top:0;}
  .card ul{padding-left:1.25rem;}
  .card li{margin-bottom:0.3rem;font-size:0.93rem;}
  .card p{font-size:0.93rem;}
  .theme-card{background:var(--card);border-radius:8px;border:1px solid var(--border);padding:1rem 1.25rem;margin-bottom:0.75rem;border-left:3px solid #1A3550;}
  .theme-card .theme-title{font-size:0.95rem;font-weight:700;color:var(--navy);margin-bottom:0.4rem;}
  .theme-card p{font-size:0.9rem;color:var(--text);}
  .enthusiasm-score{display:inline-flex;align-items:center;justify-content:center;width:64px;height:64px;border-radius:50%;background:#C96058;color:#FFFDF8;font-size:1.3rem;font-weight:800;margin-bottom:1rem;font-family:'Cigars',Georgia,serif;}
  .feature-table{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.07);font-size:0.88rem;}
  .feature-table thead tr{background:#1A3550;color:#FFFDF8;}
  .feature-table th{padding:0.7rem 1rem;text-align:left;font-weight:600;font-size:0.8rem;letter-spacing:0.04em;}
  .feature-table td{padding:0.65rem 1rem;border-bottom:1px solid var(--border);vertical-align:top;}
  .feature-table tr:last-child td{border-bottom:none;}
  .feature-table tr:nth-child(even){background:rgba(30,20,20,0.03);}
  .badge{display:inline-flex;align-items:center;gap:0.25rem;padding:0.2rem 0.6rem;border-radius:999px;font-size:0.75rem;font-weight:600;white-space:nowrap;}
  .badge-strong{background:rgba(60,140,30,0.1);color:#2a7a10;}
  .badge-positive{background:#E2E4F3;color:#4a4faa;}
  .badge-question{background:rgba(180,130,0,0.1);color:#7a5500;}
  .badge-care{background:rgba(201,96,88,0.12);color:#C96058;}
  .advisor-card{background:var(--card);border-radius:8px;border:1px solid var(--border);padding:1.1rem 1.4rem;margin-bottom:0.75rem;}
  .advisor-card h3{font-size:1rem;font-weight:700;color:var(--navy);margin-bottom:0.4rem;}
  .advisor-card p{font-size:0.9rem;color:var(--text);}
  .action-items{list-style:none;padding:0;}
  .action-items li{display:flex;gap:12px;align-items:flex-start;padding:12px 4px;border-bottom:1px solid var(--border);font-size:0.9rem;}
  .action-items li:last-child{border-bottom:none;}
  .action-number{background:#C96058;color:#FFFDF8;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;margin-top:1px;}
  .owner-tag{display:inline-block;background:#E2E4F3;color:#4a4faa;border:1px solid #C8CBE8;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;margin-left:6px;white-space:nowrap;}
  .open-questions{list-style:none;padding:0;}
  .open-questions li{padding:0.5rem 0;border-bottom:1px solid var(--border);font-size:0.9rem;}
  .open-questions li:last-child{border-bottom:none;}
  .metadata-table{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.07);font-size:0.88rem;}
  .metadata-table th{padding:0.6rem 1rem;text-align:left;font-weight:600;color:var(--muted);font-size:0.8rem;width:38%;background:rgba(30,20,20,0.04);border-bottom:1px solid var(--border);vertical-align:top;}
  .metadata-table td{padding:0.6rem 1rem;border-bottom:1px solid var(--border);vertical-align:top;}
  .metadata-table tr:last-child th,.metadata-table tr:last-child td{border-bottom:none;}
  .section>h3{font-size:0.9rem;font-weight:700;color:var(--navy);margin:1.25rem 0 0.5rem;padding:0.4rem 0.75rem;background:rgba(30,20,20,0.04);border-radius:4px;}
  .section>h3:first-of-type{margin-top:0;}
  .section>ul{padding-left:1.5rem;margin-bottom:1rem;background:rgba(30,20,20,0.02);border-radius:0 0 6px 6px;border:1px solid var(--border);border-top:none;padding-top:0.75rem;padding-right:1rem;padding-bottom:0.75rem;}
  .section>ul li{margin-bottom:0.5rem;font-size:0.9rem;line-height:1.65;}
  .section>p{font-size:0.9rem;line-height:1.65;margin-bottom:1rem;background:rgba(30,20,20,0.02);border:1px solid var(--border);border-radius:6px;padding:0.75rem 1rem;}
  footer{text-align:center;font-size:0.75rem;color:#6B6357;padding:2rem;border-top:1px solid rgba(30,20,20,0.1);background:#F2E9E2;margin-top:3rem;}
"""


def render_report_html(s: dict, sections_html: str, has_local_survey: bool = False) -> str:
    name        = s["name"]
    location    = s["location"]
    school_type = s["school_type"]
    fathom_url  = s["fathom_url"]
    date        = s["date"]
    slug        = s["slug"]
    num         = s["meeting_num"]
    at_id       = s.get("airtable_id", "")

    hub_href    = "../index.html"
    survey_href = "../survey.html"
    survey_hide = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name} — Discovery &amp; Demo Meeting | NSLS Roadshow</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  <style>{REPORT_CSS}</style>
</head>
<body>

<header class="page-header">
  <div class="header-inner">
    <div class="header-pills">
      <a href="../../../index.html" class="header-pill" style="text-decoration:none;">NSLS Society Roadshow</a>
      <span class="header-pill">{fmt_date(date)}</span>
    </div>
    <h1>{name} &mdash; Discovery &amp; Demo Meeting</h1>
    <div class="header-buttons">
      <a class="header-btn" href="{hub_href}">&larr; {name} Hub</a>
      <a class="header-btn" href="{survey_href}"{survey_hide}>Survey Results</a>
      <a class="recording-link" href="{fathom_url}" target="_blank">&#9654; Fathom Recording</a>
    </div>
  </div>
</header>

<main>
  <aside class="toc-sidebar">
    <nav class="toc-nav">
      <div class="toc-heading">Contents</div>
      <a href="#s1">1 &mdash; School Snapshot</a>
      <a href="#s2">2 &mdash; Advisor Profiles</a>
      <a href="#s3">3 &mdash; Discovery Findings</a>
      <a href="#s4">4 &mdash; Key Themes &amp; Signals</a>
      <a href="#s5">5 &mdash; Society Reception</a>
      <a href="#s6">6 &mdash; Feature-Level Feedback</a>
      <a href="#s7">7 &mdash; Next Steps &amp; Open Items</a>
      <a href="#s8">8 &mdash; Roadshow Metadata</a>
    </nav>
  </aside>
  <div class="content">
{sections_html}
  </div>
</main>

<footer>
  NSLS Society Roadshow &nbsp;&middot;&nbsp; {name} &nbsp;&middot;&nbsp; Discovery &amp; Demo Meeting &nbsp;&middot;&nbsp; {fmt_date(date)}
</footer>

<script src="/auth-chip.js"></script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Roadshow index update
# ─────────────────────────────────────────────────────────────────────────────

def _hub_card_icon(val: str) -> str:
    """Extract leading emoji from hub values like '✅ Yes' → '✅', '🤔 Unsure' → '🤔'."""
    parts = str(val).strip().split()
    return parts[0] if parts else "❓"


def school_card_html(s: dict, hub: dict = None) -> str:
    name           = s["name"]
    location       = s["location"]
    school_type    = s["school_type"]
    date           = s["date"]
    advisors       = s.get("advisors", 1)
    survey_resp    = s.get("survey_respondents", 1 if s.get("airtable_id") else 0)
    chapter_status = s.get("chapter_status", "TBD")
    chapter_type   = s.get("chapter_type", "TBD")
    slug           = s.get("slug", to_slug(name))

    if hub:
        excitement  = hub.get("excitement_score", "?/10")
        pilot_icon  = _hub_card_icon(hub.get("pilot_interest_value", "❓ TBD"))
        council_icon = _hub_card_icon(hub.get("product_council_value", "❓ TBD"))
        what_matters = hub.get("what_matters_most", "")
        ks_body      = hub.get("key_signal_body", "")

        signal_parts = []
        if what_matters:
            signal_parts.append(f'<div><strong>Top priority:</strong> {what_matters}</div>')
        if ks_body:
            short = ks_body[:160].rstrip()
            signal_parts.append(
                f'<div style="margin-top:5px;"><strong>Key signal:</strong> {short}</div>'
            )
        signal_html = "\n        ".join(signal_parts) or "<div><strong>Discovery completed</strong></div>"

        return f"""
    <!-- \u2550\u2550\u2550 {name} \u2014 {fmt_date(date)} \u2550\u2550\u2550 -->
    <a class="school-card" href="schools/{slug}/index.html" data-advisors="{advisors}" data-survey-respondents="{survey_resp}" data-school-type="{school_type}" data-chapter-status="{chapter_status}" data-chapter-type="{chapter_type}">
      <div class="school-card-header">
        <div class="school-card-meta">
          <span class="status-chip completed">Discovery Completed</span>
          <span class="meeting-date">{fmt_date(date)}</span>
        </div>
        <h3>{name}</h3>
        <div class="school-sub">{location} &nbsp;&middot;&nbsp; {school_type}</div>
      </div>
      <div class="school-stats">
        <div class="school-stat"><div class="stat-val">{excitement}</div><div class="stat-lbl">Excitement</div></div>
        <div class="school-stat"><div class="stat-val">{pilot_icon}</div><div class="stat-lbl">Pilot Partner</div></div>
        <div class="school-stat"><div class="stat-val">{council_icon}</div><div class="stat-lbl">Prod. Council</div></div>
      </div>
      <div class="school-signal">
        {signal_html}
      </div>
    </a>
"""
    else:
        return f"""
    <!-- \u2550\u2550\u2550 {name} \u2550\u2550\u2550 -->
    <a class="school-card" href="schools/{slug}/index.html" data-advisors="{advisors}" data-survey-respondents="{survey_resp}" data-school-type="{school_type}" data-chapter-status="{chapter_status}" data-chapter-type="{chapter_type}">
      <div class="school-card-header">
        <div class="school-card-meta">
          <span class="status-chip scheduled">Scheduled</span>
          <span class="meeting-date">{fmt_date(date)}</span>
        </div>
        <h3>{name}</h3>
        <div class="school-sub">{location} &nbsp;&middot;&nbsp; {school_type}</div>
      </div>
      <div class="school-stats">
        <div class="school-stat"><div class="stat-val">&mdash;</div><div class="stat-lbl">Excitement</div></div>
        <div class="school-stat"><div class="stat-val">&#x2753;</div><div class="stat-lbl">Pilot Partner</div></div>
        <div class="school-stat"><div class="stat-val">&#x2753;</div><div class="stat-lbl">Prod. Council</div></div>
      </div>
      <div class="school-signal">
        <div><strong>Meeting scheduled</strong></div>
      </div>
    </a>
"""


def _sort_school_cards(html: str) -> str:
    """Re-order school cards inside .school-grid by meeting date, newest first."""
    grid_start = html.find('<div class="school-grid">')
    marker     = "<!--\n      Add additional school cards here"
    grid_end   = html.find(marker)
    if grid_start == -1 or grid_end == -1:
        return html

    before = html[:grid_start + len('<div class="school-grid">')]
    cards_block = html[grid_start + len('<div class="school-grid">'):grid_end]
    after  = html[grid_end:]

    # Split into individual card blocks (each starts with a <!-- ═══ ... --> comment)
    card_pat = re.compile(r'(\s*<!--\s*\u2550+[^\n]*\u2550+\s*-->\s*<a class="school-card".*?</a>\s*)', re.DOTALL)
    card_blocks = card_pat.findall(cards_block)
    non_card_prefix = card_pat.sub("", cards_block)

    def _card_date(block: str) -> datetime:
        m = re.search(r'class="meeting-date">([^<]+)<', block)
        if m:
            try:
                return datetime.strptime(m.group(1).strip(), "%B %-d, %Y")
            except ValueError:
                pass
        return datetime.min

    card_blocks.sort(key=_card_date, reverse=True)
    return before + non_card_prefix + "".join(card_blocks) + after


def update_index(s: dict, hub: dict = None) -> None:
    if not INDEX_FILE.exists():
        print(f"  [WARN] Index not found: {INDEX_FILE}")
        return
    html = INDEX_FILE.read_text(encoding="utf-8")
    slug = s["slug"]
    new_card = school_card_html(s, hub)

    if f"schools/{slug}/" in html:
        # Upgrade a Scheduled placeholder to a completed card when hub data is available
        if hub:
            placeholder_pat = re.compile(
                r'\s*<!--\s*\u2550+\s*' + re.escape(s["name"]) + r'[^\n]*\u2550+\s*-->\s*'
                r'<a class="school-card"[^>]*>.*?</a>',
                re.DOTALL,
            )
            updated = placeholder_pat.sub(new_card.rstrip(), html, count=1)
            if updated == html:
                print(f"  [SKIP] {s['name']} already in index (could not locate card for upgrade)")
                return
            html = updated
            print(f"  [OK]  Upgraded {s['name']} card to completed")
        else:
            print(f"  [SKIP] {s['name']} already in index")
            return
    else:
        marker = "<!--\n      Add additional school cards here"
        if marker not in html:
            print("  [WARN] Could not find insertion marker — print card manually:")
            print(new_card)
            return
        html = html.replace(marker, new_card + "\n    " + marker, 1)
        # Bump data-total-invited
        m = re.search(r'(data-total-invited=")(\d+)(")', html)
        if m:
            html = html[:m.start()] + f'{m.group(1)}{int(m.group(2))+1}{m.group(3)}' + html[m.end():]
        print(f"  [OK]  Added {s['name']} card to {INDEX_FILE.name}")

    html = _sort_school_cards(html)
    INDEX_FILE.write_text(html, encoding="utf-8")


def update_index_editorial(s: dict, hub: dict) -> None:
    """Use Claude to update Key Findings, Heatmap, and Quote Rail for a new school."""
    if not INDEX_FILE.exists():
        return
    html = INDEX_FILE.read_text(encoding="utf-8")

    # Extract sections
    def _extract(start_comment: str, end_comment: str) -> str:
        a = html.find(start_comment)
        b = html.find(end_comment, a)
        return html[a:b + len(end_comment)] if a != -1 and b != -1 else ""

    findings_section = _extract("<!-- Key Findings Tab -->", "</div><!-- /tab-findings -->")
    heatmap_section  = _extract("<!-- ── Feature Demand Heatmap", "</div><!-- /intel-two-col -->")
    quotes_section   = _extract("<!-- Advisor Voices -->", "</div>\n\n    </div><!-- /intel-two-col -->")

    # Build compact hub summary for the prompt
    hub_summary = json.dumps({
        "name":              s["name"],
        "location":          s["location"],
        "school_type":       s["school_type"],
        "date":              s["date"],
        "excitement_score":  hub.get("excitement_score"),
        "pilot_interest":    hub.get("pilot_interest_value"),
        "product_council":   hub.get("product_council_value"),
        "what_matters_most": hub.get("what_matters_most"),
        "key_signal_title":  hub.get("key_signal_title"),
        "key_signal_body":   hub.get("key_signal_body"),
        "whats_working":     [i.get("label") for i in hub.get("whats_working", [])],
        "whats_not_working": [i.get("label") for i in hub.get("whats_not_working", [])],
        "advisors":          [a.get("name") for a in hub.get("advisors", [])],
    }, indent=2)

    prompt = f"""You are updating a static HTML roadshow report with data from a new school visit.

NEW SCHOOL DATA:
{hub_summary}

CURRENT FINDINGS SECTION (HTML):
{findings_section[:4000]}

CURRENT HEATMAP SECTION (HTML):
{heatmap_section[:3000]}

Return a JSON object with exactly these keys:
{{
  "findings_updates": [
    {{
      "type": "add_school_chip",
      "finding_headline_fragment": "exact fragment of the headline to identify the finding",
      "chip_html": "<span class=\\"exec-school-chip\\">School Name — score</span>"
    }},
    {{
      "type": "update_headline",
      "old_headline": "exact current headline text",
      "new_headline": "updated headline text"
    }},
    {{
      "type": "update_body",
      "finding_headline_fragment": "exact fragment",
      "old_body_fragment": "exact short fragment to replace (30-60 chars)",
      "new_body_fragment": "replacement text"
    }}
  ],
  "heatmap_new_column": {{
    "abbrev": "short column header (≤6 chars)",
    "full_name": "{s['name']}",
    "rows": [
      {{"feature": "Career Clarity Track", "filled": false}},
      {{"feature": "Outcomes & Reporting", "filled": false}},
      {{"feature": "SNT Automation", "filled": false}},
      {{"feature": "Campus System Integration", "filled": false}},
      {{"feature": "Mobile-First Platform", "filled": false}},
      {{"feature": "Alumni Mentor Matching", "filled": false}},
      {{"feature": "Personality Assessments", "filled": false}},
      {{"feature": "AI Coach & Nudges", "filled": false}}
    ]
  }},
  "new_quote": {{
    "text": "verbatim or close paraphrase of an advisor quote (or null if none stands out)",
    "attribution": "First Last, Title · School Name"
  }}
}}

Base heatmap dots strictly on what was explicitly raised in the meeting — err toward empty.
Only suggest finding updates where the new school clearly strengthens or extends an existing finding.
Return only valid JSON, no markdown fences."""

    print("  Calling Claude for editorial updates...")
    raw = call_claude(SYSTEM_PROMPT, prompt, max_tokens=2048)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        edits = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] Could not parse editorial JSON: {e}")
        return

    updated = html

    # Apply heatmap column
    col_data = edits.get("heatmap_new_column", {})
    if col_data.get("abbrev"):
        abbrev    = col_data["abbrev"]
        full_name = col_data["full_name"]
        # Insert column header before count column
        updated = updated.replace(
            '<th class="hm-count-col">#</th>',
            f'<th title="{full_name}">{abbrev}</th>\n              <th class="hm-count-col">#</th>',
            1,
        )
        # Insert cells into each row; match by feature label fragment
        feat_map = {r["feature"]: r["filled"] for r in col_data.get("rows", [])}
        for feat, filled in feat_map.items():
            dot_class = "filled" if filled else "empty"
            dot_cell  = f'<td class="hm-cell"><div class="hm-dot {dot_class}"></div></td>\n              '
            # Find the row by its feature label
            row_pat = re.compile(
                r'(<td class="hm-feature-label">' + re.escape(feat) + r'.*?</td>)(.*?)(<td class="hm-count">\d+</td>)',
                re.DOTALL,
            )
            def _insert_cell(m, dc=dot_class):
                return m.group(1) + m.group(2) + f'<td class="hm-cell"><div class="hm-dot {dc}"></div></td>\n              ' + m.group(3)
            updated = row_pat.sub(_insert_cell, updated, count=1)
            # Bump count when filled
            if filled:
                def _bump_count(m2):
                    return m2.group(1) + str(int(m2.group(2)) + 1) + m2.group(3)
                count_pat = re.compile(
                    r'(<td class="hm-feature-label">' + re.escape(feat) + r'.*?<td class="hm-count">)(\d+)(</td>)',
                    re.DOTALL,
                )
                updated = count_pat.sub(_bump_count, updated, count=1)
        # Update heatmap heading school count
        updated = re.sub(
            r'(Feature Demand Across )(\d+)( Schools)',
            lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3),
            updated, count=1,
        )

    # Apply findings updates
    for upd in edits.get("findings_updates", []):
        if upd.get("type") == "add_school_chip":
            frag = upd.get("finding_headline_fragment", "")
            chip = upd.get("chip_html", "")
            if frag and chip:
                pat = re.compile(
                    r'(<div class="exec-finding-headline">[^<]*' + re.escape(frag) + r'[^<]*</div>.*?'
                    r'<div class="exec-finding-schools">)(.*?)(</div>)',
                    re.DOTALL,
                )
                updated = pat.sub(lambda m: m.group(1) + m.group(2) + "\n            " + chip + "\n          " + m.group(3), updated, count=1)
        elif upd.get("type") == "update_headline":
            old_h = upd.get("old_headline", "")
            new_h = upd.get("new_headline", "")
            if old_h and new_h:
                updated = updated.replace(old_h, new_h, 1)
        elif upd.get("type") == "update_body":
            old_frag = upd.get("old_body_fragment", "")
            new_frag = upd.get("new_body_fragment", "")
            if old_frag and new_frag:
                updated = updated.replace(old_frag, new_frag, 1)

    # Add quote
    quote_data = edits.get("new_quote", {})
    if quote_data and quote_data.get("text") and quote_data.get("attribution"):
        new_quote_html = (
            f'\n          <div class="quote-card">\n'
            f'            <div class="quote-text">&ldquo;{quote_data["text"]}&rdquo;</div>\n'
            f'            <div class="quote-attribution">{quote_data["attribution"]}</div>\n'
            f'          </div>'
        )
        updated = updated.replace(
            '</div>\n        </div>\n      </div>\n\n    </div><!-- /intel-two-col -->',
            new_quote_html + '\n        </div>\n      </div>\n\n    </div><!-- /intel-two-col -->',
            1,
        )

    if updated != html:
        INDEX_FILE.write_text(updated, encoding="utf-8")
        print(f"  [OK]  Applied editorial updates for {s['name']}")
    else:
        print("  [INFO] No editorial changes applied")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NSLS Roadshow full school generator")
    parser.add_argument("--name",         required=True)
    parser.add_argument("--location",     required=True)
    parser.add_argument("--type",         required=True, dest="school_type")
    parser.add_argument("--fathom-url",   required=True)
    parser.add_argument("--csr",          default="")
    parser.add_argument("--tier",         default=3, type=int)
    parser.add_argument("--date",         default=None, help="Override meeting date (YYYY-MM-DD)")
    parser.add_argument("--slug",         default=None)
    parser.add_argument("--meeting-num",  default=1, type=int)
    parser.add_argument("--airtable-id",        default="")
    parser.add_argument("--airtable-school-id",   default="", help="Target Schools Airtable record ID — pushes champion_potential and enthusiasm_score after generation")
    parser.add_argument("--airtable-contact-ids", default="", help="Comma-separated Contact record IDs in advisor order — pushes per-advisor champion_potential to the Contacts table")
    parser.add_argument("--advisors",        default=1, type=int, help="Number of advisors met at this school")
    parser.add_argument("--advisor-names",   default="", help="Comma-separated advisor names (for group calls)")
    parser.add_argument("--chapter-status",  default="TBD", help="Chapter status (Established/New/TBD)")
    parser.add_argument("--chapter-type",    default="TBD", help="Chapter type (Hybrid/Online/In-Person/TBD)")
    parser.add_argument("--update-index",    action="store_true")
    parser.add_argument("--dry-run",         action="store_true", help="Print prompts; skip API calls")
    parser.add_argument("--transcript-file", default=None, help="Path to plain-text transcript; bypasses Fathom API (use when key is expired)")
    args = parser.parse_args()

    slug = args.slug or to_slug(args.name)

    # ── 1. Fathom: transcript ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"School: {args.name}")
    print(f"{'='*60}")
    print("\n[1/5] Fetching Fathom transcript...")

    if args.transcript_file:
        m_url = re.search(r"/(?:calls|recordings?)/(\d+)", args.fathom_url)
        recording_id = m_url.group(1) if m_url else "unknown"
        calls_url = args.fathom_url
        fathom_duration = "? min"
        fathom_date = args.date or datetime.today().strftime("%Y-%m-%d")
        items = []
        transcript_text = Path(args.transcript_file).read_text(encoding="utf-8")
        print(f"  Using local transcript file: {args.transcript_file}")
        print(f"  Recording ID: {recording_id}  →  {calls_url}")
    else:
        recording_id, fathom_duration, fathom_date, calls_url = find_recording_id(args.fathom_url)
        print(f"  Recording ID: {recording_id}  →  {calls_url}")
        items = fetch_transcript(recording_id)
        print(f"  Transcript: {len(items)} segments | Date: {fathom_date} | Duration: {fathom_duration}")
        transcript_text = transcript_to_text(items)

    date     = args.date or fathom_date
    duration = fathom_duration

    s = {
        "name":        args.name,
        "slug":        slug,
        "location":    args.location,
        "school_type": args.school_type,
        "fathom_url":  args.fathom_url,
        "csr":         args.csr,
        "tier":        args.tier,
        "date":        date,
        "duration":    duration,
        "meeting_num": args.meeting_num,
        "airtable_id":    args.airtable_id,
        "advisors":       args.advisors,
        "chapter_status": args.chapter_status,
        "chapter_type":   args.chapter_type,
    }

    if not args.transcript_file:
        transcript_text = transcript_to_text(items)

    if args.dry_run:
        print("\n[DRY RUN] Meeting report prompt (truncated):")
        print(build_report_prompt(transcript_text[:500] + "...", args.name, args.location, args.school_type, args.csr, args.tier)[:800])
        print("\n[DRY RUN] Hub data prompt (truncated):")
        print(build_hub_prompt(transcript_text[:500] + "...", args.name, args.location, args.school_type, "", "")[:800])
        print("\n[DRY RUN] Exiting without writing files.")
        sys.exit(0)

    # ── 2. Claude: meeting report sections ────────────────────────────────
    print("\n[2/5] Generating meeting report sections (Claude)...")
    report_prompt = build_report_prompt(
        transcript_text, args.name, args.location, args.school_type, args.csr, args.tier, args.advisor_names
    )
    sections_html = call_claude(SYSTEM_PROMPT, report_prompt, max_tokens=8192)
    sections_html = re.sub(r"^```(?:html)?\s*", "", sections_html.strip())
    sections_html = re.sub(r"\s*```$", "", sections_html.strip())
    print(f"  Generated {len(sections_html)} chars of HTML")

    # ── 3. Claude: hub page data ───────────────────────────────────────────
    print("\n[3/5] Generating hub page data (Claude)...")
    hub_prompt = build_hub_prompt(
        transcript_text, args.name, args.location, args.school_type, args.csr, sections_html, args.advisor_names
    )
    hub_raw = call_claude(SYSTEM_PROMPT, hub_prompt, max_tokens=4096)

    # Strip any markdown code fences
    hub_raw = re.sub(r"^```(?:json)?\s*", "", hub_raw.strip())
    hub_raw = re.sub(r"\s*```$", "", hub_raw.strip())
    try:
        hub = json.loads(hub_raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] Could not parse hub JSON: {e}")
        print(f"  Raw output:\n{hub_raw[:500]}")
        hub = {}
    print(f"  Parsed hub data with {len(hub)} top-level keys")

    # ── 4. Timestamp injection ─────────────────────────────────────────────
    print("\n[4/5] Matching timestamps from Fathom transcript...")

    def _inject_ts(item_list: list, key: str = "keywords"):
        for item in item_list:
            kws = item.get(key, [])
            if kws:
                secs, score = find_best_timestamp(items, kws)
                if secs is not None and score >= 3:
                    item["_ts_link"] = ts_link_html(calls_url, secs)
                    label = item.get("label") or item.get("text", "")[:40]
                    print(f"  ✓ {label!r:45s} → {fmt_time(secs)}  (score={score})")

    _inject_ts(hub.get("school_about", []))
    _inject_ts(hub.get("whats_working", []))
    _inject_ts(hub.get("whats_not_working", []))
    _inject_ts(hub.get("action_items", []))

    # Key signal timestamp
    ks_kws = hub.get("key_signal_keywords", [])
    if ks_kws:
        secs, score = find_best_timestamp(items, ks_kws)
        if secs is not None and score >= 3:
            hub["_key_signal_ts_link"] = ts_link_html(calls_url, secs)
            print(f"  ✓ 'Key Signal'                                → {fmt_time(secs)}  (score={score})")

    # ── 5. Airtable survey data (optional) ────────────────────────────────
    airtable_html = ""
    if args.airtable_id:
        print(f"\n[5/5] Fetching Airtable survey record {args.airtable_id}...")
        fields = fetch_airtable_survey(args.airtable_id)
        airtable_html = render_survey_section(fields, args.airtable_id, args.name) if fields else ""
    else:
        print("\n[5/5] No --airtable-id provided; skipping survey section")

    # ── Write files ────────────────────────────────────────────────────────
    print("\n[Writing files]")

    # Hub page
    hub_path = PROJECT / "schools" / slug
    has_local_survey = (hub_path / "survey.html").exists()
    hub_html_str = render_hub_html(s, hub, airtable_html, has_local_survey)
    hub_path.mkdir(parents=True, exist_ok=True)
    hub_file = hub_path / "index.html"
    hub_file.write_text(hub_html_str, encoding="utf-8")
    print(f"  Hub page:       {hub_file}")

    # Meeting report
    report_dir = PROJECT / "schools" / slug / "meetings"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_filename = f"meeting-{args.meeting_num}-{date}.html"
    report_path = report_dir / report_filename
    report_path.write_text(render_report_html(s, sections_html, has_local_survey), encoding="utf-8")
    print(f"  Meeting report: {report_path}")

    # Auto-inject timestamps into the newly generated meeting report
    print(f"\n[Injecting timestamps into meeting report]")
    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "add_timestamps.py"), "--file", str(report_path)],
        check=False,
    )

    # Update index
    if args.update_index:
        print(f"\n[Updating index: {INDEX_FILE.name}]")
        update_index(s, hub)
        if hub:
            print(f"\n[Updating editorial content: Key Findings, Heatmap, Quotes]")
            update_index_editorial(s, hub)

    # ── Airtable Target Schools push (optional) ────────────────────────────
    if args.airtable_school_id and hub:
        print(f"\n[Airtable] Pushing to Target Schools record {args.airtable_school_id}...")
        contact_ids = [c.strip() for c in args.airtable_contact_ids.split(",") if c.strip()] if args.airtable_contact_ids else None
        push_school_to_airtable(args.airtable_school_id, hub, contact_ids)

    print(f"\n{'='*60}")
    print("Done.")
    print(f"  file://{hub_file}")
    print(f"  file://{report_path}")
    if not args.update_index:
        print("\nRe-run with --update-index to add this school to the index")


if __name__ == "__main__":
    main()
