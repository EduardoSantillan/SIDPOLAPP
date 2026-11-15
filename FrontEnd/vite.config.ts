/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /api se reenvía a la API (docker compose -f docker-compose.yml -f docker-compose.dev.yml) quitando el prefijo,
// igual que hace Nginx en producción. Así el front usa siempre rutas relativas y no hay CORS ni direcciones fijas.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: process.env.API_URL ?? "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
  build: { sourcemap: false },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/preparar.ts"], css: false },
});
