/**
 * HazardWatch Nigeria — App shell + React Router
 *
 * Routes:
 *   /            → Dashboard
 *   /map         → FloodRiskMap
 *   /forecast    → ForecastPanel
 *   /alerts      → AlertList
 *   /shelters    → SheltersPage
 *   /report      → ReportForm
 *   /subscribe   → SubscribeForm
 *   /voice       → VoicePipeline (NEMA officers only)
 *
 * Geolocation: On first load, browser GPS → IP fallback → Nigeria centroid.
 * Detected coords passed as context so Dashboard + Map auto-center on user.
 */
import React, { Suspense, useState, useEffect, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import './index.css'
import { useTranslation } from 'react-i18next'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import './i18n'
import {
  LayoutDashboard, Map, Bell, Home, Building2, BarChart2,
  Menu, X, Globe, AlertTriangle, ChevronRight,
} from 'lucide-react'

import { SUPPORTED_LANGUAGES, type SupportedLang } from './i18n'
import type { Alert } from './api/alertsApi'
import WeatherLoader from './components/WeatherLoader'

// ── Geolocation context ──────────────────────────────────────────
export interface UserLocation {
  lat: number
  lng: number
  accuracy?: number
  placeName?: string    // "Lagos, Lagos State" — resolved from coords
  source: 'gps' | 'ip' | 'fallback'
}

interface GeoCtx {
  location: UserLocation | null
  status:   'loading' | 'granted' | 'denied' | 'error'
}

export const GeoContext = createContext<GeoCtx>({ location: null, status: 'loading' })

// Lazy-loaded route components
const Dashboard         = React.lazy(() => import('./components/Dashboard/Dashboard'))
const FloodRiskMap      = React.lazy(() => import('./components/Map/FloodRiskMap'))
const ForecastPanel     = React.lazy(() => import('./components/Forecast/ForecastPanel'))
const AlertList         = React.lazy(() => import('./components/Alerts/AlertList'))
const SubscribeForm     = React.lazy(() => import('./components/Subscribe/SubscribeForm'))
const SheltersPage      = React.lazy(() => import('./components/Shelters/SheltersPage'))
const ReportForm        = React.lazy(() => import('./components/Report/ReportForm'))
const VoicePipeline     = React.lazy(() => import('./components/VoicePipeline/VoicePipeline'))

// ── Reverse-geocode coords → "City, State" via Nominatim (free, no key) ──
async function reverseGeocode(lat: number, lng: number): Promise<string> {
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=10`,
      { headers: { 'Accept-Language': 'en' } }
    )
    const d = await r.json()
    const addr = d.address || {}
    const city  = addr.city || addr.town || addr.village || addr.county || ''
    const state = addr.state || ''
    return [city, state].filter(Boolean).join(', ') || 'Nigeria'
  } catch {
    return 'Nigeria'
  }
}

// ── Nigeria bounding box — clamp location to within Nigeria ──────
function isInNigeria(lat: number, lng: number): boolean {
  return lat >= 4.0 && lat <= 14.2 && lng >= 2.5 && lng <= 15.0
}

// ── IP geolocation fallback (free, no key needed) ─────────────────
async function ipGeolocate(): Promise<{ lat: number; lng: number; city: string; region: string }> {
  const r = await fetch('https://ipapi.co/json/')
  const d = await r.json()
  return { lat: parseFloat(d.latitude), lng: parseFloat(d.longitude), city: d.city || '', region: d.region || '' }
}

// Nigeria centroid — used whenever no valid in-country location is found
const NIGERIA_CENTER: UserLocation = {
  lat: 9.08, lng: 8.68,
  placeName: 'Nigeria',
  source: 'fallback',
}

// ── useGeolocation hook ───────────────────────────────────────────
function useGeolocation(): GeoCtx {
  const [ctx, setCtx] = useState<GeoCtx>({ location: null, status: 'loading' })

  useEffect(() => {
    let cancelled = false

    const setLocation = (loc: UserLocation) => {
      if (!cancelled) setCtx({ location: loc, status: 'granted' })
    }

    const tryGPS = () => {
      if (!navigator.geolocation) { tryIP(); return }
      navigator.geolocation.getCurrentPosition(
        async pos => {
          const { latitude: lat, longitude: lng, accuracy } = pos.coords
          if (isInNigeria(lat, lng)) {
            const placeName = await reverseGeocode(lat, lng)
            setLocation({ lat, lng, accuracy, placeName, source: 'gps' })
          } else {
            setLocation(NIGERIA_CENTER)
          }
        },
        () => tryIP(),
        { timeout: 7000, maximumAge: 300_000 }
      )
    }

    const tryIP = async () => {
      try {
        const { lat, lng, city, region } = await ipGeolocate()
        if (isInNigeria(lat, lng)) {
          setLocation({
            lat, lng,
            placeName: [city, region].filter(Boolean).join(', ') || 'Nigeria',
            source: 'ip',
          })
        } else {
          setLocation(NIGERIA_CENTER)
        }
      } catch {
        if (!cancelled) setLocation(NIGERIA_CENTER)
      }
    }

    tryGPS()
    return () => { cancelled = true }
  }, [])

  return ctx
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime:   5 * 60 * 1000,
      gcTime:      72 * 60 * 60 * 1000,
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
    { to: '/',          label: t('nav.dashboard'), icon: LayoutDashboard },
    { to: '/map',       label: t('nav.map'),       icon: Map             },
    { to: '/forecast',  label: t('nav.forecast'),  icon: BarChart2       },
    { to: '/alerts',    label: t('nav.alerts'),    icon: Bell            },
    { to: '/subscribe', label: t('nav.subscribe'), icon: Bell            },
  ]

  return (
    <nav className="app-nav" aria-label="Main navigation">
      {/* Brand */}
      <div className="app-nav__brand">
        <div className="app-nav__logo-mark" aria-hidden>
          <AlertTriangle size={16} strokeWidth={2.5} />
        </div>
        <span className="app-nav__title">{t('app.name')}</span>
        <span className="app-nav__subtitle">Nigeria</span>
      </div>

      {/* Mobile hamburger */}
      <button
        className="app-nav__hamburger"
        aria-expanded={menuOpen}
        aria-controls="nav-menu"
        aria-label="Toggle navigation"
        onClick={() => setMenuOpen(o => !o)}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
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
      <div className="app-nav__lang-wrap" aria-label="Language">
        <Globe size={13} className="app-nav__lang-icon" aria-hidden />
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
      </div>
    </nav>
  )
}

// ── Bottom Tab Bar ───────────────────────────────────────────

function BottomTabBar() {
  const { data: alerts = [] } = useQuery<Alert[]>({
    queryKey: ['alerts-badge'],
    queryFn: () => import('./api/alertsApi').then(m => m.alertsApi.list()),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const redCount      = alerts.filter(a => a.severity === 'RED').length
  const criticalCount = alerts.filter(a => ['RED', 'ORANGE'].includes(a.severity)).length

  const tabs = [
    { to: '/',         icon: Home,      label: 'Home'     },
    { to: '/map',      icon: Map,       label: 'Map'      },
    { to: '/alerts',   icon: Bell,      label: 'Alerts',  badge: criticalCount },
    { to: '/shelters', icon: Building2, label: 'Shelters' },
    { to: '/forecast', icon: BarChart2, label: 'Forecast' },
  ]

  return (
    <>
      {tabs.map(tab => {
        const Icon = tab.icon
        return (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/'}
            className={({ isActive }) => `footer-tab ${isActive ? 'active' : ''}`}
            aria-label={tab.label}
          >
            <span className="footer-tab__icon-wrap" aria-hidden>
              <Icon size={20} strokeWidth={1.75} />
              {tab.badge != null && tab.badge > 0 && (
                <span className={`footer-tab__badge ${redCount > 0 ? 'footer-tab__badge--red' : ''}`}>
                  {tab.badge > 99 ? '99+' : tab.badge}
                </span>
              )}
            </span>
            <span>{tab.label}</span>
          </NavLink>
        )
      })}
    </>
  )
}

// ── Voice Pipeline Gate (NEMA officers only) ─────────────────

function VoiceGate() {
  const [alertId,   setAlertId]   = useState('')
  const [officerId, setOfficerId] = useState('')
  const [active,    setActive]    = useState(false)

  if (active && alertId && officerId) {
    return (
      <Suspense fallback={<PageLoader />}>
        <VoicePipeline
          alertId={alertId}
          alertSeverity="RED"
          officerId={officerId}
          onClose={() => setActive(false)}
        />
      </Suspense>
    )
  }

  return (
    <div className="voice-gate">
      <div className="voice-gate__card">
        <div className="voice-gate__header">
          <div className="voice-gate__icon-wrap" aria-hidden>
            <AlertTriangle size={22} strokeWidth={2} />
          </div>
          <div>
            <h2 className="voice-gate__title">NEMA Officer Access</h2>
            <p className="voice-gate__subtitle">Voice alert production — authorised personnel only</p>
          </div>
        </div>
        <div className="voice-gate__fields">
          <div className="form-group">
            <label className="form-label" htmlFor="alert-id">Alert ID</label>
            <input
              id="alert-id"
              className="form-input"
              placeholder="e.g. ALT-2024-001234"
              value={alertId}
              onChange={e => setAlertId(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="officer-id">Officer ID</label>
            <input
              id="officer-id"
              className="form-input"
              placeholder="e.g. NEMA-OFF-5678"
              value={officerId}
              onChange={e => setOfficerId(e.target.value)}
            />
          </div>
          <button
            className="btn btn--primary btn--full"
            disabled={!alertId || !officerId}
            onClick={() => setActive(true)}
          >
            Enter Pipeline <ChevronRight size={16} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Loading fallback ─────────────────────────────────────────

function PageLoader() {
  return (
    <div className="page-loader">
      <WeatherLoader />
    </div>
  )
}

// ── Root App ─────────────────────────────────────────────────

export default function App() {
  const { i18n } = useTranslation()
  const [lang, setLang] = useState<SupportedLang>(
    (localStorage.getItem('hazardwatch_lang') as SupportedLang) || 'en'
  )
  const geo = useGeolocation()

  const handleLangChange = (newLang: SupportedLang) => {
    setLang(newLang)
    i18n.changeLanguage(newLang)
    localStorage.setItem('hazardwatch_lang', newLang)
    document.documentElement.lang = newLang
  }

  // All supported languages (en, ha, ig, yo, pidgin) use Latin script — LTR.
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = 'ltr'
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <GeoContext.Provider value={geo}>
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
                  <Route path="/shelters"  element={<SheltersPage lang={lang} />} />
                  <Route path="/subscribe" element={<SubscribeForm lang={lang} />} />
                  <Route path="/report"    element={<ReportForm lang={lang} />} />
                  <Route path="/voice/*"   element={<VoiceGate />} />
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
    </GeoContext.Provider>
  )
}
