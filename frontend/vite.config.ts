import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, loadEnv } from "vite";

// Dev only: proxy relative /api calls, including the canonical Team chat WebSocket, to the local
// backend. The same paths run in production through Caddy; loopbacks never enter src/.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiPort = env.SHIMPZ_API_PORT || "8000";
  return {
    plugins: [tailwindcss(), sveltekit()],
    server: {
      proxy: {
        "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true, ws: true },
      },
    },
  };
});
