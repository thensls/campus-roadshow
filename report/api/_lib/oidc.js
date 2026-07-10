// OIDC client for auth.nsls.org.
//
// Uses discovery on first call, then caches the client instance for the
// lifetime of the serverless function warm instance. Cold starts pay
// one discovery request; subsequent calls are free.

import { Issuer, generators } from "openid-client";

let cachedClient = null;

export async function getOidcClient() {
  if (cachedClient) return cachedClient;

  const issuerUrl = requireEnv("OIDC_ISSUER_URL");
  const clientId = requireEnv("OIDC_CLIENT_ID");
  const clientSecret = requireEnv("OIDC_CLIENT_SECRET");
  const redirectUri = requireEnv("OIDC_REDIRECT_URI");
  const postLogoutRedirectUri = requireEnv("OIDC_POST_LOGOUT_REDIRECT_URI");

  const issuer = await Issuer.discover(issuerUrl);

  cachedClient = new issuer.Client({
    client_id: clientId,
    client_secret: clientSecret,
    redirect_uris: [redirectUri],
    post_logout_redirect_uris: [postLogoutRedirectUri],
    response_types: ["code"],
    token_endpoint_auth_method: "client_secret_post",
  });

  return cachedClient;
}

export { generators };

function requireEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env var: ${name}`);
  return v;
}
