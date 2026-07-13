// Vercel Edge Middleware — gates every request behind an NSLS Auth
// session. Runs BEFORE any static file or serverless function is served.
//
// This is a full seal verification, not a presence check. The cookie
// value must be a valid iron-session seal produced by /api/auth/callback
// with our SESSION_SECRET, must contain a `user` claim, and must not be
// past its 8-hour TTL. Anything else — missing, forged, expired,
// tampered — redirects to /api/auth/login.
//
// Excluded paths:
//   - /api/auth/*                 — the auth handshake itself
//   - Vercel internals + favicon
//
// Everything else — including pilot-survey.html, society-feedback.html,
// and /api/pilot-survey-submit — requires a valid session. External
// advisors following emailed links will bounce through auth.nsls.org.
//
// Using unsealData (rather than getIronSession) because middleware runs
// in the Edge runtime with a Web-standard Request; getIronSession's
// req/res API is Node-idiomatic and the low-level unseal is cleaner
// here. Chunked-cookie handling isn't needed at our current payload
// size (~1 KB id_token + profile stays well under iron-session's 4 KB
// chunk threshold).

import { unsealData } from "iron-session";

const AUTH_COOKIE = "roadshow_session";
const SESSION_TTL_SECONDS = 60 * 60 * 8;

export const config = {
  matcher: [
    "/((?!api/auth|_next|_vercel|favicon\\.ico).*)",
  ],
};

export default async function middleware(req) {
  const url = new URL(req.url);

  const cookieHeader = req.headers.get("cookie") || "";
  const match = cookieHeader.match(new RegExp(`(?:^|; )${AUTH_COOKIE}=([^;]+)`));

  let authenticated = false;
  if (match) {
    try {
      const sealed = decodeURIComponent(match[1]);
      const data = await unsealData(sealed, {
        password: process.env.SESSION_SECRET,
        ttl: SESSION_TTL_SECONDS,
      });
      authenticated = !!(data && data.user);
    } catch {
      // Malformed, wrong-secret, or expired seal — treat as unauth.
    }
  }

  if (authenticated) return;

  const loginUrl = new URL("/api/auth/login", url.origin);
  loginUrl.searchParams.set("returnTo", url.pathname + url.search);
  return Response.redirect(loginUrl.toString(), 302);
}
