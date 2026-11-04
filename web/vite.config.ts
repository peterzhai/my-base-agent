import { defineConfig } from "vite";
import path from "node:path";
export default defineConfig({
  resolve: {
    alias: {
      "@factory-agent/chat": path.resolve(
        import.meta.dirname,
        "../packages/chat/src/index.tsx",
      ),
    },
  },
  server: {
    proxy: {
      "/api": process.env.AGENT_BACKEND_ORIGIN || "http://127.0.0.1:8000",
      "/host-api": {
        target: process.env.HOST_BACKEND_ORIGIN || "http://127.0.0.1:8001",
        rewrite: (p) => p.replace(/^\/host-api/, ""),
      },
    },
  },
});
