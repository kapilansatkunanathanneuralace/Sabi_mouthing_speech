import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const desktopDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: "renderer",
  envDir: desktopDir,
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../dist-renderer",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    strictPort: true
  }
});
