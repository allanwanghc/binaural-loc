import { defineConfig } from "vite";

// In development, run the Python server (`python -m binaural_loc serve ...`, port 8000)
// and `npm run dev`; API calls are proxied to it.
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
