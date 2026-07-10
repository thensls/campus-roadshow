// Vercel Edge Middleware — gates every request behind an NSLS Auth
// session. Runs BEFORE any static file or serverless function is served.
//
// Presence check only: if the `roadshow_session` cookie exists, pass
// through. Cookie signature is verified inside serverless functions
// when they need the actual user identity. For the report content
// itself (HTML, images), presence is sufficient — an attacker with a
// forged cookie sees the same content any legitimate user does, and we
// don't leak per-user data through the pages.
//
// Excluded paths: /api/auth/* (would create a redirect loop) and Vercel
// internals. Static assets flow through the same gate so an unauthed
// user can't fetch a school detail page directly.

const AUTH_COOKIE = "roadshow_session";

export const config = {
  matcher: [
    // Match everything except:
    //   - /api/auth/* (login/callback/logout/me — needed to authenticate)
    //   - _next/_vercel internals
    //   - favicon.ico
    "/((?!api/auth|_next|_vercel|favicon\\.ico).*)",
  ],
};

export default function middleware(req) {
  const url = new URL(req.url);

  // Cookie header parsing (edge runtime doesn't give us req.cookies on
  // raw Web Requests; use the header).
  const cookieHeader = req.headers.get("cookie") || "";
  const hasSession = cookieHeader
    .split(";")
    .some((c) => c.trim().startsWith(`${AUTH_COOKIE}=`));

  if (hasSession) return; // pass through

  const loginUrl = new URL("/api/auth/login", url.origin);
  loginUrl.searchParams.set("returnTo", url.pathname + url.search);
  return Response.redirect(loginUrl.toString(), 302);
}
