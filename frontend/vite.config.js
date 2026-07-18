import { defineConfig, splitVendorChunkPlugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    splitVendorChunkPlugin(), // Split recharts/lucide into separate vendor chunks
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: [
        "favicon.ico",
        "favicon.svg",
        "favicon-32x32.png",
        "favicon-16x16.png",
        "apple-touch-icon.png",
      ],
      manifest: {
        name: "Ledger — AI Finance Platform",
        short_name: "Ledger",
        description: "Manage your personal finances with AI-powered insights",
        // Match the dark dual-palette brand (near-black surface, neon-lime accent)
        // so the install splash screen and OS chrome stay on-brand.
        theme_color: "#0A0A0B",
        background_color: "#0A0A0B",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        categories: ["finance", "productivity", "business"],
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          {
            src: "maskable-icon-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
        shortcuts: [
          {
            name: "Add transaction",
            short_name: "Add",
            url: "/transactions",
            description: "Quickly record a new transaction",
          },
          {
            name: "Dashboard",
            short_name: "Dashboard",
            url: "/",
            description: "Open your financial overview",
          },
          {
            name: "Amadeus AI",
            short_name: "Advisor",
            url: "/advisor",
            description: "Chat with your AI financial advisor",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        // API responses are never precached/runtime-cached — TanStack Query
        // owns freshness/staleness in-app, and stale API data cached by the
        // service worker would be actively misleading for a finance app.
        runtimeCaching: [
          {
            // Cache Google Fonts
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
            handler: "CacheFirst",
            options: {
              cacheName: "google-fonts",
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
      },
    }),
  ],
  build: {
    // Raise chunk warning threshold slightly (recharts is large)
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Manual chunk splitting: separate recharts so the main app loads fast
        manualChunks(id) {
          if (id.includes("recharts") || id.includes("d3-")) {
            return "recharts";
          }
          if (id.includes("lucide-react")) {
            return "icons";
          }
          if (id.includes("node_modules")) {
            return "vendor";
          }
        },
      },
    },
  },
  // Dev server proxy to avoid CORS issues locally
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
