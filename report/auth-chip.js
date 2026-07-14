// Universal "Signed in as X · Sign out" chip.
//
// Included by every HTML page (except the main index, which has an
// in-header chip integrated into its own layout). Fetches the current
// session from /api/auth/me and renders a floating pill at the
// top-right of the page. Fails silently — if the endpoint is
// unavailable or the user is somehow unauthenticated on a gated page,
// the chip just doesn't appear.
//
// Styles inlined so no page-level CSS is required.

(function () {
  var WRAPPER =
    "position:fixed;top:14px;right:18px;z-index:9999;" +
    'display:none;gap:10px;align-items:center;' +
    'font:12px "Inter",-apple-system,BlinkMacSystemFont,sans-serif;' +
    "color:#6B6357;background:rgba(232,221,213,0.94);" +
    "backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);" +
    "border:1px solid rgba(30,20,20,0.10);border-radius:20px;" +
    "padding:6px 14px;box-shadow:0 2px 8px rgba(30,20,20,0.08);";
  var NAME = "font-weight:600;color:#1A3550;";
  var LINK = "color:#6B6357;text-decoration:underline;text-underline-offset:3px;transition:color .15s;";

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function render(user) {
    var name = user.name || user.email || "signed in";
    var chip = document.createElement("div");
    chip.setAttribute("style", WRAPPER);
    chip.innerHTML =
      "<span>Signed in as <span style=\"" + NAME + "\">" +
      escapeHtml(name) + "</span></span>" +
      '<a id="auth-chip-signout" href="/api/auth/logout" style="' + LINK + '">Sign out</a>';
    document.body.appendChild(chip);
    chip.style.display = "flex";

    var link = document.getElementById("auth-chip-signout");
    if (link) {
      link.addEventListener("mouseover", function () { link.style.color = "#C96058"; });
      link.addEventListener("mouseout", function () { link.style.color = "#6B6357"; });
    }
  }

  function boot() {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.authenticated && data.user) render(data.user);
      })
      .catch(function () { /* silent */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
