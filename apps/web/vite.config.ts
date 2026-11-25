import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API is reached through this proxy (same origin, no CORS needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VISION_API_URL ?? "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "node",
    // Tests that read the stylesheet (Rail.test.tsx) get the real file, not an empty string.
    css: { include: [/layout\.css/] },
  },
});
