#!/usr/bin/env python3
"""
Reformat reports generated with modern template to use original Cigars/cream template.
Extracts content from existing new reports and rewraps with original styling.
"""

import json
import re
from pathlib import Path
from datetime import datetime

# Original template CSS
ORIGINAL_CSS = '''
  :root {
    --navy:   #1A3550;
    --gold:   #F2DA4E;
    --green:  #88D86B;
    --teal:   #88D86B;
    --amber:  #F2DA4E;
    --red:    #C96058;
    --bg:     #F2E9E2;
    --card:   #E8DDD5;
    --text:   #1E1414;
    --muted:  #6B6357;
    --border: rgba(30,20,20,0.1);
    --yellow: #F2DA4E;
    --white:  #FFFDF8;
    --black:  #1E1414;
    --purple: #4a4faa;
    --pink:   #C96058;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #F2E9E2;
    color: var(--black);
    line-height: 1.6;
  }
  h1, h2 { font-family: 'Cigars', Georgia, 'Times New Roman', serif; }
  a { color: #1A3550; }
  a:hover { color: #C96058; }

  /* Header */
  .page-header {
    background: #F2E9E2;
    border-bottom: 2px solid #1A3550;
    padding: 2rem 0 0.56rem;
  }
  .page-header .header-inner {
    max-width: 1180px;
    margin: 0 auto;
    padding: 0 1.5rem;
  }
  .page-header .header-pills {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }
  .page-header .header-pill {
    background: transparent;
    border: 1px solid rgba(36,59,82,0.35);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: #243B52;
  }
  .page-header .header-buttons {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 16px;
  }
  .page-header .header-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #243B52;
    border: 1px solid #243B52;
    color: #FFFDF8;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 14px;
    text-decoration: none;
    transition: background 0.15s;
  }
  .page-header .header-btn:hover { background: #1a2d3e; color: #FFFDF8; }
  .page-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: #1A3550;
    margin-bottom: 0.5rem;
  }
  .page-header .recording-link {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.85rem;
    background: #C96058;
    border: 1px solid #C96058;
    border-radius: 6px;
    color: #FFFDF8;
    font-size: 0.8rem;
    font-weight: 600;
    text-decoration: none;
    transition: opacity 0.15s;
  }
  .page-header .recording-link:hover {
    opacity: 0.88;
    color: #FFFDF8;
  }

  /* Main content */
  main {
    max-width: 1180px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
    display: flex;
    align-items: flex-start;
    gap: 2rem;
  }
  .content { flex: 1; min-width: 0; }

  /* TOC sidebar */
  .toc-sidebar {
    width: 185px;
    flex-shrink: 0;
    position: sticky;
    top: 1.5rem;
  }
  .toc-nav {
    background: var(--card);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 0.9rem 1rem;
  }
  .toc-nav .toc-heading {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 0.65rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  .toc-nav a {
    display: block;
    font-size: 0.78rem;
    color: var(--text);
    text-decoration: none;
    padding: 0.28rem 0.5rem;
    border-radius: 4px;
    line-height: 1.4;
    margin-bottom: 0.05rem;
  }
  .toc-nav a:hover { background: rgba(30,20,20,0.05); color: var(--navy); }

  /* Section */
  .section {
    margin-bottom: 2.5rem;
  }
  .section-title {
    font-size: 20px;
    font-weight: 700;
    color: var(--navy);
    padding-bottom: 10px;
    border-bottom: 2px solid var(--navy);
    margin-bottom: 1rem;
    font-family: 'Cigars', Georgia, serif;
  }

  /* Card */
  .card {
    background: var(--card);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 1.25rem 1.5rem;
  }
  .card h3 {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--yellow);
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
    border: 1px solid var(--border);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    border-left: 3px solid #1A3550;
  }
  .theme-card .theme-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.4rem;
  }
  .theme-card p { font-size: 0.9rem; color: var(--text); }

  /* Enthusiasm score */
  .enthusiasm-score {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 64px;
    height: 64px;
    border-radius: 50%;
    background: var(--gold);
    color: var(--black);
    font-size: 1.3rem;
    font-weight: 800;
    margin-bottom: 1rem;
    font-family: 'Cigars', Georgia, serif;
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
    background: #1A3550;
    color: #FFFDF8;
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
  .feature-table tr:nth-child(even) { background: rgba(30,20,20,0.03); }

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
  .badge-strong   { background: rgba(60,140,30,0.1);    color: #2a7a10; }
  .badge-positive { background: #E2E4F3;               color: #4a4faa; }
  .badge-question { background: rgba(180,130,0,0.1);   color: #7a5500; }
  .badge-care     { background: rgba(201,96,88,0.12);  color: #C96058; }

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
    background: rgba(30,20,20,0.04);
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

  /* Section accordion (collapsible metadata) */
  .section-accordion > summary {
    list-style: none;
    cursor: pointer;
    user-select: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 20px;
    font-weight: 700;
    color: var(--navy);
    padding-bottom: 10px;
    border-bottom: 2px solid var(--navy);
    margin-bottom: 1rem;
    font-family: 'Cigars', Georgia, serif;
  }
  .section-accordion > summary::-webkit-details-marker { display: none; }
  .section-accordion > summary::after {
    content: "▸ Show";
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--muted);
    flex-shrink: 0;
    margin-left: 0.75rem;
  }
  details[open].section-accordion > summary::after { content: "▾ Hide"; }

  /* Advisor cards */
  .advisor-card {
    background: var(--card);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.75rem;
  }
  .advisor-card h3 {
    font-size: 1rem;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 0.4rem;
  }
  .advisor-card p { font-size: 0.9rem; color: var(--text); }

  /* Action items */
  .action-items {
    list-style: none;
    padding: 0;
  }
  .action-items li {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 12px 4px;
    border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
  }
  .action-items li:last-child { border-bottom: none; }
  .action-items input[type=checkbox] { margin-top: 4px; flex-shrink: 0; cursor: pointer; width: 15px; height: 15px; }
  .action-number {
    background: #C96058;
    color: #FFFDF8;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
  }
  .owner-tag {
    display: inline-block;
    background: #E2E4F3;
    color: #4a4faa;
    border: 1px solid #C8CBE8;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    margin-left: 6px;
    white-space: nowrap;
  }

  /* Subsection content */
  .section > h3 {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--navy);
    margin: 1.25rem 0 0.5rem;
    padding: 0.4rem 0.75rem;
    background: rgba(30,20,20,0.04);
    border-radius: 4px;
  }
  .section > h3:first-of-type { margin-top: 0; }
  .section > ul {
    padding-left: 1.5rem;
    margin-bottom: 1rem;
    background: rgba(30,20,20,0.02);
    border-radius: 0 0 6px 6px;
    border: 1px solid var(--border);
    border-top: none;
    padding-top: 0.75rem;
    padding-right: 1rem;
    padding-bottom: 0.75rem;
  }
  .section > ul li {
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
    line-height: 1.65;
  }
  .section > ul li:last-child { margin-bottom: 0; }
  .section > p {
    font-size: 0.9rem;
    line-height: 1.65;
    margin-bottom: 1rem;
    background: rgba(30,20,20,0.02);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
  }

  /* Footer */
  footer {
    text-align: center;
    font-size: 0.75rem;
    color: #6B6357;
    padding: 2rem;
    border-top: 1px solid rgba(30,20,20,0.1);
    background: #F2E9E2;
    margin-top: 3rem;
  }
'''


def extract_content_from_html(html: str) -> dict:
    """Extract key content from modern template HTML."""
    
    data = {
        'title': '',
        'date': '',
        'school': '',
        'recording_url': '',
        'sections': [],
        'pills': [],
        'nav_items': []
    }
    
    # Extract title from <title> or <h1>
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        data['title'] = title_match.group(1)
    
    # Extract h1
    h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if h1_match:
        data['title'] = h1_match.group(1)
    
    # Extract main content sections - look for divs with data attributes or specific content structure
    # This is a simplified extraction - in practice you'd want more sophisticated parsing
    
    return data



def extract_sections_from_html(html: str) -> list[tuple[str, str]]:
    """Extract section ID and title pairs from HTML."""
    sections = []
    # Find all section tags with id and h2 titles
    section_pattern = r'<section[^>]*id=["\']s(\d+)["\'][^>]*>.*?<h[23][^>]*>([^<]+)</h[23]>'
    for match in re.finditer(section_pattern, html, re.DOTALL):
        section_num = match.group(1)
        section_title = match.group(2).strip()
        sections.append((section_num, section_title))
    return sections


def wrap_with_original_template(html_content: str, school_name: str, title: str, 
                                recording_url: str = '', date_str: str = '') -> str:
    """Wrap content with original template structure."""
    
    if not date_str:
        date_str = datetime.now().strftime('%B %d, %Y')
    
    # Extract main content between <main> tags
    main_match = re.search(r'<main[^>]*>(.*?)</main>', html_content, re.DOTALL)
    if not main_match:
        print("Warning: No <main> tag found")
        return html_content
    
    main_content = main_match.group(1)
    
    # Try to extract just the content sections (skip any sidebar/nav)
    # Look for .content div or just extract all sections
    content_match = re.search(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>\s*</main>', main_content, re.DOTALL)
    if content_match:
        content_only = content_match.group(1)
    else:
        # Fallback: get all section tags
        sections = re.findall(r'<section[^>]*>.*?</section>', main_content, re.DOTALL)
        content_only = ''.join(sections)
    
    # Extract section info for TOC
    sections_info = extract_sections_from_html(content_only)
    if not sections_info:
        sections_info = [(str(i), f'Section {i}') for i in range(1, 9)]
    
    # Generate TOC
    toc_items = []
    for sec_num, sec_title in sections_info:
        toc_items.append(f'      <a href="#s{sec_num}">{sec_num} — {sec_title}</a>\n')
    toc_html = ''.join(toc_items)
    
    recording_button = ''
    if recording_url:
        recording_button = f'''<a class="recording-link" href="{recording_url}" target="_blank">&#9654; Fathom Recording</a>'''
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | NSLS Roadshow</title>
  <!-- Inter from Google Fonts. Add your Adobe Fonts kit <link> here to enable Cigars. -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&display=swap" rel="stylesheet">
  <style>
{ORIGINAL_CSS}
  </style>
</head>
<body>

<header class="page-header">
  <div class="header-inner">
    <div class="header-pills">
      <span class="header-pill">NSLS Society Roadshow</span>
      <span class="header-pill">{date_str}</span>
    </div>
    <h1>{title}</h1>
    <div class="header-buttons">
      <a class="header-btn" href="../index.html">&larr; {school_name} Hub</a>
      {recording_button}
    </div>
  </div>
</header>

<main>
  <aside class="toc-sidebar">
    <nav class="toc-nav">
      <div class="toc-heading">Contents</div>
{toc_html}    </nav>
  </aside>
  <div class="content">
{content_only}
  </div><!-- /.content -->
</main>

<footer>
  Generated by Society Roadshow Reporting System &nbsp;·&nbsp; {date_str}
</footer>

</body></html>'''
    
    return html


def reformat_school_reports(school_slugs: list[str], base_path: str = '/Users/chrishigbee/Desktop/Campus Roadshow/report/schools'):
    """Reformat meeting reports for specified schools."""
    
    base_path_obj = Path(base_path)
    
    for school_slug in school_slugs:
        school_dir = base_path_obj / school_slug
        meetings_dir = school_dir / 'meetings'
        
        if not meetings_dir.exists():
            print(f"⚠️  No meetings directory for {school_slug}")
            continue
        
        # Get all meeting HTML files
        meeting_files = sorted(meetings_dir.glob('meeting-*.html'))
        
        for meeting_file in meeting_files:
            print(f"📝 Reformatting: {meeting_file.name}")
            
            # Read current file
            with open(meeting_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Extract metadata
            title_match = re.search(r'<title>([^<]*)</title>', html_content)
            title = title_match.group(1) if title_match else 'Meeting Report'
            
            recording_match = re.search(r'href=["\']https://fathom\.video[^"\']*["\']', html_content)
            recording_url = recording_match.group(0).split('href="')[1].split('"')[0] if recording_match else ''
            
            # Extract date from filename
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', meeting_file.name)
            if date_match:
                from datetime import datetime as dt
                date_obj = dt.strptime(f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}', '%Y-%m-%d')
                date_str = date_obj.strftime('%B %d, %Y')
            else:
                date_str = datetime.now().strftime('%B %d, %Y')
            
            # Clean school name for display
            school_display = school_slug.replace('-', ' ').title()
            
            # Wrap with original template
            reformatted_html = wrap_with_original_template(
                html_content,
                school_name=school_display,
                title=title,
                recording_url=recording_url,
                date_str=date_str
            )
            
            # Write back
            with open(meeting_file, 'w', encoding='utf-8') as f:
                f.write(reformatted_html)
            
            print(f"  ✓ Updated with original template")


if __name__ == '__main__':
    # Schools to reformat (6 new ones that need original template)
    new_schools = [
        'texas-lutheran-university',
        'central-wyoming-college',
        'madison-area-technical-college',
        'south-piedmont-community-college',
        'austin-peay-state-university',
        'western-governors-university'
    ]
    
    print("🎨 Reformatting meeting reports to original Cigars/cream template...\n")
    reformat_school_reports(new_schools)
    print("\n✅ Reformat complete!")
