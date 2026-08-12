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
| Airtable CRM has drifted badly out of sync | **Open** — see §5 |
| Platform consolidation has no key finding despite being a 5-school pattern | **Open** — see §4 |
| AI Coach heatmap row undercounts | **Open, accepted** — see §4 |
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

### Platform consolidation has no key finding
It's a **5-school pattern** — Madison Area Tech, Mott CC, Muskingum, Texas A&M Corpus Christi,
UAlbany — which is more schools than "SNT friction" (5 chips) or "non-completion" (3 chips), both
of which *do* have findings. Looks like a genuine hole in the report's narrative. Not written
because a new key finding is a cross-report editorial call, not a mechanical fix.

### Ideas grid ordering
Ranked by school count descending, ties broken by signal strength (unprompted > prompted, specific
request > vague frustration). **Cards past roughly #19 are appended chronologically and are not
strictly sorted** — that tail is intentional drift, don't "fix" it by re-sorting the whole grid.

---

## 5. Airtable CRM drift (open)

Base `app5rj9bOGQNFoIoD` was meant to hold this data in queryable form. **It has fallen out of sync.**

As of 2026-08-12:
- **`Meetings` stops at 2026-05-04 (Dartmouth).** Every school added since — roughly a dozen,
  including Columbia Southern, Coastal Carolina Graduate, Southern Miss, SUU, Youngstown, Alvin,
  La Roche, Johnston, Northeast Lakeview, Texas A&M, Lehigh, UAlbany — has **no Meetings record**.
- **7 `Target Schools` records are stubs** carrying only School Name + CS Rep: UAlbany, Southern
  Mississippi, Lehigh, Columbia Southern, Youngstown State, Bryan College, Southern Utah.
  Fully-populated records have ~14 fields (Enthusiasm, Location, Key Signal, Pilot Partner,
  Chapter Status/Type, Champion Potential, Interview Date, Roadshow URL).
- **`Roadshow Report URL` values still point at `v0-deploy-campus-roadshow.vercel.app`**, not
  `roadshow.nsls.org`.
- **UAlbany's `CS Rep` points at Sari Khatib**, who is the school's advisor, not the CS rep
  (Alexis Scott). `Primary Contact` is empty. Worth auditing whether other records share this.

Nothing in the pipeline writes to Airtable — `generate_school.py` has `--airtable-school-id` and
`--airtable-contact-ids` flags that push a couple of fields, but the survey token is scoped
`data.records:read` and the CRM is otherwise maintained by hand. **That's the root cause: there is
no automated sync, so it drifts whenever someone adds a school without also updating Airtable.**

Backfilling is a real task, not a cleanup. Decide whether the CRM is genuinely the query layer
(then it needs a sync script) or has been superseded by the site itself (then stop maintaining it).

---

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
