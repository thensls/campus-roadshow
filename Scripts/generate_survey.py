#!/usr/bin/env python3
"""
generate_survey.py — Generate a static survey results page for a school from Airtable.

Usage:
  python generate_survey.py \
    --airtable-id recjcYaHnZTNmjBKs \
    --slug drew-university \
    --school "Drew University"

Env vars required:
  AIRTABLE_API_KEY

Output:
  report/schools/{slug}/survey.html
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

AIRTABLE_BASE    = "https://api.airtable.com/v0"
AIRTABLE_BASE_ID = "app5rj9bOGQNFoIoD"
AIRTABLE_TABLE   = "Survey%20Responses"

PROJECT = Path.home() / "Desktop" / "Campus Roadshow" / "report"

# ── Feature signal field names (top pick + runner-ups per category) ────────
FEATURE_CATEGORIES = [
    {
        "label": "Career Clarity",
        "top": ["[ARCHIVED] test", "test", "Career Clarity", "Career Clarity Options:", "Career Clarity Signal"],
        "runner_ups": ["Tags", "[ARCHIVED] Feature 3", "Feature 3"],
    },
    {
        "label": "Leadership & Skills",
        "top": ["[ARCHIVED] Leadership & Skills Options", "Leadership & Skills Options:", "Leadership & Skills", "Leadership"],
        "runner_ups": ["[ARCHIVED] Leadership & Skills Feature 2", "[ARCHIVED] Leadership & Skills Feature 3",
                       "Leadership & Skills Feature 2", "Leadership & Skills Feature 3"],
    },
    {
        "label": "Networking & Connection",
        "top": ["[ARCHIVED] Network & Connection Options", "Network & Connection Options:", "Networking", "Networking Signal"],
        "runner_ups": ["[ARCHIVED] Networking & Connection Feature 2", "[ARCHIVED] Networking & Connection Feature 3",
                       "Networking & Connection Feature 2:", "Networking & Connection Feature 3:"],
    },
    {
        "label": "Outcomes & Data",
        "top": ["[ARCHIVED] Outcomes & Data Options", "Outcomes & Data Options:", "Outcomes & Data", "Outcomes"],
        "runner_ups": ["[ARCHIVED] Outcomes & Data Feature 2", "[ARCHIVED] Outcomes & Data Feature 3",
                       "Outcomes & Data Feature 2:", "Outcomes & Data Feature 3:"],
    },
    {
        "label": "Engagement & Experience",
        "top": ["[ARCHIVED] Engagement & Experience Options", "Engagement & Experience Options:", "Engagement", "Engagement Signal"],
        "runner_ups": ["[ARCHIVED] Engagement & Experience Feature 2", "[ARCHIVED] Engagement & Experience Feature 3",
                       "Engagement & Experience Feature 2:", "Engagement & Experience Feature 3:"],
    },
]

# Fields used in the priority section (detected by prefix pattern)
PRIORITY_FIELD_PREFIXES = [
    "Focus Area", "Priority", "Rank", "priority_", "Select",
    "Product Feedback/Suggestions",
]

# Fields to skip in the "extra fields" fallback table
SKIP_IN_EXTRAS = {
    "Response ID", "Timestamp", "Respondent Name", "Respondent Email",
    "Respondent Role", "School", "Survey Analysis & Key Themes (AI)",
    "Executive Summary (JSON)", "Tags", "Respondent Contact",
    "Describe top concerns",
    "What feature or capability are we missing that would make Society indispensable for your institution?",
    "Product Feedback/Suggestions", "Focus Area 2:", "Focus Area 4:", "Select",
    "test", "Feature 3",
    "Leadership & Skills Options:", "Leadership & Skills Feature 2", "Leadership & Skills Feature 3",
    "Network & Connection Options:", "Networking & Connection Feature 2:", "Networking & Connection Feature 3:",
    "Outcomes & Data Options:", "Outcomes & Data Feature 2:", "Outcomes & Data Feature 3:",
    "Engagement & Experience Options:", "Engagement & Experience Feature 2:", "Engagement & Experience Feature 3:",
}

PRODUCT_COUNCIL_KEYS = [
    "How interested would you be in serving on a Product Council to help shape Society's development? Instructions: Select one",
    "Product Council Interest",
    "Product Council",
]

# All open-ended (free text) survey questions, in display order.
# Shown even when the response is blank.
OPEN_QUESTIONS = [
    ("What's working that is essential to keep for your organization?",
     "What\u2019s Working That\u2019s Essential to Keep"),
    ("Describe top concerns",
     "Top Concerns"),
    ("What feature or capability are we missing that would make Society indispensable for your institution?",
     "Missing Capability"),
    ("What would students need to see to actively use Society weekly (not just complete it once)?",
     "What Would Make Students Use It Weekly?"),
    ("What data or reporting would you need to prove ROI to your leadership?",
     "Data / Reporting Needed to Prove ROI"),
    ("Other",
     "Other / Additional Comments"),
    ("How interested would you be in serving on a Product Council to help shape Society's development? Instructions: Select one",
     "Product Council Interest"),
]

PRIORITY_MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]


# ─────────────────────────────────────────────────────────────────────────────
# Airtable
# ─────────────────────────────────────────────────────────────────────────────

def fetch_record(record_id: str) -> dict:
    key = os.environ.get("AIRTABLE_API_KEY", "").strip()
    if not key:
        sys.exit("Error: AIRTABLE_API_KEY environment variable is not set.")
    url = f"{AIRTABLE_BASE}/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}/{record_id}"
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"})
    if not r.ok:
        sys.exit(f"Error: Airtable returned HTTP {r.status_code} — {r.text}")
    return r.json().get("fields", {})


# ─────────────────────────────────────────────────────────────────────────────
# Field helpers
# ─────────────────────────────────────────────────────────────────────────────

def get(fields: dict, *keys):
    for k in keys:
        v = fields.get(k)
        if v and not isinstance(v, (list, dict)):
            return str(v).strip()
        if isinstance(v, list) and v:
            return ", ".join(str(x) for x in v).strip()
    return None


def get_airtable_text(val):
    """Safely extract text from an Airtable field value (handles error objects)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, dict):
        # AI/formula fields sometimes have {state, value} shape
        inner = val.get("value")
        if inner and isinstance(inner, str):
            return inner.strip() or None
    if isinstance(val, list):
        parts = [get_airtable_text(x) for x in val]
        return ", ".join(p for p in parts if p) or None
    return None


def get_exec_summary(fields: dict):
    """Try to parse the Executive Summary (JSON) AI field."""
    raw = fields.get("Executive Summary (JSON)")
    if not raw:
        return None
    text = get_airtable_text(raw)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def get_priorities(fields: dict):
    """Collect all non-empty focus area / priority fields as an ordered list."""
    # Ordered candidate field names — include both current and [ARCHIVED] variants
    ordered_keys = [
        "Product Feedback/Suggestions",
        "[ARCHIVED] Focus Area 2", "Focus Area 2:",
        "[ARCHIVED] Focus Area 4", "Focus Area 4:",
        "[ARCHIVED] Select", "Select",
    ]
    results = []
    for k in ordered_keys:
        v = get_airtable_text(fields.get(k))
        if v:
            # Strip everything after " → " (these are description tooltips)
            label = v.split(" → ")[0].strip()
            if label and label not in results:
                results.append(label)
    return results


def get_feature_top(fields: dict, keys: list):
    for k in keys:
        v = get_airtable_text(fields.get(k))
        if v:
            return v.split(" → ")[0].strip()
    return None


def get_feature_runners(fields: dict, keys: list):
    out = []
    for k in keys:
        v = get_airtable_text(fields.get(k))
        if v:
            out.append(v.split(" → ")[0].strip())
    return out


def get_product_council(fields: dict):
    return get(fields, *PRODUCT_COUNCIL_KEYS)


def generate_profile(respondent: str, role: str, school: str, fields: dict) -> str:
    """Call Claude to write a 2-3 sentence practitioner profile when the AI field is unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return ""
    answers = {
        "Role": role,
        "Priorities": get_priorities(fields),
        "Top concerns": get_airtable_text(fields.get("Describe top concerns")),
        "Missing capability": get_airtable_text(fields.get(
            "What feature or capability are we missing that would make Society indispensable for your institution?"
        )),
        "What's working": get_airtable_text(fields.get("What's working that is essential to keep for your organization?")),
    }
    answers_text = "\n".join(f"- {k}: {v}" for k, v in answers.items() if v)
    prompt = (
        f"Write a 2-3 sentence professional bio for {respondent}, {role} at {school}, "
        f"based on their NSLS Society platform survey responses below. "
        f"Focus on their role, what they care about for students, and their key priorities. "
        f"Write in third person. Output only the bio, no preamble.\n\n{answers_text}"
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return ""


def extra_fields(fields: dict):
    result = []
    for k, v in fields.items():
        if k in SKIP_IN_EXTRAS:
            continue
        if k.startswith("[ARCHIVED]"):
            continue
        text = get_airtable_text(v)
        if not text:
            continue
        result.append((k, text))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
    :root {
      --navy:#1A3550; --border:rgba(30,20,20,0.1);
      --text:#1E1414; --muted:#6B6357; --card:#E8DDD5; --black:#1E1414;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    a{color:#1A3550;text-decoration:none;} a:hover{color:#C96058;}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#F2E9E2;color:var(--black);line-height:1.6;}
    h1,h2{font-family:'Cigars',Georgia,'Times New Roman',serif;}
    .page-header{background:#F2E9E2;border-bottom:2px solid #1A3550;padding:2rem 0 0.75rem;}
    .inner{max-width:1180px;margin:0 auto;padding:0 2rem;}
    .pills{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;}
    .pill{transition:color .2s;background:transparent;border:1px solid rgba(36,59,82,0.35);border-radius:20px;padding:4px 14px;font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;color:#243B52;}
    a.pill:hover{color:#C96058;}
    .page-header h1{font-size:1.9rem;font-weight:700;color:#1A3550;margin-bottom:0.3rem;}
    .page-header .sub{font-size:1rem;color:#6B6357;margin-bottom:1rem;}
    .btn-row{display:flex;gap:10px;flex-wrap:wrap;}
    .btn{display:inline-flex;align-items:center;gap:8px;padding:9px 20px;border-radius:8px;font-weight:600;font-size:13px;text-decoration:none;background:#243B52;color:#FFFDF8;border:1px solid #243B52;transition:opacity .2s;}
    .btn:hover{opacity:0.88;color:#FFFDF8;}
    main{max-width:1180px;margin:0 auto;padding:2.5rem 2rem 5rem;}
    .section{margin-bottom:2.5rem;}
    .section-title{font-size:1.2rem;font-weight:700;color:#1A3550;padding-bottom:10px;border-bottom:2px solid #1A3550;margin-bottom:1.25rem;font-family:'Cigars',Georgia,serif;}
    .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px;}
    @media(max-width:860px){.grid-2{grid-template-columns:1fr;}}
    .card{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:24px;}
    .card-label{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-bottom:14px;display:flex;align-items:center;gap:8px;}
    .card-label::after{content:'';flex:1;height:1px;background:var(--border);}
    /* Priority list */
    .priority-list{list-style:none;}
    .priority-list li{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border);font-size:14px;line-height:1.5;}
    .priority-list li:last-child{border-bottom:none;}
    .medal{font-size:18px;flex-shrink:0;margin-top:1px;}
    /* Feature table */
    .feature-table{width:100%;border-collapse:collapse;font-size:13px;}
    .feature-table tr{border-bottom:1px solid var(--border);}
    .feature-table tr:last-child{border-bottom:none;}
    .feature-table td{padding:10px 12px;vertical-align:top;}
    .feature-table td:first-child{width:38%;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);padding-right:8px;}
    .feat-pick{display:block;font-weight:600;color:#1A3550;margin-bottom:4px;font-size:13px;}
    .feat-runner{display:block;color:var(--muted);font-size:12px;margin-top:3px;}
    /* Open questions */
    .oq-row{padding:16px 0;border-bottom:1px solid var(--border);}
    .oq-row:last-child{border-bottom:none;}
    .oq-label{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;color:var(--muted);margin-bottom:8px;}
    .oq-answer{font-size:14px;line-height:1.65;color:var(--black);}
    .oq-empty{color:var(--muted);font-style:italic;}
    /* Stats row */
    .stats-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:2.5rem;}
    .stat-tile{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:18px 22px;min-width:180px;}
    .stat-tile .lbl{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;color:var(--muted);margin-bottom:8px;}
    .stat-tile .val{font-size:17px;font-weight:700;color:#1A3550;line-height:1.3;}
    /* Profile */
    .profile-box{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:20px 24px;display:flex;align-items:flex-start;gap:14px;font-size:14px;line-height:1.65;}
    .profile-icon{font-size:24px;flex-shrink:0;margin-top:2px;}
    /* Extra fields */
    .extra-table{width:100%;border-collapse:collapse;font-size:13px;}
    .extra-table tr{border-bottom:1px solid var(--border);}
    .extra-table tr:last-child{border-bottom:none;}
    .extra-table th{padding:9px 14px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted);background:rgba(30,20,20,0.03);width:35%;vertical-align:top;}
    .extra-table td{padding:9px 14px;vertical-align:top;}
    .footer{text-align:center;color:#6B6357;font-size:12px;padding:32px;border-top:1px solid rgba(30,20,20,0.1);background:#F2E9E2;}
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_page(school: str, slug: str, at_id: str, fields: dict) -> str:
    respondent = get(fields, "Respondent Name", "Name") or "Survey Respondent"
    role       = get(fields, "Respondent Role", "Role") or ""
    council    = get_product_council(fields)
    priorities = get_priorities(fields)
    exec_json  = get_exec_summary(fields)
    today      = datetime.today().strftime("%B %-d, %Y")

    # ── At-a-glance stat tiles ─────────────────────────────────────────────
    stat_tiles = ""
    if role:
        stat_tiles += f'<div class="stat-tile"><div class="lbl">Role</div><div class="val">{role}</div></div>'
    if council:
        stat_tiles += f'<div class="stat-tile"><div class="lbl">Product Council Interest</div><div class="val">{council.strip()}</div></div>'

    stats_block = f'<div class="stats-row">{stat_tiles}</div>' if stat_tiles else ""

    # ── Priority rankings ──────────────────────────────────────────────────
    if priorities:
        items_html = ""
        for i, text in enumerate(priorities):
            medal = PRIORITY_MEDALS[i] if i < len(PRIORITY_MEDALS) else "•"
            items_html += f'<li><span class="medal">{medal}</span><span>{text}</span></li>\n'
        pri_html = f'<ul class="priority-list">{items_html}</ul>'
    else:
        pri_html = '<p style="color:var(--muted);font-style:italic;">No priority data recorded.</p>'

    # ── Feature signals ────────────────────────────────────────────────────
    feat_rows = ""
    for cat in FEATURE_CATEGORIES:
        top     = get_feature_top(fields, cat["top"])
        runners = get_feature_runners(fields, cat["runner_ups"])
        if not top and not runners:
            continue
        runners_html = "".join(f'<span class="feat-runner">↳ {r}</span>' for r in runners)
        top_html = f'<span class="feat-pick">{top}</span>' if top else ""
        feat_rows += (
            f'<tr>'
            f'<td>{cat["label"]}</td>'
            f'<td>{top_html}{runners_html}</td>'
            f'</tr>'
        )
    signals_html = (
        f'<table class="feature-table"><tbody>{feat_rows}</tbody></table>'
        if feat_rows
        else '<p style="color:var(--muted);font-style:italic;">No feature signals recorded.</p>'
    )

    # ── Open questions (shown even when blank) ─────────────────────────────
    open_q_html = ""
    for field_name, display_label in OPEN_QUESTIONS:
        response = get_airtable_text(fields.get(field_name))
        if response:
            open_q_html += f'''
    <div class="oq-row">
      <div class="oq-label">{display_label}</div>
      <div class="oq-answer">{response.strip()}</div>
    </div>'''
        else:
            open_q_html += f'''
    <div class="oq-row oq-blank">
      <div class="oq-label">{display_label}</div>
      <div class="oq-answer oq-empty">No response provided</div>
    </div>'''

    # ── Executive Summary (AI) + profile fallback ─────────────────────────
    exec_block = ""
    profile_text = ""
    if exec_json and isinstance(exec_json, dict):
        profile_text = exec_json.get("practitioner_profile") or exec_json.get("profile") or ""
    if not profile_text:
        print("  Executive Summary field unavailable; generating profile via Claude...")
        profile_text = generate_profile(respondent, role, school, fields)
    if profile_text:
        exec_block = f'''
  <div class="section">
    <h2 class="section-title">Respondent Profile</h2>
    <div class="profile-box">
      <span class="profile-icon">&#x1F9D1;&#x200D;&#x1F4BC;</span>
      <div><strong>{respondent}</strong>{f" &mdash; {role}" if role else ""}<br><br>{profile_text}</div>
    </div>
  </div>'''

    # ── Extra fields ───────────────────────────────────────────────────────
    extras = extra_fields(fields)
    extra_block = ""
    if extras:
        rows = "".join(
            f'<tr><th>{label}</th><td>{value}</td></tr>'
            for label, value in extras
        )
        extra_block = f'''
  <div class="section">
    <h2 class="section-title">Additional Fields</h2>
    <div class="card" style="padding:0;overflow:hidden;">
      <table class="extra-table"><tbody>{rows}</tbody></table>
    </div>
  </div>'''

    # ── Meeting report button (auto-detect first meeting file) ────────────────
    meeting_btn = ""
    meetings_dir = PROJECT / "schools" / slug / "meetings"
    meeting_files = sorted(meetings_dir.glob("meeting-*.html")) if meetings_dir.exists() else []
    if meeting_files:
        meeting_file = meeting_files[0].name
        meeting_btn = f'''
      <a class="btn" href="meetings/{meeting_file}">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Discovery &amp; Demo Meeting
      </a>'''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Survey Results — {school} | NSLS Roadshow</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>

<div class="page-header">
  <div class="inner">
    <div class="pills">
      <a href="../../index.html" class="pill" style="text-decoration:none;">NSLS Society Roadshow</a>
      <span class="pill">Pre-Meeting Survey</span>
    </div>
    <h1>{school} &mdash; Pre-Meeting Survey</h1>
    <div class="sub">{respondent}{f" &mdash; {role}" if role else ""}</div>
    <div class="btn-row">
      <a class="btn" href="index.html">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        {school} Hub
      </a>{meeting_btn}
    </div>
  </div>
</div>

<main>
  {stats_block}

  <div class="section">
    <h2 class="section-title">What Matters Most?</h2>
    <div class="grid-2">
      <div class="card">
        <div class="card-label">Priority Rankings</div>
        {pri_html}
      </div>
      <div class="card">
        <div class="card-label">Top Feature Picks by Category</div>
        {signals_html}
      </div>
    </div>
  </div>

  <div class="section">
    <h2 class="section-title">Additional Responses</h2>
    <div class="card">
      {open_q_html}
    </div>
  </div>

{exec_block}
{extra_block}

</main>

<div class="footer">
  NSLS Society Platform Roadshow &nbsp;&middot;&nbsp; {school} &nbsp;&middot;&nbsp; {respondent}<br>
  Airtable Record: {at_id} &nbsp;&middot;&nbsp; Generated {today}
</div>

<script src="/auth-chip.js"></script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate a survey results page from Airtable.")
    parser.add_argument("--airtable-id", required=True, help="Airtable record ID (e.g. recjcYaHnZTNmjBKs)")
    parser.add_argument("--slug",        required=True, help="School slug (e.g. drew-university)")
    parser.add_argument("--school",      required=True, help="School display name (e.g. 'Drew University')")
    args = parser.parse_args()

    school_dir = PROJECT / "schools" / args.slug
    if not school_dir.exists():
        sys.exit(f"Error: School directory not found: {school_dir}")

    print(f"Fetching Airtable record {args.airtable_id}...")
    fields = fetch_record(args.airtable_id)
    print(f"  {len(fields)} fields: {', '.join(fields.keys())}")

    html = render_page(args.school, args.slug, args.airtable_id, fields)

    out_path = school_dir / "survey.html"
    out_path.write_text(html)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
