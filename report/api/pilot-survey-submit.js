// Vercel serverless function — accepts a Fall Pilot Setup Survey submission
// and writes a record to the "Fall Pilot Setup Survey" table in the
// Campus Discovery CRM Airtable base (app5rj9bOGQNFoIoD).
//
// Requires the AIRTABLE_API_KEY env var to be set in the Vercel project
// (scope: data.records:write on app5rj9bOGQNFoIoD).

const BASE_ID = "app5rj9bOGQNFoIoD";
const TABLE_ID = "tbl6QCWcVrl6Wj9bc";

const FIELDS = {
  submissionLabel: "fld6hVRqZQdpy3shS",
  submittedAt: "fld2iaMxDnUEn5prY",
  school: "fldx7mlycv7b63qTe",
  schoolNameText: "fldTZKF1ce3ojNJUJ",
  respondentName: "fldkMpRsfdOQLjVSF",
  respondentEmail: "flduQIzWYS4b3dtUz",
  respondentRole: "fldi9LVhLn3FnKuNH",
  q1Planning: "fldV8k7U572EuoyOJ",
  q2Induction: "fldXXkMKkv5kNi2QH",
  q3Ltd: "fldwpyxq4RQnbMrZF",
  q3bCombinedEvents: "fldViKUF0h30Kgr5G",
  q4SntFormation: "fldecVHayD9g3ZcW9",
  q5MemberCounts: "fldvwFcOdgV6PzUy9",
  q5bInvitationListSize: "fld4K6EF4oXAjpVdc",
  q6StallStep: "fld6cmafT2eOwJDwP",
  q7SntPilotApproach: "fldNl5mOx97uv7mkA",
  q8ItConstraints: "fld2UitOtrmw0I1aD",
  q8bItConstraintDetails: "fldoWRsjvCjtvQ8Ba",
  q9Worries: "fldwdIcvjokFjRc8y",
  sourceUrl: "fldoApw17m0sSuWZr",
  userAgent: "fldiNz4lcRTv1jELi",
};

const SCHOOL_RECORD_IDS = {
  "arapahoe-community-college": "recskxIekBJtnu8FO",
  "austin-peay-state-university": "rec3FNVSKBZuSaYUp",
  "central-wyoming-community-college": "recKYHNiAfFNiNtlt",
  "coastal-carolina-university": "rectUbkpwbMAKdTZf",
  "drew-university": "recy9X7mP1Kp6cQsF",
  "madison-area-technical-college": "rechU5JkHaCV42uwq",
  "mott-community-college": "reclkpqZt967oCa7n",
  "muskingum-university": "recr63DLoYVZzxA7P",
  "south-piedmont-community-college": "recDQLrzobXjQi6Bf",
  "texas-am-corpus-christi": "recWxsbdXjVhGin9P",
  "texas-lutheran-university": "recnp929tLn96uD2M",
  "university-of-nevada-las-vegas": "recrUWHzIIrhYjt68",
  "university-of-north-texas": "recx0lJHx32QIM1G0",
  "university-of-tennessee-knoxville": "recgRPTHazNsUw1A7",
};

function trim(value, max = 100000) {
  if (value == null) return "";
  return String(value).slice(0, max).trim();
}

function pickSingleSelect(value, allowed) {
  const v = trim(value, 200);
  return allowed.includes(v) ? v : "";
}

function pickMultiSelect(values, allowed) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const out = [];
  for (const v of values) {
    const trimmed = trim(v, 200);
    if (allowed.includes(trimmed) && !seen.has(trimmed)) {
      seen.add(trimmed);
      out.push(trimmed);
    }
  }
  return out;
}

const ALLOWED = {
  q2: ["Fully in person", "Fully online", "A mix of both"],
  q3: ["In-person event", "Live online", "Students complete it on their own", "We don't really run it"],
  q4: ["Grouped in person at an event", "Students self-organize", "Advisor assigns groups", "They struggle to form at all"],
  q6: ["Orientation", "Leadership Training Day", "Speaker Broadcasts", "SNTs", "Final induction step"],
  q7: ["Fully online in Society", "Hybrid (in person + Society for matching/tracking)", "Not sure yet — want to talk it through"],
  q8: [
    "Campus firewall / network restrictions",
    "SSO or login requirements",
    "Accessibility or screen-reader requirements",
    "Data, privacy, or FERPA review needed",
    "None that I know of",
  ],
};

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }

  const apiKey = process.env.AIRTABLE_API_KEY;
  if (!apiKey) {
    console.error("AIRTABLE_API_KEY is not set");
    res.status(500).json({ error: "server_misconfigured" });
    return;
  }

  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      res.status(400).json({ error: "invalid_json" });
      return;
    }
  }
  if (!body || typeof body !== "object") {
    res.status(400).json({ error: "missing_body" });
    return;
  }

  const respondentName = trim(body.respondentName, 200);
  const respondentEmail = trim(body.respondentEmail, 200);
  const schoolSlug = trim(body.schoolSlug, 100).toLowerCase();
  const schoolNameText = trim(body.schoolNameText, 200);

  if (!respondentName || !respondentEmail || !schoolNameText) {
    res.status(400).json({ error: "missing_required_fields" });
    return;
  }

  const submittedAt = new Date().toISOString();
  const submissionLabel = `${schoolNameText} — ${respondentName} — ${submittedAt.slice(0, 10)}`;

  const fields = {
    [FIELDS.submissionLabel]: submissionLabel,
    [FIELDS.submittedAt]: submittedAt,
    [FIELDS.schoolNameText]: schoolNameText,
    [FIELDS.respondentName]: respondentName,
    [FIELDS.respondentEmail]: respondentEmail,
    [FIELDS.respondentRole]: trim(body.respondentRole, 200),
    [FIELDS.q1Planning]: trim(body.q1Planning),
    [FIELDS.q2Induction]: pickSingleSelect(body.q2Induction, ALLOWED.q2),
    [FIELDS.q3Ltd]: pickSingleSelect(body.q3Ltd, ALLOWED.q3),
    [FIELDS.q3bCombinedEvents]: trim(body.q3bCombinedEvents),
    [FIELDS.q4SntFormation]: pickSingleSelect(body.q4SntFormation, ALLOWED.q4),
    [FIELDS.q5MemberCounts]: trim(body.q5MemberCounts),
    [FIELDS.q5bInvitationListSize]: trim(body.q5bInvitationListSize, 200),
    [FIELDS.q6StallStep]: pickSingleSelect(body.q6StallStep, ALLOWED.q6),
    [FIELDS.q7SntPilotApproach]: pickSingleSelect(body.q7SntPilotApproach, ALLOWED.q7),
    [FIELDS.q8ItConstraints]: pickMultiSelect(body.q8ItConstraints, ALLOWED.q8),
    [FIELDS.q8bItConstraintDetails]: trim(body.q8bItConstraintDetails),
    [FIELDS.q9Worries]: trim(body.q9Worries),
    [FIELDS.sourceUrl]: trim(body.sourceUrl, 2000),
    [FIELDS.userAgent]: trim(req.headers["user-agent"] || "", 500),
  };

  const schoolRecordId = SCHOOL_RECORD_IDS[schoolSlug];
  if (schoolRecordId) {
    fields[FIELDS.school] = [schoolRecordId];
  }

  // Drop empty single-select / link values so Airtable doesn't reject them.
  for (const key of Object.keys(fields)) {
    const v = fields[key];
    if (v === "" || (Array.isArray(v) && v.length === 0)) {
      delete fields[key];
    }
  }

  try {
    const airtableRes = await fetch(`https://api.airtable.com/v0/${BASE_ID}/${TABLE_ID}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ records: [{ fields }] }),
    });

    if (!airtableRes.ok) {
      const text = await airtableRes.text();
      console.error("Airtable error", airtableRes.status, text);
      res.status(502).json({ error: "airtable_error", status: airtableRes.status });
      return;
    }

    const data = await airtableRes.json();
    const recordId = data?.records?.[0]?.id || null;
    res.status(200).json({ ok: true, recordId });
  } catch (err) {
    console.error("Submit failed", err);
    res.status(500).json({ error: "submit_failed" });
  }
}
