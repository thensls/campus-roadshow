// Session cookie helpers for the Campus Roadshow report.
//
// Two separate cookies:
//   - roadshow_session — long-lived, holds authenticated user info
//   - roadshow_login   — short-lived, holds state/nonce/PKCE during the
//                        login handshake with auth.nsls.org
//
// Both are signed + encrypted with SESSION_SECRET via iron-session.

import { getIronSession } from "iron-session";

const isProd = process.env.VERCEL_ENV === "production";

const BASE_COOKIE_OPTIONS = {
  secure: isProd,
  httpOnly: true,
  sameSite: "lax",
  path: "/",
};

function sessionOptions() {
  const password = process.env.SESSION_SECRET;
  if (!password || password.length < 32) {
    throw new Error("SESSION_SECRET env var missing or too short (need 32+ chars)");
  }
  return { password };
}

export function getSession(req, res) {
  return getIronSession(req, res, {
    ...sessionOptions(),
    cookieName: "roadshow_session",
    cookieOptions: {
      ...BASE_COOKIE_OPTIONS,
      maxAge: 60 * 60 * 8, // 8 hours
    },
  });
}

export function getLoginSession(req, res) {
  return getIronSession(req, res, {
    ...sessionOptions(),
    cookieName: "roadshow_login",
    cookieOptions: {
      ...BASE_COOKIE_OPTIONS,
      maxAge: 60 * 10, // 10 minutes — enough to bounce through auth.nsls.org
    },
  });
}
