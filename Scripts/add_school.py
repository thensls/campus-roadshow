#!/usr/bin/env python3
"""
add_school.py — Orchestration script for adding a new school to the Campus Roadshow report.

Usage:
    python add_school.py \\
        --name "Texas Lutheran University" \\
        --location "Seguin, TX" \\
        --type "Private 4-Year" \\
        --fathom-url "https://app.fathom.video/..." \\
        --csr "Olivia Orend" \\
        --date 2026-04-01 \\
        --airtable-id recXXXXXXXXXXXXXX  # optional

Steps:
    1. Run generate_school.py  (hub page + meeting report)
    2. Run generate_survey.py  (survey page) if --airtable-id provided
    3. Deploy to Vercel (--prod) unless --no-deploy is set
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPORT_DIR  = SCRIPTS_DIR.parent / "report"


def run(cmd: list[str], label: str) -> int:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=SCRIPTS_DIR)
    if result.returncode != 0:
        print(f"\n[ERROR] {label} failed (exit {result.returncode})", file=sys.stderr)
    return result.returncode


def main():
    import re
    parser = argparse.ArgumentParser(
        description="Add a new school to the Campus Roadshow report and deploy."
    )
    parser.add_argument("--name",         required=True,  help="School display name")
    parser.add_argument("--location",     required=True,  help="City, State")
    parser.add_argument("--type",         required=True,  dest="school_type",
                        help="School type (e.g. 'Public 4-Year')")
    parser.add_argument("--fathom-url",   required=True,  help="Fathom recording URL")
    parser.add_argument("--csr",          default="",     help="CSR / account owner name")
    parser.add_argument("--tier",         default=3, type=int)
    parser.add_argument("--date",         default=None,   help="Meeting date override (YYYY-MM-DD)")
    parser.add_argument("--slug",         default=None,   help="Directory slug override")
    parser.add_argument("--meeting-num",  default=1, type=int)
    parser.add_argument("--advisors",        default=1, type=int, help="Number of advisors met at this school")
    parser.add_argument("--advisor-names",   default="", help="Comma-separated advisor names (for group calls)")
    parser.add_argument("--chapter-status",  default="TBD", help="Chapter status (Established/New/TBD)")
    parser.add_argument("--chapter-type",    default="TBD", help="Chapter type (Hybrid/Online/In-Person/TBD)")
    parser.add_argument("--airtable-id",     default="",    help="Airtable Survey Responses record ID")
    parser.add_argument("--no-deploy",       action="store_true",
                        help="Skip Vercel deployment")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Pass --dry-run to generate_school.py; skip survey + deploy")
    args = parser.parse_args()

    # ── Step 1: Generate hub + meeting report ────────────────────────────────
    gen_school_cmd = [
        sys.executable, str(SCRIPTS_DIR / "generate_school.py"),
        "--name",       args.name,
        "--location",   args.location,
        "--type",       args.school_type,
        "--fathom-url", args.fathom_url,
        "--csr",        args.csr,
        "--tier",       str(args.tier),
        "--meeting-num", str(args.meeting_num),
        "--update-index",
    ]
    if args.date:
        gen_school_cmd += ["--date", args.date]
    if args.slug:
        gen_school_cmd += ["--slug", args.slug]
    if args.airtable_id:
        gen_school_cmd += ["--airtable-id", args.airtable_id]
    gen_school_cmd += ["--advisors", str(args.advisors)]
    if args.advisor_names:
        gen_school_cmd += ["--advisor-names", args.advisor_names]
    gen_school_cmd += ["--chapter-status", args.chapter_status]
    gen_school_cmd += ["--chapter-type",   args.chapter_type]
    if args.dry_run:
        gen_school_cmd.append("--dry-run")

    rc = run(gen_school_cmd, "Step 1/3 — Generating hub page + meeting report")
    if rc != 0:
        sys.exit(rc)

    if args.dry_run:
        print("\n[DRY RUN] Skipping survey generation and deployment.")
        sys.exit(0)

    # ── Step 2: Generate survey page ─────────────────────────────────────────
    if args.airtable_id:
        from pathlib import Path as _Path
        import re

        slug = args.slug or re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")

        gen_survey_cmd = [
            sys.executable, str(SCRIPTS_DIR / "generate_survey.py"),
            "--airtable-id", args.airtable_id,
            "--slug",        slug,
            "--school",      args.name,
        ]
        rc = run(gen_survey_cmd, "Step 2/3 — Generating survey results page")
        if rc != 0:
            print("[WARN] Survey generation failed; continuing to deploy.", file=sys.stderr)
    else:
        print("\n[Step 2/3 — Survey] No --airtable-id provided; creating placeholder survey page.")
        slug = args.slug or re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
        survey_path = REPORT_DIR / "schools" / slug / "survey.html"
        if not survey_path.exists():
            survey_path.write_text(
                f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Survey — {args.name} | NSLS Roadshow</title>
</head>
<body style="font-family:sans-serif;padding:2rem;">
  <p><a href="index.html">&larr; {args.name} Hub</a></p>
  <h1>{args.name} &mdash; Pre-Meeting Survey</h1>
  <p>No survey responses on file yet.</p>
</body>
</html>""",
                encoding="utf-8",
            )
            print(f"  Created placeholder: {survey_path}")
        else:
            print(f"  Placeholder already exists; skipping.")

    # ── Step 3: Deploy to Vercel ──────────────────────────────────────────────
    if args.no_deploy:
        print("\n[Step 3/3 — Deploy] Skipped (--no-deploy).")
        sys.exit(0)

    rc = run(
        ["npx", "vercel", "--prod", "--yes"],
        "Step 3/3 — Deploying to Vercel (prod)",
    )
    sys.exit(rc)


if __name__ == "__main__":
    # Need re at module level for slug fallback outside the if-block
    import re
    main()
