// Owner D — Vite config for the iframe app.
// public/loader.js is copied verbatim to dist/ and served at /widget.js by nginx.
// The iframe app entry is src/main.tsx; Vite hashes the bundle into dist/assets/.

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    target: "es2020",
    sourcemap: false,
  },
});
