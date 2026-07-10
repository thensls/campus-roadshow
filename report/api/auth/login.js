// Start an OIDC login. Generates fresh state/nonce/PKCE values,
// stashes them in a short-lived signed cookie, and redirects the
// browser to auth.nsls.org's authorization endpoint.

import { getOidcClient, generators } from "../_lib/oidc.js";
import { getLoginSession } from "../_lib/session.js";

export default async function handler(req, res) {
  try {
    const client = await getOidcClient();

    const state = generators.state();
    const nonce = generators.nonce();
    const codeVerifier = generators.codeVerifier();
    const codeChallenge = generators.codeChallenge(codeVerifier);

    // Where to send the user after successful login. Only accept
    // same-origin paths to avoid open-redirect abuse.
    const rawReturnTo = typeof req.query.returnTo === "string" ? req.query.returnTo : "/";
    const returnTo = rawReturnTo.startsWith("/") && !rawReturnTo.startsWith("//")
      ? rawReturnTo
      : "/";

    const loginSession = await getLoginSession(req, res);
    loginSession.state = state;
    loginSession.nonce = nonce;
    loginSession.codeVerifier = codeVerifier;
    loginSession.returnTo = returnTo;
    await loginSession.save();

    const scopes = process.env.OIDC_SCOPES || "openid profile email";
    const url = client.authorizationUrl({
      scope: scopes,
      state,
      nonce,
      code_challenge: codeChallenge,
      code_challenge_method: "S256",
    });

    res.redirect(302, url);
  } catch (err) {
    console.error("auth/login error:", err);
    res.status(500).send("Login failed to start. Check server logs.");
  }
}
