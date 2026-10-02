import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The FastAPI server (T-009) serves web/dist in production. During `npm run dev`
// the Vite dev server forwards API and WebSocket calls to it. 8765 is the launcher's port
// (tools/launcher/Launcher.cs).
const SERVER = process.env.DINO_AF_SERVER ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": SERVER,
      "/ws": { target: SERVER, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
