import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Proxy dev: /api/v1/... và /health đi tới backend (hoặc mock) ở cổng 8000, tránh CORS.
const BACKEND = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": BACKEND, "/health": BACKEND },
  },
  test: { environment: "node" },
});
