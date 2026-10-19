import { defineConfig } from "vite";

// Dev: `npm run dev` serves on :5173 and forwards /api to the FastAPI server.
// Build: `npm run build` writes dist/, which api/server.py serves at "/".
export default defineConfig({
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://localhost:8000" } },
});
