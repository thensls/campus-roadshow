# Society Pilot Feedback — Working Context & Full Record

_Source of truth for the Society pilot feedback report. Last updated: 2026-07-10._

## Context

I'm Chris, VP of Product at NSLS. This file is the reference for the Society pilot feedback report.

**What exists**

- Consolidated feedback report: `/Users/chrishigbee/Desktop/Campus Roadshow/report/society-feedback.html` — a single-file filterable HTML page matching the Campus Roadshow site design (roadshow.nsls.org), wired into the main report's tab bar via `report/index.html`.
- Filters: School, Product Area, Type (Praise/Complaint/Idea), Audience (Student vs Faculty/Staff). Sortable columns (default School A→Z). Stat tiles: Total, Respondents, Schools. A "Recurring Themes" band with per-theme narrative synopses and drill-down links.
- Airtable copy: base `app5rj9bOGQNFoIoD`, table `Society Pilot Feedback` (`tbljNa341i5cXLrK9`). The HTML and Airtable are kept **static** — no auto-sync; update both by hand when new feedback arrives.

**Data model** (per item): School, Respondent, Role, Audience (Student / Faculty-Staff), Product Area, Type (Praise/Complaint/Idea), feedback text, source email link (links live in the HTML + Airtable, not this file).

**Current totals:** 109 items · 16 respondents · 7 schools · 49 Complaints, 37 Ideas, 23 Praise.

**Product areas used:** Onboarding, Personal Insights / Assessments, Coach Chat, Career Clarity, Platform / UX, Visual / Content, Content / Compliance, Overall.

**To add new feedback:** parse the email/doc into item(s), classify each by area + type + audience, add to the `FEEDBACK` array in society-feedback.html (verify with `node --check`), add matching records to the Airtable table, and update this file (then re-upload it to the project as knowledge).

---

## Full verbatim feedback (109 items, grouped by school → respondent)

### Arapahoe CC

**Dan Balski** — Advisor (Faculty / Staff)

- [Complaint / Visual / Content] Noticed a lack of NSLS branding throughout the site.
- [Idea / Coach Chat] Where is it noted that the 'Career Coach' isn't an actual person? Add somewhere that describes what the Coach is.
- [Complaint / Onboarding] Profile 'Ages' has no under-18 option — they have concurrent-enrollment students under 18. Is access to Society age-limited?
- [Idea / Onboarding] 'Duration for Jobs' — unclear how to handle partial years (e.g., 2.5); add guidance on whether to round up or down.
- [Complaint / Personal Insights / Assessments] While filling the four quadrants, was never asked about 'Personal Network' or 'Professional Network' — are these not built yet?
- [Complaint / Personal Insights / Assessments] Personality questions felt forced — most pitted a plain option against a statement containing the word 'emotions'; balance the wording.
- [Complaint / Visual / Content] A weird animated graphic on the 'Social Situations' results — the shirt moved in an odd way.
- [Complaint / Personal Insights / Assessments] Strengths — unclear whether to select from the text-bubble options or type your own; at first assumed he had to select.
- [Complaint / Platform / UX] Not obvious you can scroll the Strengths text bubbles further to the right.
- [Complaint / Platform / UX] Didn't realize you could scroll down in Inspirations/Strengths for 2 more options (thought there were only 6) — could skew results.
- [Idea / Platform / UX] Values — add a counter of how many you've selected, instead of scrolling back to the top to check.
- [Complaint / Personal Insights / Assessments] Duplicative Values text — 'Compassion: showing kindness to others' overlaps with a separate 'Kindness' value; don't use one value inside another's definition.
- [Idea / Platform / UX] The progress tracker only covers Career Clarity — unclear how much overall profile work remains; consider an overall completion indicator.
- [Complaint / Career Clarity] Financial Needs — unclear what 'total monthly housing cost' includes (rent + utilities?); a Utilities section appeared later. Ask them together or clarify housing = rent/mortgage only.
- [Complaint / Platform / UX] Dream Job forced clicking 'Open to any industry' to continue (not what the prompt implied); same with 'Nothing to share' and another screen — not intuitive.
- [Complaint / Coach Chat] In Dream Job, the coach shifts to 'Dan has…' language instead of 'You have…' — jarring vs the otherwise 'you'-focused voice.
- [Complaint / Coach Chat] Career Statement — the Coach said he could edit his statement, but editing doesn't actually work.
- [Complaint / Platform / UX] Set a goal for July 5, the card changed it to July 7, and he couldn't edit the date back — bug.
- [Complaint / Coach Chat] Raised an AI / environmental-impact question (per the forwarding email) and wants guidance on how to address it with students.

**Jessica Horning** — Advisor (Faculty / Staff)

- [Complaint / Visual / Content] Odd that there isn't any NSLS branding on the site.
- [Complaint / Onboarding] Education step bumps you back to the form; the college logo made her think her info wasn't accepted — enlarge the confirmation or add a button asking if you need to add more education info.
- [Complaint / Visual / Content] Motion on the graphics is a bit creepy (Personal Growth section).
- [Praise / Personal Insights / Assessments] Loves the personality assessment results.
- [Complaint / Personal Insights / Assessments] Wishes the personality results went into more detail — the answer choices were limited and left little room for nuance.
- [Complaint / Career Clarity] Housing costs — unclear whether it's asking what you can spend or what you currently spend.
- [Idea / Career Clarity] Can't hit Continue on the career-suggestions list until choosing one — what if students want to keep options open? Allow selecting more than one.

### Central Wyoming College

**Lisa Appelhans** — Advisor (Faculty / Staff)

- [Praise / Overall] Went through the Society program; found it interesting and believes students will realize many benefits from learning about themselves.

### Drew University

**Anonymous tester (via C. Gonzalez)** — Staff (Faculty / Staff)

- [Praise / Career Clarity] "So accurate — much more than any other site I've used." Dream Job returned Community Engagement Specialist (with Graphic Designer second), which felt spot-on.

**Anonymous student (via C. Gonzalez)** — Student (Student)

- [Idea / Personal Insights / Assessments] Disliked getting a new question only after answering the prior one — would prefer all questions (or ~10 per section) shown together as a scrollable list.
- [Complaint / Visual / Content] Found the attached images distracting and unhelpful for answering — the contrast between plain text and the colorful, clay-like images was jarring.
- [Complaint / Coach Chat] Didn't find the open-ended responses helpful. (Note: this comment was cut off in the source and may be incomplete.)
- [Praise / Career Clarity] Really enjoyed the financial aspect and how it calculated an 'enough' income.
- [Complaint / Platform / UX] Unclear what the final product/outcome was supposed to be.

**Cassandra Gonzalez** — Career Services (Faculty / Staff)

- [Praise / Onboarding] Intro to the Clarity path was straightforward; the nickname step is a nice touch, and it was easy to enter education and work experience.
- [Idea / Platform / UX] The assessment felt long and fatiguing, and it was unclear whether progress would save on exit — add a save button and a 'you don't have to finish in one sitting' disclaimer.
- [Idea / Platform / UX] Add an overall progress tracker (left side) showing how much is left before reaching the 'dream job.'
- [Idea / Coach Chat] Add suggested prompts to the in-between coach chats — would have used them more.
- [Complaint / Personal Insights / Assessments] Personal Insights felt off — unlimited options and vague descriptions made accuracy unclear, and choices were repetitive (e.g., emotions vs. analytical) compared with more discrete personality tests.
- [Idea / Personal Insights / Assessments] Offer more choices on the single-word-selection questions.
- [Idea / Personal Insights / Assessments] The Values list is missing core values (e.g., 'Love') — add more options or a write-in blank.
- [Complaint / Career Clarity] Financial Needs Summary ignores splitting costs with a partner and expenses like school/childcare, and it's unclear whether students enter current or future 'realistic' expenses — needs more thought.
- [Idea / Career Clarity] Let users select more than one dream job / provide more dream-job options — many are open to multiple paths.
- [Complaint / Platform / UX] The flow ended abruptly at the coach chat — expected a 'congratulations, first step' moment or a clear transition after such a long process.
- [Praise / Career Clarity] Found the 'ideal work environment' and 'living environment' results really interesting.
- [Praise / Career Clarity] Loved the career statement.
- [Praise / Coach Chat] Likes the 'Ask your coach' suggestions on the dashboard.

**Kim Giorgio** — Career Services (Faculty / Staff)

- [Complaint / Onboarding] After signing in, the 'Continue' button was buried too low on the screen and not immediately obvious.
- [Complaint / Platform / UX] The dashboard appears optimized for mobile rather than desktop, making it less intuitive on a computer.
- [Complaint / Platform / UX] The overall experience felt very long and hard to finish in one sitting; lost focus and engagement by the Career Clarity section.
- [Complaint / Visual / Content] Photo captions in the Strengths & Inspirations section were extremely hard to read, especially after the second click-through — improve contrast/font size.
- [Praise / Personal Insights / Assessments] Really liked the Values Exercise and the way it broke down and explained personal values.
- [Idea / Onboarding] Auto-parse the Work Information section from an uploaded résumé instead of requiring manual entry.
- [Complaint / Coach Chat] The Career Clarity chat lacked guidance — often didn't know what to ask or how to engage effectively.
- [Idea / Coach Chat] Reduce reliance on fully open-ended AI chat — add guided prompts, suggested responses, multiple-choice pathways, and examples, especially for students new to self-reflection.
- [Idea / Career Clarity] Goal-setting is too open-ended — provide goal categories/pathways (Career, Academic, Financial, Personal Development, Wellness).
- [Idea / Career Clarity] The financial section may confuse students — add sample budgets, guided budget-building, and educational content before asking for inputs.

### Johnston CC

**Olivia Reitmann** — Student (Student)

- [Complaint / Platform / UX] Website is buggy on mobile — images slow to upload, framing suboptimal, scrolling stifled.
- [Complaint / Onboarding] Age 17 was not a selectable option; had to choose 19 because 18 wasn't available either.
- [Complaint / Personal Insights / Assessments] Assessment felt monotonous, time-consuming, and predictable; binary multiple-choice reinforces bias and didn't capture full personality.
- [Idea / Personal Insights / Assessments] Condense the assessment and add more write-in/open-response questions instead of stereotype-enforcing multiple choice.
- [Complaint / Visual / Content] Doesn't care for the chat option; artwork should be made by a real artist, not AI — the added 'motion' was clunky and unsettling.
- [Complaint / Career Clarity] Suggested careers weren't inspiring or related to her passions; entered her own dream career and left with no new insight. Feels the algorithm lacks the insight a human mentor provides.

**Tiffany Ruiz** — Faculty (Faculty / Staff)

- [Praise / Overall] "A wonderful tool — I wish I'd had it when I was younger, and still find it beneficial at any stage." Didn't notice anything to fix.
- [Praise / Coach Chat] Enjoyed the interaction throughout the question portion; believes it will be truly helpful for those who fully engage with the AI.

**Shelby Anderson** — Student (Student)

- [Praise / Onboarding] Getting started was straightforward and easy to work with. Overall liked it.
- [Idea / Personal Insights / Assessments] Either-or answers don't fit; add a 'both' option or fill-in-the-blank since responses vary by situation.
- [Idea / Platform / UX] Label the 'back' arrow — worried clicking it would erase her progress.
- [Idea / Coach Chat] Auto-generate starter prompts for the Coach Chat (struggled to come up with a question); add tabs so multiple topics don't get mixed up.
- [Idea / Career Clarity] Add help understanding costs for people who aren't good with prices.
- [Idea / Platform / UX] Show estimated time to complete each section — the process took longer than expected.

**Kessler Holmes** — Student (Student)

- [Praise / Overall] Brief positive impression — flagged as a potential pull-quote candidate.

**Megan Shaner** — Advisor (Faculty / Staff)

- [Praise / Coach Chat] Really enjoyed the tools and the interaction with the AI coach; tonally appropriate, bridging college and career. (Set July 15 feedback timeline.)

### Muskingum University

**Melissa Hartley** — Staff (Faculty / Staff)

- [Praise / Overall] "Thorough and comprehensive — really all-encompassing." Her favorite assessment of this kind so far, because of how in-depth it is and how many resources it pulls from.
- [Idea / Career Clarity] The 'enough' income from monthly expenses isn't tied to the Dream Job description — there should be a correlation, since a dream job might not support the life you want or need to survive.
- [Idea / Career Clarity] Multiple dream jobs are shown but you can only pick one — let students choose their top 2 for comparison.

**Amy Nestor** — Staff (Faculty / Staff)

- [Praise / Coach Chat] Really enjoyed the Career Coach module — very easy to use and does a great job covering the major areas of self-understanding and career exploration.
- [Complaint / Career Clarity] Students often lack the life/work experience to answer meaningfully — e.g., as a student she'd have picked an office environment just because it's all she knew, though she might have thrived somewhere hands-on.
- [Complaint / Career Clarity] Financial section may feel overwhelming or discouraging — most students underestimate housing/living costs. Wondered whether the AI coach recognizes that and offers guidance/context.
- [Idea / Coach Chat] The AI coach should proactively add explanation/context within the summaries instead of waiting for the student to ask — many students won't realize they should dig deeper or know what to ask.
- [Praise / Overall] A very detailed, thoughtful inventory; likes the focus on connecting strengths, values, personality, career interests, and wellbeing to build student confidence and clarity.
- [Complaint / Personal Insights / Assessments] Her personality result was a little off (labeled extrovert; she's an introvert). Appreciated the coach's note that assessments aren't always accurate, but worries students will accept results at face value without challenging them.

### SPCC

**Dr. Marsha Thomas** — Dean (Faculty / Staff)

- [Praise / Onboarding] Welcome flow quick and easy; personality type outcome given and can be saved to profile.
- [Praise / Coach Chat] Coach Chat generates a clear, multi-section response with a good follow-up question; strong opportunity to 'dig deep' to unpack results.
- [Praise / Personal Insights / Assessments] Loves the variety of assessments; consistent structure across sections works well.
- [Complaint / Personal Insights / Assessments] Problem-solving section can feel predictable/redundant — users may get bored and click without thinking.
- [Praise / Career Clarity] Appreciates the financial-needs section; '5 dream jobs' is a good starting point; the career statement is a powerful, reusable output for cover letters.

### UNT

**Sydney Pickett** — Advisor (Faculty / Staff)

- [Idea / Onboarding] Does 'Job Experience' have to be required to move forward? Consider making it optional in bio-building.
- [Complaint / Onboarding] Needs clarification on what 'Career Clarity', 'Professional Network', 'Personal Network', and 'Job Acquisition Confidence' actually mean.
- [Complaint / Onboarding] Unclear whether students are auto-enrolled into bio-building at signup or it's optional — worried students will drop off if forced into the survey automatically.
- [Idea / Platform / UX] Add a break between bio-building and the insights survey.
- [Idea / Personal Insights / Assessments] Two options per question feels oversimplified; three options would provide more depth.
- [Idea / Personal Insights / Assessments] Add an overview page explaining each assessment and what it measures, so users don't have to ask the coach mid-flow.
- [Idea / Personal Insights / Assessments] Clarify that results reflect a work setting — answers can shift back and forth depending on context.
- [Idea / Personal Insights / Assessments] Add a disclaimer that personality types can change based on your current state of mind.
- [Idea / Coach Chat] Provide prompting questions to help users interpret the personality tests (raised repeatedly across sections).
- [Complaint / Personal Insights / Assessments] Strengths: unclear whether to write in tasks you're good at or only select from what's given.
- [Idea / Personal Insights / Assessments] Add more options to select from in the Strengths section.
- [Praise / Personal Insights / Assessments] The strengths the assessment came up with were very accurate!
- [Complaint / Content / Compliance] Social-justice-advocacy terminology in Inspirations may conflict with Texas SB17 — student orgs may be protected, but this needs checking.
- [Complaint / Coach Chat] Asked a career-paths question (philosophical inquiry + social impact), hit a long buffer, and got no answer the first time; a retry worked — latency/reliability issue.
- [Praise / Personal Insights / Assessments] Values was the most interesting section — narrowing down the options was more engaging than a normal assessment.
- [Idea / Career Clarity] After the Work Environment assessment, show how it's relevant to the workplace and how to tell whether a potential employer fits your preferences.
- [Complaint / Career Clarity] Living Environment's 'what type of scene' is vague — add options clarifying what's being asked.
- [Idea / Career Clarity] Costs: add tips/explanation for calculating housing costs — many students don't know what it costs to live on their own.
- [Complaint / Career Clarity] Confused whether 'total monthly housing cost' means rent only or all expenses (groceries, gas, insurance, phone).
- [Idea / Career Clarity] Dream Job: let users see info from multiple options instead of choosing just one — undeclared students may want to compare.
- [Idea / Career Clarity] Use the Career Statement step to have students reflect on the values surfaced earlier.
- [Complaint / Career Clarity] Career statement didn't sound like her (vocabulary) — let students personalize before the coach fully drafts it, or warn them to personalize.
- [Complaint / Career Clarity] Career statement needs more context specific to the chosen career — hers mentioned higher education only once and education twice.
