import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  build: { outDir: "dist" },
  server: {
    // `npm run dev` (HMR on :5173) proxies API calls to the live backend from start.bat.
    proxy: {
      "/ask": "http://127.0.0.1:8000",
      "/runs": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
