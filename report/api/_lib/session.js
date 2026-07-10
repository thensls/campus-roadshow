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

// iron-session's `ttl` bounds the seal's server-side validity; without it
// the encrypted payload stays decryptable for the default 14 days regardless
// of `cookieOptions.maxAge`. Setting both keeps browser + server aligned.

export function getSession(req, res) {
  return getIronSession(req, res, {
    ...sessionOptions(),
    ttl: 60 * 60 * 8, // 8 hours — seal expires with the cookie
    cookieName: "roadshow_session",
    cookieOptions: {
      ...BASE_COOKIE_OPTIONS,
      maxAge: 60 * 60 * 8,
    },
  });
}

export function getLoginSession(req, res) {
  return getIronSession(req, res, {
    ...sessionOptions(),
    ttl: 60 * 10, // 10 min — seal expires with the login-transaction cookie
    cookieName: "roadshow_login",
    cookieOptions: {
      ...BASE_COOKIE_OPTIONS,
      maxAge: 60 * 10,
    },
  });
}
