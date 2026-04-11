import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // Use our hand-crafted service worker (not Vite's auto-generated one)
      strategies: 'injectManifest',
      srcDir: 'public',
      filename: 'service-worker.js',
      injectManifest: {
        injectionPoint: undefined,   // our SW manages its own cache lists
      },
      manifest: false,   // manifest.json is already in public/
      registerType: 'autoUpdate',
      devOptions: { enabled: false },
    }),
  ],

  server: {
    port: 3000,
    proxy: {
      // Dev proxy: forward /api/* to FastAPI on :8000
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/maps': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          // Keep mapbox in its own chunk — it's large (~800KB)
          mapbox: ['mapbox-gl'],
          vendor: ['react', 'react-dom', 'react-router-dom', 'i18next', 'react-i18next'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },

  // Allow Mapbox GL worker imports
  optimizeDeps: {
    exclude: ['mapbox-gl'],
  },
})
