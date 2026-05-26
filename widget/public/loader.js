// Owner D — Phase 3 D-011: real loader.
// Served at /widget.js. Host pages embed with:
//   <script src="https://concierge.example.com/widget.js" data-widget-id="..."></script>
//
// Behaviour:
//   1. Read data-widget-id from the current <script> element.
//   2. Detect window.location.origin (the host page's origin).
//   3. POST {widget_id, origin} to /api/v1/widget/token on the widget server.
//   4. Hold the returned token + session_id in this IIFE's closure (not localStorage).
//   5. Inject an <iframe> pointing to /iframe.html#token=...&session_id=...&widget_id=...
//      Token lives in the URL fragment so it never reaches the server in logs.
//   6. On HTTP 403 (origin not allowlisted) or any other failure: silently do nothing —
//      no console error, no visible indicator. The widget simply does not appear.

(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var widgetId = script.getAttribute("data-widget-id");
  if (!widgetId) return;

  var hostOrigin = window.location.origin;
  var widgetServer;
  try {
    widgetServer = new URL(script.src).origin;
  } catch (_) {
    return;
  }

  // Closure-scoped — never written to window, localStorage, or sessionStorage.
  var token = null;
  var sessionId = null;

  fetch(widgetServer + "/api/v1/widget/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId, origin: hostOrigin }),
    credentials: "omit",
  })
    .then(function (response) {
      if (!response.ok) return null;
      return response.json();
    })
    .then(function (data) {
      if (!data || !data.token || !data.session_id) return;
      token = data.token;
      sessionId = data.session_id;

      var iframe = document.createElement("iframe");
      iframe.src =
        widgetServer +
        "/iframe.html#token=" +
        encodeURIComponent(token) +
        "&session_id=" +
        encodeURIComponent(sessionId) +
        "&widget_id=" +
        encodeURIComponent(widgetId);
      iframe.title = "Concierge";
      iframe.setAttribute("allow", "");
      iframe.style.cssText =
        "position:fixed;bottom:20px;right:20px;width:380px;height:560px;" +
        "border:none;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.15);" +
        "z-index:2147483647;background:#fff;";

      if (document.body) {
        document.body.appendChild(iframe);
      } else {
        document.addEventListener("DOMContentLoaded", function () {
          document.body.appendChild(iframe);
        });
      }
    })
    .catch(function () {
      // Silent fail — per spec, no console output, no visible widget.
    });
})();
