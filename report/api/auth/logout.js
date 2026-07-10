// Clear the local session, then redirect to auth.nsls.org's
// end_session_endpoint so the identity provider knows we're done.

import { getOidcClient } from "../_lib/oidc.js";
import { getSession } from "../_lib/session.js";

export default async function handler(req, res) {
  try {
    const client = await getOidcClient();
    const session = await getSession(req, res);
    const idToken = session.idToken;

    await session.destroy();

    const url = client.endSessionUrl({
      id_token_hint: idToken,
      post_logout_redirect_uri: process.env.OIDC_POST_LOGOUT_REDIRECT_URI,
    });

    res.redirect(302, url);
  } catch (err) {
    console.error("auth/logout error:", err);
    // If OIDC discovery fails, still clear the local session and go
    // back to the home page so the user isn't stranded.
    res.redirect(302, "/");
  }
}
