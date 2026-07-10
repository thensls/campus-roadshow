// Handle the OIDC authorization code callback.
//
// Verifies state + nonce + PKCE, exchanges the code for tokens,
// validates the ID token, and creates a signed session cookie
// with the minimum user info the report site needs.

import { getOidcClient } from "../_lib/oidc.js";
import { getSession, getLoginSession } from "../_lib/session.js";

export default async function handler(req, res) {
  try {
    const client = await getOidcClient();
    const loginSession = await getLoginSession(req, res);

    if (!loginSession.state) {
      res.status(400).send("Login session expired. Please start again.");
      return;
    }

    const params = client.callbackParams(req);

    // openid-client validates state, nonce, and PKCE code_verifier as
    // part of client.callback(). It also verifies the ID token
    // signature (via discovered JWKS), issuer, audience, and expiry.
    const tokenSet = await client.callback(
      process.env.OIDC_REDIRECT_URI,
      params,
      {
        state: loginSession.state,
        nonce: loginSession.nonce,
        code_verifier: loginSession.codeVerifier,
      }
    );

    const claims = tokenSet.claims();

    // Persist minimal user info in the app session. We do NOT store
    // the access token — the site only needs identity, not API access
    // against auth.nsls.org. id_token is kept so logout can pass it as
    // id_token_hint to /oidc/logout.
    const session = await getSession(req, res);
    session.user = {
      iss: claims.iss,
      sub: claims.sub,
      email: claims.email,
      email_verified: claims.email_verified,
      name: claims.name || claims.preferred_username || claims.email,
      given_name: claims.given_name,
      family_name: claims.family_name,
      picture: claims.picture,
      auth_time: claims.auth_time,
    };
    session.idToken = tokenSet.id_token;
    await session.save();

    const returnTo = loginSession.returnTo || "/";
    await loginSession.destroy();

    res.redirect(302, returnTo);
  } catch (err) {
    console.error("auth/callback error:", err);
    res.status(400).send("Login failed. Please try again.");
  }
}
