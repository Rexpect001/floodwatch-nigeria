import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/public-sans'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './i18n'

// Register service worker (PWA)
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch(err => {
      console.warn('[SW] Registration failed:', err)
    })
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
)
