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
      // Dev proxy: forward /api/* and /maps/* to FastAPI on :8000
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/maps': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
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
          leaflet: ['leaflet', 'react-leaflet'],
          vendor: ['react', 'react-dom', 'react-router-dom', 'i18next', 'react-i18next'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },

  optimizeDeps: {
    include: ['leaflet', 'react-leaflet'],
  },
})
