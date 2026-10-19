import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The backend serves web/dist as static files; in development Vite proxies /api to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.CHATLPT_DEV_API ?? "http://localhost:3050", changeOrigin: false } },
  },
  build: { outDir: "dist", sourcemap: true },
});
