/**
 * FloodWatch Nigeria — App shell + React Router
 *
 * Routes:
 *   /            → Dashboard
 *   /map         → FloodRiskMap
 *   /forecast    → ForecastPanel
 *   /alerts      → AlertList
 *   /shelters    → Shelters (redirect to /alerts?tab=shelters for now)
 *   /report      → ReportForm
 *   /subscribe   → SubscribeForm
 *   /voice       → VoicePipeline (NEMA officers only)
 */
import React, { Suspense, useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate, useLocation } from 'react-router-dom'
import './index.css'
import { useTranslation } from 'react-i18next'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './i18n'

import { SUPPORTED_LANGUAGES, type SupportedLang } from './i18n'

// Lazy-loaded route components
const Dashboard         = React.lazy(() => import('./components/Dashboard/Dashboard'))
const FloodRiskMap      = React.lazy(() => import('./components/Map/FloodRiskMap'))
const ForecastPanel     = React.lazy(() => import('./components/Forecast/ForecastPanel'))
const AlertList         = React.lazy(() => import('./components/Alerts/AlertList'))
const SubscribeForm     = React.lazy(() => import('./components/Subscribe/SubscribeForm'))
const VoicePipeline     = React.lazy(() => import('./components/VoicePipeline/VoicePipeline'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime:   5 * 60 * 1000,   // 5 min
      gcTime:      72 * 60 * 60 * 1000,  // 72h (matches SW cache)
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})

// ── Nav ──────────────────────────────────────────────────────

function AppNav({ lang, onLangChange }: { lang: SupportedLang; onLangChange: (l: SupportedLang) => void }) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)

  const navItems = [
    { to: '/',          label: t('nav.dashboard') },
    { to: '/map',       label: t('nav.map')       },
    { to: '/forecast',  label: t('nav.forecast')  },
    { to: '/alerts',    label: t('nav.alerts')    },
    { to: '/subscribe', label: t('nav.subscribe') },
  ]

  return (
    <nav className="app-nav" aria-label="Main navigation">
      <div className="app-nav__brand">
        <span className="app-nav__logo" aria-hidden>🌊</span>
        <span className="app-nav__title">{t('app.name')}</span>
      </div>

      {/* Mobile hamburger */}
      <button
        className="app-nav__hamburger"
        aria-expanded={menuOpen}
        aria-controls="nav-menu"
        aria-label="Toggle navigation"
        onClick={() => setMenuOpen(o => !o)}
      >
        <span /><span /><span />
      </button>

      <ul id="nav-menu" className={`app-nav__links ${menuOpen ? 'open' : ''}`} role="list">
        {navItems.map(item => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `app-nav__link ${isActive ? 'active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>

      {/* Language switcher */}
      <select
        className="app-nav__lang"
        value={lang}
        onChange={e => onLangChange(e.target.value as SupportedLang)}
        aria-label="Select language"
      >
        {SUPPORTED_LANGUAGES.map(l => (
          <option key={l.code} value={l.code}>{l.nativeLabel}</option>
        ))}
      </select>
    </nav>
  )
}

// ── Bottom Tab Bar ───────────────────────────────────────────

function BottomTabBar() {
  const location = useLocation()
  const tabs = [
    { to: '/',          icon: '🏠', label: 'Home'     },
    { to: '/map',       icon: '🗺️', label: 'Map'      },
    { to: '/alerts',    icon: '🚨', label: 'Alerts'   },
    { to: '/forecast',  icon: '📊', label: 'Forecast' },
    { to: '/subscribe', icon: '📱', label: 'SMS'      },
  ]
  return (
    <>
      {tabs.map(tab => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/'}
          className={({ isActive }) => `footer-tab ${isActive ? 'active' : ''}`}
          aria-label={tab.label}
        >
          <span className="footer-tab__icon" aria-hidden>{tab.icon}</span>
          <span>{tab.label}</span>
        </NavLink>
      ))}
    </>
  )
}

// ── Loading fallback ─────────────────────────────────────────

function PageLoader() {
  return (
    <div className="page-loader" role="status" aria-live="polite">
      <div className="page-loader__spinner" aria-hidden />
      <span className="sr-only">Loading…</span>
    </div>
  )
}

// ── Root App ─────────────────────────────────────────────────

export default function App() {
  const { i18n } = useTranslation()
  const [lang, setLang] = useState<SupportedLang>(
    (localStorage.getItem('floodwatch_lang') as SupportedLang) || 'en'
  )

  const handleLangChange = (newLang: SupportedLang) => {
    setLang(newLang)
    i18n.changeLanguage(newLang)
    localStorage.setItem('floodwatch_lang', newLang)
    document.documentElement.lang = newLang
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app-shell">
          <AppNav lang={lang} onLangChange={handleLangChange} />

          <main className="app-main" id="main-content">
            <Suspense fallback={<PageLoader />}>
              <Routes>
                <Route path="/"          element={<Dashboard lang={lang} />} />
                <Route path="/map"       element={<FloodRiskMap lang={lang} />} />
                <Route path="/forecast"  element={<ForecastPanel lang={lang} />} />
                <Route path="/alerts"    element={<AlertList lang={lang} />} />
                <Route path="/shelters"  element={<Navigate to="/alerts?tab=shelters" replace />} />
                <Route path="/subscribe" element={<SubscribeForm lang={lang} />} />
                <Route path="/voice/*"   element={<VoicePipeline alertId="" alertSeverity="GREEN" officerId="" onClose={() => {}} />} />
                <Route path="*"          element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </main>

          <footer className="app-footer">
            <BottomTabBar />
          </footer>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
