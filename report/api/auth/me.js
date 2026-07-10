// Small JSON endpoint the browser can call to render "Signed in as X"
// in the header. Returns 401 if there's no session.

import { getSession } from "../_lib/session.js";

export default async function handler(req, res) {
  try {
    const session = await getSession(req, res);
    if (!session.user) {
      res.status(401).json({ authenticated: false });
      return;
    }
    const u = session.user;
    res.status(200).json({
      authenticated: true,
      user: {
        sub: u.sub,
        name: u.name,
        email: u.email,
        picture: u.picture,
      },
    });
  } catch (err) {
    console.error("auth/me error:", err);
    res.status(500).json({ authenticated: false, error: "session_read_failed" });
  }
}
