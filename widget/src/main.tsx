// Owner D — Phase 3 D-015: iframe app entry point.
// Mounts <Widget /> into #root in index.html. Strict mode is fine — Widget tolerates
// the double-effect dev behaviour because its mount-time fetches are idempotent.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Widget } from "./Widget";

const rootEl = document.getElementById("root");
if (rootEl) {
  createRoot(rootEl).render(
    <StrictMode>
      <Widget />
    </StrictMode>
  );
}
