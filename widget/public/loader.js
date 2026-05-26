// Owner D — Phase 1 hello-world loader. Served at /widget.js by nginx.
// Host pages embed it as:
//   <script src="https://concierge.example.com/widget.js" data-widget-id="..."></script>
//
// Phase 1 scope: file exists, returns 200, IIFE so it does not pollute window.
// Real token-exchange + iframe injection lands in Phase 3 (D-011).

(function () {
  "use strict";

  var script = document.currentScript;
  var widgetId = script && script.getAttribute("data-widget-id");

  if (window.console && console.info) {
    console.info("[concierge] widget loader v0.1 stub", { widgetId: widgetId || null });
  }
})();
