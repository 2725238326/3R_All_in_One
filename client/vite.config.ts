import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const runtimeEnv =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env ?? {};
const host = runtimeEnv.TAURI_DEV_HOST;
const buildTarget = runtimeEnv.TAURI_ENV_PLATFORM && runtimeEnv.TAURI_ENV_PLATFORM !== "windows" ? "safari13" : "chrome105";

export default defineConfig({
  clearScreen: false,
  plugins: [react()],
  envPrefix: ["VITE_", "TAURI_ENV_*"],
  server: {
    port: 5173,
    strictPort: true,
    host: host || "127.0.0.1",
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"]
    },
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/local_jobs": "http://127.0.0.1:8765"
    }
  },
  build: {
    target: buildTarget,
    minify: !runtimeEnv.TAURI_ENV_DEBUG ? "esbuild" : false,
    sourcemap: !!runtimeEnv.TAURI_ENV_DEBUG,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, "/");
          if (!normalizedId.includes("/node_modules/")) {
            return undefined;
          }
          if (
            normalizedId.includes("/node_modules/react/") ||
            normalizedId.includes("/node_modules/react-dom/")
          ) {
            return "vendor-react";
          }
          if (
            normalizedId.includes("/node_modules/recharts/") ||
            normalizedId.includes("/node_modules/d3-")
          ) {
            return "vendor-charts";
          }
          if (normalizedId.includes("/node_modules/three/")) {
            return "vendor-three";
          }
          if (normalizedId.includes("/node_modules/lucide-react/")) {
            return "vendor-icons";
          }
          return undefined;
        }
      }
    }
  }
});
