# Campus Roadshow — Maintenance Notes

Context for anyone maintaining this repo. Records **why** things are the way they are, what's
known-broken, and which decisions were deliberate — the things that aren't recoverable from
the code or the commit log alone.

Last substantive update: **2026-08-12**.

---

## 1. What this is

A stakeholder-facing report site built from Fathom recordings and Airtable survey responses.
One page per school, timestamped to the actual recording, plus cross-school synthesis
(key findings, feature-demand heatmap, ideas grid, map).

| Thing | Where |
|---|---|
| Live site | https://roadshow.nsls.org |
| Repo | `thensls/campus-roadshow` (GitHub **org** repo) |
| Vercel project | `v0-deploy-campus-roadshow`, team **`nsls`** |
| Deploy root | `report/` |
| Airtable CRM | base `app5rj9bOGQNFoIoD` ("Campus Discovery CRM") |
| Skill | `~/.claude/local-plugins/nsls-builder-toolkit/skills/campus-roadshow/SKILL.md` |

The site is **not** a plain static build: it has serverless functions in `report/api/` and sits
behind NSLS Auth (OIDC). An anonymous fetch of the live URL 302s to `auth.nsls.org`, so
**you cannot verify a deploy by curling the page.**

---

## 2. Deploying — read this first

**Merging a PR does not deploy anything.** Vercel has no Git integration on this project
(zero Preview deployments in its entire history; `vercel project inspect` shows no linked repo).
Shipping is two independent actions:

```bash
git push / gh pr create / gh pr merge      # versions the work only
cd report && npx vercel --prod --scope nsls   # actually updates the live site
```

`--scope nsls` is **mandatory**. The CLI silently defaults to a personal account; in that state
`vercel whoami` returns `Not authorized`, and `vercel --prod` can create a stray personal project
that reports success while roadshow.nsls.org never changes. Check `npx vercel whoami` first.

Verify a deploy landed with `npx vercel inspect <url> --scope nsls` — expect `target production`,
`status ● Ready`, and `roadshow.nsls.org` in the alias list.

### Why Git integration isn't connected
Connecting it needs the Vercel GitHub App installed on the **`thensls` org**, which is owner-only.
Repo `ADMIN` is not enough, so a member's attempt becomes a permission request. Owners:
`bevans-nsls`, `juancarlosmaggi`, `kkimnsls`, `kprentiss`, `lauren-prentiss`, `red-akasha`.

**Decision (2026-08-12): deliberately not pursued.** Preview deployments — the main benefit —
are already available without it via `npx vercel --scope nsls` (no `--prod`). Auto-deploy-on-merge
would also remove explicit control over when stakeholders see changes. Revisit if a second person
starts maintaining this, since the merge-does-not-deploy trap is easy to fall into.

**Recommended flow:** deploy a preview, eyeball it, then promote.

---

## 3. Known-broken / known-stale

| Issue | Status |
|---|---|
| Airtable CRM had drifted badly out of sync | **Tooling fixed** 2026-08-12 (`sync_airtable.py`) — see §5 |
| Contacts + Champion Potential | Synced 2026-08-12 (35/39) — see §5 |
| Platform consolidation had no key finding | Added 2026-08-12 (PR #18) — see §4 |
| AI Coach heatmap row undercounts | **Open, accepted** — see §4 |
| Five legacy Product Insights records, no attribution | Retired 2026-08-12 — values recorded in §5 |
| Implementation Complexity / Category / Times Mentioned blank | Filled 2026-08-12 — Priority Score computes across all 27; see §5 |
| Society Feedback page and Airtable drifted 56 entries apart | Reconciled + automated 2026-08-12 (PR #31) — see §5 |
| Concerns & Objections effectively abandoned (8 records, 3 schools) | **On trial** — triage-on-add for the next 3 schools; see §5 |
| Feedback page is source of truth for hand-entered data | **Open, deferred** — inversion documented with a trigger; see §5 |
| Generator maintained counts it should not own | Fixed 2026-08-12 (PRs #9, #7, #23) — see §4 |
| Two heatmap rows had 11 dots vs 39 columns | Fixed 2026-08-12 (PR #10) |
| Map title hardcoded, went stale every addition | Fixed 2026-08-12 (PR #7, automated in PR #9) |
| Card sorting silently never worked | Fixed 2026-08-12 (PR #9) |
| School Agent card: 16 claimed vs 15 attributions | Fixed 2026-08-12 (PR #12) — UTRGV had a chip but no attribution |

---

## 4. Editorial decisions worth knowing

### The generator does not do the editorial work
`generate_school.py` prints `[OK] Applied editorial updates` after updating the heatmap, quotes
and school card. **It does not touch the Key Findings.** The success message is misleading —
UAlbany shipped without appearing in any finding because of it (fixed in PR #8). Always check.

### Key Finding chips are evidence-selective, not exhaustive
A school belongs on a finding only where its transcript supports it. Lehigh appears on one of five.
Do not add a new school to every finding — that fabricates evidence.

### The AI Coach heatmap row is a floor, not a true count
PR #10 repopulated two never-maintained heatmap rows from attributions already curated on the site
(key-finding chips + ideas cards). That works for **Outcomes & Reporting**, but under-counts
**AI Coach & Nudges**, because:

> The heatmap row measures demand for a **core feature**, but the ideas grid only carries cards for
> **specific enhancement requests**. A school that enthusiastically received the AI coach without
> asking for a change to it has no card to be attributed to.

This is not hypothetical — it wrongly flipped Madison Area Tech and Muskingum to empty, both
corrected in PR #12 after checking their reports (both recorded "**Strong**").

**Do not fix this by keyword-grepping the reports.** 38 of 39 mention the AI coach, because it's
demoed on every call. "Mentioned" ≠ "wanted". Getting the row genuinely right needs a per-school
read of all 39 reports. **Decision (2026-08-12): deferred, accepted as a known floor.**

### Third-party assessment integration may deserve its own idea card
UAlbany sits on *Personality Assessment Enrichment*, but its ask is different in kind from the
others on that card:
- Mott / UNLV — **interpretation**: make Society's own assessment results legible to students.
- UAlbany — **integration**: recognise Gallup StrengthsFinder, which the campus already runs, so
  Society consolidates a student's self-knowledge rather than adding a competing profile.

Sharing one card for now. Split it if a second school raises integration. It also connects to the
platform-consolidation theme below.

### Platform consolidation — added as a key finding (PR #18)
Added 2026-08-12 at position 5. **Four schools, not the five an earlier keyword grep suggested** —
Mott was a false positive whose only hit was "consolidate into the full meeting *record*", about
meeting notes rather than platforms. Each school was verified against its transcript before
inclusion. This is the same "mentioned ≠ meant" trap documented for the AI Coach row below; a
grep found it, reading it did not.

The finding grades its evidence rather than flattening it: **Texas A&M Corpus Christi** and
**UAlbany** are the strong cases and both named the need *unprompted before the feature was
shown*; **Madison Area Tech** and **Muskingum** are narrower, about consolidation inside the SNT
workflow rather than campus-wide platform overload.

### Watch for the generator maintaining numbers it should not own
Three separate bugs this session were the same shape: `generate_school.py` quietly maintaining a
count that is not derivable from the thing it was adding.

| Number | What went wrong | Fix |
|---|---|---|
| Map array entry | Never written at all — school silently absent from the map | Generator now writes it, given `--lat`/`--lng` (PR #9) |
| `"N Schools, Coast to Coast"` | Hardcoded literal, stale on every addition | Derived from the school-card count (PR #7 / #9) |
| `data-total-invited` | **Incremented on every school added** | Auto-bump removed; hand-maintained (PR #23) |

The third is the instructive one. `data-total-invited` is the **planned** school count — the
denominator of "39 of 40 schools met" — not a tally of schools written up. A school being added
was almost always already on the invite list, so bumping double-counted it and the ratio drifted
upward forever: 39/41, 40/42, 41/43, permanently understating progress against plan.

**Rule of thumb:** if a number describes the *plan* or the *whole collection*, the generator
should either derive it from the collection or not touch it. It should only own numbers that
follow directly from the single school being added.

### Ideas grid ordering
Ranked by school count descending, ties broken by signal strength (unprompted > prompted, specific
request > vague frustration). **Cards past roughly #19 are appended chronologically and are not
strictly sorted** — that tail is intentional drift, don't "fix" it by re-sorting the whole grid.

---

## 5. Airtable CRM — the query layer

Base `app5rj9bOGQNFoIoD` ("Campus Discovery CRM") is where this data gets analysed. **The site is
the source of truth; Airtable mirrors it.**

### Keeping it in sync
```bash
python3 Scripts/sync_airtable.py             # dry run (default)
python3 Scripts/sync_airtable.py --execute   # apply
```

Idempotent upsert across Target Schools, Meetings, Quotes and Executive Findings.
**Run it after every school addition** — it is Stage 6 of the pipeline, not a periodic chore.
Skipping it is exactly how the CRM ended up four months stale: as of 2026-08-12 the `Meetings`
table stopped at 2026-05-04, 19 schools had no meeting record, 12 had no school record at all,
6 more were empty stubs, and one Executive Finding still read *"across 19 schools"*.

### Read the dry run — it is not a formality
On first use it caught four things that would have damaged the CRM:
- **Two data-corrupting matches.** Substring matching mapped "Texas A&M University" onto the
  *Corpus Christi* record, and "Coastal Carolina University — Graduate" onto the *undergrad*
  record. Substring matching is now removed entirely.
- **A duplicate-in-waiting.** Airtable holds the typo "University of Texas, Rio **Grand** Valley",
  so the matcher missed it and would have created a second UTRGV.
- **A name regression.** The sync would have overwritten Airtable's correct "Austin Peay **State**
  University" with the site's typo "Austin Peay University".
- **A dropped finding.** The WGU finding is `class="exec-finding risk"`; a regex matching only the
  bare class missed it and reported it as an orphan.

### Invariants the script encodes — don't undo them
- **No substring matching on school names.** Use `NAME_ALIASES` for genuine equivalences.
- **`School Name` is never written on update**, only on create. The site is not always the better
  source of a school's own name.
- **Collision detection aborts the run** if two site schools resolve to one Airtable record,
  rather than letting one silently overwrite the other.
- Orphaned Airtable findings are **reported, never deleted** — a human judges them.

### Superseded — do not run
`backfill_target_schools.py`, `backfill_intel.py`, `backfill_report_content.py` were one-shot
backfills. **`backfill_intel.py` creates Quotes and Findings unconditionally**, so running it now
duplicates every quote and finding. `sync_airtable.py` replaces all three.

### Contacts and Champion Potential
Synced as of 2026-08-12. `Champion Potential` on Target Schools is a **lookup** through
`Primary Contact` → Contacts, so it cannot be written directly — it populates once the contact
link exists. Coverage is now 35/39; the rest are schools whose hub page carries no champion tile.

Two rules the sync applies here, both deliberate:
- **The champion tile is a school-level judgement but the field lives on a person.** It is written
  to the Primary Contact only, never duplicated onto a second advisor it was not made about.
- **Primary Contact is the survey respondent** where one exists (matching the Airtable field
  description), otherwise the first advisor listed on the hub page.
- **Ambiguous names are skipped, not guessed.** When a name matches more than one contact the
  sync warns and moves on rather than picking. This fired on a genuine "Lauren Breckenridge"
  duplicate, which was resolved by hand on 2026-08-12 (the bare record was deleted, the one
  carrying Champion Potential, email, title and the Texas A&M Corpus Christi Primary Contact link
  was kept). The guard stays — people dedupe far worse than institutions.

### Product Insights — mirrors the ideas grid
**Decision 2026-08-12: Product Insights is a mirror of the ideas grid**, not a feature-area
rollup. The sync creates unmatched cards, so all 24 ideas-grid cards now have a record and stay
current automatically.

**Feature Name, First Discussed, Also Discussed and Excitement Level** are written.
Feature Category and Implementation Complexity have no source on the site and stay manual.

**Excitement Level is derived**, not hand-set. Every meeting report has a Section 6
"Feature-Level Feedback" table — 439 rows across 44 reports, with a four-value vocabulary
(Strong / Positive / Open Question / Needs Care). Report labels are free text (381 distinct, only
3 exactly matching a card name), so `FEATURE_PATTERNS` maps them to cards by keyword family, one
pattern per card. A label may match several cards — "Career Readiness Score (Advisor Dashboard)"
genuinely speaks to both — and that is intended.

`grade_excitement()` is **breadth-aware on purpose**: a lone Strong mention grades Low, not High.
An earlier intensity-only rule disagreed with the hand-set values on 16 of 21 cards, all of them
thin-sample; adding breadth cut that to 13 and brought every low-n card into agreement. The
remaining differences are concentrated where evidence is *thickest* — Administrator Dashboard was
rated Medium while 37 schools discussed it and 22 called it Strong — because the hand-set values
date from when the base held ~19 schools. **Decision 2026-08-12: the derived value wins**, since
it reflects all 44 reports and re-derives on every run.

`Excitement Score (Numeric)` is an Airtable formula off Excitement Level — do not write it.
`Priority Score (Auto)` reads NaN/Infinity for four cards because **Implementation Complexity is
blank** on them: Entry-Level Pathways, Shareable Progress Summary, Student-Initiated Group
Formation, Skill-Level Outcome Data & NACE. Set Complexity by hand to make Priority compute.

`INSIGHT_ALIASES` maps an ideas-grid card onto an Airtable record named differently. Currently one
entry: the site's "Career Readiness Score" is Airtable's "Career Readiness Score & Outcomes
Dashboard" — confirmed the same concept because both carry First Discussed = *Cassandra Gonzalez ·
Drew University* and the identical downstream chain. `Feature Name` is never rewritten, so the
longer Airtable form is preserved deliberately.

**Retired 2026-08-12.** Five legacy records from the older coarse taxonomy were deleted once the
mirror decision made them redundant. Their values are recorded here so the judgements are not
lost — they were the only place some Implementation Complexity and Feature Category ratings
existed, and they may be useful when filling those fields on the current cards:

| Retired record | Category | Complexity | Excitement | Schools |
|---|---|---|---|---|
| AI Career Clarity (Clarity Track) | Career Clarity | Medium | High | Mott, UTRGV |
| LMS / Platform Integration | Accountability | High | High | Mott, UTRGV |
| Automated SNT Management | Accountability | Low | High | Mott |
| Cross-Institutional Peer Matching | Connections | Medium | Medium | Mott, St. John's |
| Alumni Mentor Matching | Connections | Medium | Medium | St. John's |

Product Insights is now 24 records, all carrying attribution — a clean mirror of the ideas grid.

*Historical note — what these were:* they carried a category and excitement level but no attribution, and
roughly duplicated the heatmap row names, which is what made the table mix two granularities.

### Product Insights fields filled by hand 2026-08-12
`Priority Score (Auto)` is `(Excitement × **Times Mentioned** × Adoption Driver) / Complexity`, so it
reads NaN until *three* fields are set — not just Complexity, which is the trap.

- **Times Mentioned** was derived from Section 6 signal counts (objective).
- **Feature Category** was classified against the existing vocabulary. Note it includes an
  **Integrations** option, which is where both integration cards belong.
- **Implementation Complexity** is an *estimate*. Where a retired legacy record covered the same
  class of work its value was reused as precedent: LMS/Platform Integration was High, so both
  integration cards are High; Cross-Institutional Peer Matching was Medium, so Student-Initiated
  Group Formation is Medium; AI Career Clarity was Medium, so Entry-Level Pathways is Medium.

**`Times Mentioned` is now derived** by the sync (2026-08-12) from Section 6 signal-row counts,
closing the drift risk. It is only written when signals exist — writing 0 for a card with no
Section 6 label would zero its Priority Score.

This **rebased the whole Priority column**. The prior hand-set values dated from the ~19-school era
and ran 1&ndash;4; derived counts run to 38, so scores moved by an order of magnitude (Career
Readiness Score 18 &rarr; 222). Ranking is what matters and the top is stable — Career Readiness
Score, Administrator Dashboard — but Personality Assessment Enrichment rose sharply on 35 real
mentions.

**Caveat:** for cards whose keyword family also catches *core-feature* discussion — Personality
Assessment Enrichment, School Agent — the count includes demo reception, not only the enhancement
ask. Same limitation as the AI Coach heatmap row. Treat those two as upper bounds.

<details><summary>Prior hand-set Times Mentioned values, for reference</summary>

| Feature | Was |
|---|---|
| AI Study & Career Prep Toolkit | 1 |
| Administrator Dashboard | 3 |
| Affinity-Based SNT Groupings | 1 |
| Alumni & Lifelong Membership Product | 1 |
| Campus Engagement Platform Integration | 4 |
| Career Readiness Score & Outcomes Dashboard | 3 |
| Entry-Level Pathways & Reverse-Engineered Career Steps | 1 |
| FOL Micro-Learning & Modular Content | 4 |
| Gamification & Friendly Engagement Nudges | 2 |
| Handshake Integration | 3 |
| In-Platform Events & Speaker Broadcasts | 11 |
| In-Platform Messaging & Event Communication Hub | 1 |
| Member Drop-off Analytics | 1 |
| Multi-Semester Analytics | 2 |
| Non-Member On-Ramp | 1 |
| Peer Chapter Benchmarking | 1 |
| Personality Assessment Enrichment | 1 |
| Platform-Driven Engagement Nudges | 2 |
| Quick-Pulse Student Feedback | 1 |
| SIS & Academic-System Integration | 4 |
| School Agent | 4 |
| School-Specific Onboarding Questions | 1 |
| Shareable Progress Summary for Career Services Handoff | 5 |
| Skill-Level Outcome Data & NACE Competency Reporting | 3 |
| Student Email Preferences | 2 |
| Student ID Field in the Platform | 1 |
| Student-Initiated & On-Demand Group Formation | 4 |

</details>

### Society Pilot Feedback — mirrors the feedback page
`report/society-feedback.html` is the source of truth; the Airtable table mirrors it. Synced as of
2026-08-12, after the two drifted **56 entries apart** — the page held 179, Airtable 123, and
Airtable was missing Columbia Southern, USM and UTK entirely. The page was a strict superset, so
reconciliation was a one-way backfill.

Two parsing notes for anyone touching `parse_feedback()`:
- The page array is **JavaScript, not JSON** — `link` is sometimes `GM+"threadid"` string
  concatenation — so it is parsed with a tolerant regex over the uniform object literals rather
  than `json.loads`.
- Entries are matched on the first 70 characters of normalised feedback text. There is no id on
  either side.

**`Source` is typed as `url` but does not hold URLs.** Feedback arriving as a PDF or forwarded
email has no thread link, so the sync leaves `Source` alone rather than blanking hand-entered
provenance such as *"Test-Drive Notes for Society (PDF, Kelby Nichols)"*. Airtable accepts the
text, but do not rely on the field being a link.

**Outstanding one-click fix:** change `Source` to single line text. The Airtable meta API refuses
field-type changes (`INVALID_REQUEST_UNKNOWN — Changing a field's type is not currently
supported`), so it must be done in the UI. The field description has been updated to say so.

### Concerns & Objections — on trial, not backfilled
**The table is an abandoned stub, not a curated asset.** As of 2026-08-12 it holds **8 records from
3 schools** (St. John's, UTRGV, Mott — all March meetings), **all still "Unresolved."** Nothing has
moved to In Progress or Resolved in five months, and 36 schools have never been entered.

An earlier read of this was wrong: the argument against importing was that ~163 untriaged bullets
would "bury the curated entries in noise." There are 8 entries, and no evidence anyone works the
queue.

The site *can* supply a concern's description, school and date — roughly 163 bullets across the
"What Raised Questions or Friction" sections. It cannot supply **Severity Level, Concern Category,
Resolution Status or Follow-Up Actions**, which are the fields that make the table worth querying
and are post-call human judgements.

**Decision (2026-08-12): do not backfill. Restart small instead.** Triage that school's 3&ndash;5
friction bullets as part of adding it, while the meeting is fresh. Run it for the next three
schools. If it gets used, backfill the history then; if it does not, retire the table having spent
an hour rather than a day. Adding 163 more rows will not create a habit that has not existed since
March.

Nothing is lost while this is on trial — every friction bullet is already visible in its meeting
report on the live site. What is missing is queryability, which so far nobody has used.

### The feedback page is the wrong source of truth (open, deferred)
Every other dataset here is **generated** — schools, meetings, quotes, findings and insights all
derive from Fathom transcripts and meeting reports, so the site is naturally upstream and Airtable
naturally mirrors it. **Feedback is not generated.** It is typed in from emails, PDFs and
conversations.

Making a static page the master for hand-entered data is precisely why the feedback sync needs a
regex parser for a JavaScript array, matches records on the first 70 characters of text because
neither side carries an id, and required a 56-entry reconciliation. Those are three symptoms of one
cause.

**Inverting it would remove all three at once:** Airtable becomes the source (real record ids,
forms for non-technical contributors, no parser) and `society-feedback.html` renders from it via an
API route — `report/api/` already exists and the site is already auth-gated.

**Deferred, with a trigger.** Do it when advisors start submitting student feedback regularly
rather than it arriving ad hoc through Chris. A second reconciliation would also be a signal that
the current direction is not holding.

**Known fragility until then:** editing the opening sentence of an entry on the page creates a
duplicate in Airtable instead of updating the existing record, because the match key is the text
itself.

## 6. Gotchas that cost real time

**Fathom has two different IDs.** `recording_id` (internal, transcript fetch only) and the
`/calls/{id}` public URL used for `?t=` links. They are different numbers for the same recording.
Never put `recording_id` in a `?t=` link, and never pass a `fathom.video/share/xyz` URL to the
transcript endpoint.

**Two Airtable record types in `Survey Responses`.** School-level summaries (~9 fields) look right
and produce an **empty survey page with no error**. Only individual respondent records (~27–33
fields) work. Always verify before running `generate_survey.py`.

**A dropped `</div>` renders the entire site blank.** The editorial pass drops the closing tag on
the *previous* school's quote card when inserting a new one. `generate_school.py` now warns, but
check `div depth == 0` before every deploy.

**Don't grep counts with wide context patterns.** `grep -oE '.{60}\b38\b.{60}'` requires 60
characters on both sides and silently misses matches near line ends — that's how the stale map
title survived a "no literal 38 remains" check. Use plain `grep '38'`.

**`gh pr merge` has no `-q` flag.** It errors out and prints help; the merge silently does not happen.

---

## 7. Per-school data lives in four places

Adding a school means all four stay in sync, or the numbers disagree:

1. **School card** — `data-*` attributes drive the computed stats in `tab-stats`
2. **Map array** — hand-maintained JS, separate from the cards (`generate_school.py` writes it as
   of PR #9, but only if you pass `--lat`/`--lng`)
3. **Heatmap column** — one `<th title="…">` plus one dot per row; every row must have
   `1 label + N schools + 1 total`, and the total must equal the filled count
4. **Ideas grid** — three things per card that must agree: the count in `idea-rank-basis`, a
   `idea-school-chip`, and an `idea-attr-person`

Verification snippets for all of these are in the `campus-roadshow` skill under
"Stage 2 — Verify Before Committing".
