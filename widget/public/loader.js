// Owner D — Phase 3 D-011: real loader with launcher bubble.
// Served at /widget.js. Host pages embed with:
//   <script src="https://concierge.example.com/widget.js" data-widget-id="..."></script>
//
// Behaviour:
//   1. Read data-widget-id from the current <script> element.
//   2. Detect window.location.origin (the host page's origin).
//   3. POST {widget_id, origin} to /api/v1/widget/token on the widget server.
//   4. Hold the returned token + session_id in this IIFE's closure (not localStorage).
//   5. Inject a fixed bottom-right launcher BUBBLE and a hidden iframe pointing to
//      /iframe.html#token=...&session_id=...&widget_id=...
//      The bubble opens the iframe; the iframe posts "concierge:close" to close.
//      Token lives in the URL fragment so it never reaches the server in logs.
//   6. On HTTP 403 (origin not allowlisted) or any other failure: silently do nothing
//      - no console error, no visible indicator. Neither bubble nor iframe appears.

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
  var bubble = null;
  var iframe = null;

  var BUBBLE_STYLE =
    "position:fixed;bottom:20px;right:20px;width:60px;height:60px;" +
    "border:none;border-radius:50%;cursor:pointer;background:#c8607a;" +
    "color:#fff;box-shadow:0 4px 14px rgba(140,60,80,0.35);" +
    "z-index:2147483647;display:flex;align-items:center;justify-content:center;" +
    "transition:transform 0.15s ease, background 0.15s ease;";
  var BUBBLE_HOVER_BG = "#8e4055";
  var IFRAME_STYLE_BASE =
    "position:fixed;bottom:20px;right:20px;width:380px;height:560px;" +
    "max-height:calc(100vh - 40px);border:none;border-radius:16px;" +
    "box-shadow:0 12px 36px rgba(0,0,0,0.18);" +
    "z-index:2147483647;background:#fff;";

  // SVG chat bubble icon — currentColor inherits from the button's color.
  var CHAT_ICON =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>' +
    "</svg>";

  function appendWhenReady(el) {
    if (document.body) {
      document.body.appendChild(el);
    } else {
      document.addEventListener("DOMContentLoaded", function () {
        document.body.appendChild(el);
      });
    }
  }

  function openWidget() {
    if (!iframe) return;
    iframe.style.display = "block";
    if (bubble) bubble.style.display = "none";
  }

  function closeWidget() {
    if (!iframe) return;
    iframe.style.display = "none";
    if (bubble) bubble.style.display = "flex";
  }

  function createBubble() {
    bubble = document.createElement("button");
    bubble.type = "button";
    bubble.setAttribute("aria-label", "Open chat");
    bubble.title = "Chat with us";
    bubble.innerHTML = CHAT_ICON;
    bubble.style.cssText = BUBBLE_STYLE;
    bubble.addEventListener("mouseenter", function () {
      bubble.style.background = BUBBLE_HOVER_BG;
      bubble.style.transform = "scale(1.05)";
    });
    bubble.addEventListener("mouseleave", function () {
      bubble.style.background = "#c8607a";
      bubble.style.transform = "scale(1)";
    });
    bubble.addEventListener("click", openWidget);
    appendWhenReady(bubble);
  }

  function createIframe() {
    iframe = document.createElement("iframe");
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
    iframe.style.cssText = IFRAME_STYLE_BASE + "display:none;";
    appendWhenReady(iframe);
  }

  // The iframe asks the host to close itself via postMessage.
  window.addEventListener("message", function (e) {
    if (e && e.data === "concierge:close") closeWidget();
  });

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
      createIframe();
      createBubble();
    })
    .catch(function () {
      // Silent fail — per spec, no console output, no visible widget.
    });
})();
