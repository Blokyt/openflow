import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    outDir: "dist",
    rollupOptions: {
      output: {
        // Vendors séparés du code applicatif : ils changent rarement, le
        // navigateur les garde en cache entre deux mises à jour de l'app.
        // recharts (~350 kB) n'est utilisé que par le dashboard.
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-charts": ["recharts"],
          "vendor-icons": ["lucide-react"],
        },
      },
    },
  },
});
