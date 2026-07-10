// Clear the local session, then redirect to auth.nsls.org's
// end_session_endpoint so the identity provider knows we're done.
//
// The local session is destroyed FIRST — before any OIDC discovery
// call that could throw. Otherwise a discovery failure would leave the
// user logged in locally despite hitting logout.

import { getOidcClient } from "../_lib/oidc.js";
import { getSession } from "../_lib/session.js";

export default async function handler(req, res) {
  // Step 1 — always clear the local session, even if the OIDC discovery
  // step below fails. Capture id_token first so we can pass it as a hint.
  let idToken;
  try {
    const session = await getSession(req, res);
    idToken = session.idToken;
    await session.destroy();
  } catch (err) {
    console.error("auth/logout: failed to clear local session:", err);
    // Continue anyway — the cookie may already be invalid; user still
    // deserves to be sent to end_session_endpoint or home.
  }

  // Step 2 — attempt to redirect to auth.nsls.org's end_session_endpoint.
  // If discovery or env validation fails, fall back to /.
  try {
    const client = await getOidcClient();
    const url = client.endSessionUrl({
      id_token_hint: idToken,
      post_logout_redirect_uri: process.env.OIDC_POST_LOGOUT_REDIRECT_URI,
    });
    res.redirect(302, url);
  } catch (err) {
    console.error("auth/logout: OIDC discovery failed, redirecting locally:", err);
    res.redirect(302, "/");
  }
}
