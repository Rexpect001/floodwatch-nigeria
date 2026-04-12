/**
 * Dashboard v4 — Map-first, location-aware landing page
 *
 * Layout:
 *   1. Location banner — "You are here: Lagos, Lagos State" (auto-detected)
 *   2. Map hero — FloodRiskMap centred on user, 280px, tap-to-expand
 *   3. Weather widget for detected location
 *   4. Active alert banner (RED/ORANGE)
 *   5. Severity summary cards
 *   6. Advisory sections (heatwave / drought / landslide / security)
 *   7. Quick navigation
 *   8. Seasonal outlook callout
 *   9. USSD hint
 */
import React, { useContext, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { alertsApi, type Alert } from '../../api/alertsApi'
import { forecastsApi, type CurrentWeather } from '../../api/forecastsApi'
import type { SupportedLang } from '../../i18n'
import { GeoContext } from '../../App'

const FloodRiskMap = React.lazy(() => import('../Map/FloodRiskMap'))

interface Props { lang: SupportedLang }

const SEVERITY_ORDER = ['RED', 'ORANGE', 'YELLOW', 'GREEN'] as const

// ── Location Banner ───────────────────────────────────────────────
function LocationBanner() {
  const { location, status } = useContext(GeoContext)

  if (status === 'loading') {
    return (
      <div className="location-banner location-banner__loading" aria-live="polite">
        <div className="spinner" style={{ width: 12, height: 12 }} aria-hidden />
        <span>Detecting your location…</span>
      </div>
    )
  }

  if (!location) {
    return (
      <div className="location-banner location-banner__error" aria-live="polite">
        📍 Location unavailable — showing Nigeria overview
      </div>
    )
  }

  return (
    <div className="location-banner" aria-live="polite" aria-label={`Your location: ${location.placeName}`}>
      <div className="location-banner__dot" aria-hidden />
      <div className="location-banner__text">
        <span className="location-banner__here">You are here</span>
        <span className="location-banner__place">{location.placeName}</span>
      </div>
      {location.source === 'fallback' && (
        <span style={{ fontSize: '0.65rem', opacity: 0.6, marginLeft: 'auto' }}>
          Enable location for local alerts
        </span>
      )}
    </div>
  )
}

// ── Map Hero ──────────────────────────────────────────────────────
function MapHero({ lang }: { lang: SupportedLang }) {
  return (
    <div className="dashboard-hero">
      <div className="dashboard-hero__overlay">
        <span className="dashboard-hero__label">🗺 Live Hazard Map</span>
        <Link to="/map" className="dashboard-hero__expand">Expand ↗</Link>
      </div>
      <div className="dashboard-hero__map">
        <Suspense fallback={
          <div style={{ height: '100%', background: 'var(--surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="spinner" style={{ width: 24, height: 24 }} aria-hidden />
          </div>
        }>
          <FloodRiskMap lang={lang} heroMode />
        </Suspense>
      </div>
    </div>
  )
}

// ── Live Status Strip ─────────────────────────────────────────────
function LiveStatusBar({ alerts, isLoading }: { alerts: Alert[]; isLoading: boolean }) {
  if (isLoading) return null
  const red    = alerts.filter(a => a.severity === 'RED').length
  const orange = alerts.filter(a => a.severity === 'ORANGE').length
  const yellow = alerts.filter(a => a.severity === 'YELLOW').length
  const total  = alerts.length

  if (total === 0) {
    return (
      <div className="dashboard__status-strip">
        <span className="status-chip status-chip--green">
          <span className="status-chip__dot status-chip__dot--green" />
          All clear
        </span>
        <span className="status-chip status-chip--muted">No active alerts</span>
      </div>
    )
  }

  return (
    <div className="dashboard__status-strip">
      {red > 0 && (
        <span className="status-chip status-chip--red">
          <span className="status-chip__dot status-chip__dot--red" />
          {red} Critical
        </span>
      )}
      {orange > 0 && (
        <span className="status-chip status-chip--orange">
          <span className="status-chip__dot status-chip__dot--orange" />
          {orange} High Risk
        </span>
      )}
      {yellow > 0 && (
        <span className="status-chip status-chip--yellow">
          {yellow} Moderate
        </span>
      )}
      <span className="status-chip status-chip--muted">{total} alerts active</span>
    </div>
  )
}

// ── Weather Widget ────────────────────────────────────────────────
function WeatherWidget({ lang }: { lang: SupportedLang }) {
  const LGA_ABUJA = 1  // TODO: resolve detected LGA from coordinates
  const { data: weather, isLoading } = useQuery<CurrentWeather>({
    queryKey: ['weather', lang],
    queryFn: () => forecastsApi.getWeather(LGA_ABUJA, lang),
    refetchInterval: 15 * 60 * 1000,
    retry: 1,
  })

  if (isLoading) return (
    <div className="weather-widget weather-widget--loading" aria-label="Loading weather">
      <div className="spinner" aria-hidden style={{ width: 20, height: 20 }} />
    </div>
  )

  if (!weather) return null

  return (
    <div className={`weather-widget ${weather.is_heatwave ? 'weather-widget--heatwave' : ''}`}
         role="region" aria-label="Current weather">
      <div className="weather-widget__location">
        📍 {weather.lga_name}, {weather.state_name}
      </div>
      <div className="weather-widget__main">
        <span className="weather-widget__temp">
          {weather.temp_c != null ? `${Math.round(weather.temp_c)}°C` : '--'}
        </span>
        {weather.is_heatwave && (
          <span className="weather-widget__heatwave-badge">🔥 HEATWAVE</span>
        )}
        <span className="weather-widget__condition">{weather.condition ?? 'N/A'}</span>
      </div>
      <div className="weather-widget__stats">
        {weather.rainfall_mm != null && (
          <span className="weather-widget__stat">🌧 {weather.rainfall_mm.toFixed(1)}mm</span>
        )}
        {weather.humidity_pct != null && (
          <span className="weather-widget__stat">💧 {weather.humidity_pct}%</span>
        )}
        {weather.wind_kmh != null && (
          <span className="weather-widget__stat">💨 {Math.round(weather.wind_kmh)}km/h</span>
        )}
      </div>
      <div className="weather-widget__source">{weather.data_source_label}</div>
    </div>
  )
}

function AlertBanner({ alert }: { alert: Alert }) {
  const { t } = useTranslation()
  return (
    <div
      className={`alert-banner alert-banner--${alert.severity.toLowerCase()}`}
      role="alert"
      aria-live="assertive"
    >
      <div className="alert-banner__header">
        <span className="alert-banner__severity">{t(`severity.${alert.severity}`)}</span>
        <span className="alert-banner__source">{alert.data_source_label}</span>
      </div>
      <p className="alert-banner__title">{alert.title}</p>
      <p className="alert-banner__body">{alert.body}</p>
      <div className="alert-banner__actions">
        <Link to="/alerts" className="btn btn--primary">{t('alerts.evacuate')}</Link>
        <Link to="/alerts?tab=shelters" className="btn btn--secondary">{t('alerts.shelter')}</Link>
      </div>
      {alert.confirmed_by.length > 1 && (
        <p className="alert-banner__confirmed">
          {t('alerts.confirmed_by', { sources: alert.confirmed_by.join(' + ') })}
        </p>
      )}
      <p className="alert-banner__timestamp">
        {t('alerts.last_updated', { timestamp: alert.last_updated })}
      </p>
    </div>
  )
}

function SeverityCard({ severity, count }: { severity: string; count: number }) {
  const { t } = useTranslation()
  return (
    <Link to={`/alerts?severity=${severity}`} className={`severity-card severity-card--${severity.toLowerCase()}`} style={{ textDecoration: 'none' }}>
      <span className="severity-card__count">{count}</span>
      <span className="severity-card__label">{t(`severity.${severity}`)}</span>
    </Link>
  )
}


export default function Dashboard({ lang }: Props) {
  const { t } = useTranslation()

  const { data: alerts = [], isLoading, isError } = useQuery({
    queryKey: ['alerts', lang],
    queryFn: () => alertsApi.list({ lang }),
    refetchInterval: 60_000,
  })

  const topAlert      = alerts.find((a: Alert) => a.severity === 'RED') || alerts.find((a: Alert) => a.severity === 'ORANGE')
  const heatAlert      = alerts.find((a: Alert) => a.alert_type === 'HEATWAVE'  && ['RED','ORANGE'].includes(a.severity))
  const droughtAlert   = alerts.find((a: Alert) => a.alert_type === 'DROUGHT'   && ['RED','ORANGE'].includes(a.severity))
  const landslideAlert = alerts.find((a: Alert) => a.alert_type === 'LANDSLIDE' && ['RED','ORANGE'].includes(a.severity))
  const securityAlert  = alerts.find((a: Alert) =>
    ['BANDITRY','INSURGENCY','COMMUNAL_CONFLICT','CIVIL_UNREST','KIDNAPPING_HOTSPOT','TERRORISM'].includes(a.alert_type)
    && ['RED','ORANGE'].includes(a.severity)
  )

  const countBySeverity = SEVERITY_ORDER.reduce(
    (acc, s) => ({ ...acc, [s]: alerts.filter((a: Alert) => a.severity === s).length }),
    {} as Record<string, number>
  )

  return (
    <div className="dashboard">
      {/* ── Location banner — full width ── */}
      <LocationBanner />

      {/* ── Two-column body: map left, info right ── */}
      <div className="dashboard__body">

        {/* Left: sticky map */}
        <div className="dashboard__map-col">
          <MapHero lang={lang} />
        </div>

        {/* Right: scrollable info panel */}
        <div className="dashboard__info-col">

          {/* Live status strip */}
          <LiveStatusBar alerts={alerts} isLoading={isLoading} />

          {/* Weather widget */}
          <WeatherWidget lang={lang} />

          {/* Critical alert banner */}
          {topAlert && <AlertBanner alert={topAlert} />}

          {!topAlert && !isLoading && (
            <div className="dashboard__all-clear" role="status">
              <span aria-hidden>✅</span> {t('alerts.none')}
            </div>
          )}
          {isLoading && (
            <div className="dashboard__loading" role="status" aria-live="polite">
              <div className="spinner" aria-hidden /> {t('alerts.active')}…
            </div>
          )}
          {isError && (
            <div className="dashboard__error" role="alert">
              Unable to load alerts. Showing cached data.
            </div>
          )}

          {/* Severity summary */}
          {alerts.length > 0 && (
            <section className="dashboard__severity-summary" aria-label="Alert severity summary">
              <h2 className="dashboard__section-title">{t('alerts.active')}</h2>
              <div className="severity-cards">
                {SEVERITY_ORDER.map(s => (
                  <SeverityCard key={s} severity={s} count={countBySeverity[s]} />
                ))}
              </div>
            </section>
          )}

          {/* Advisories */}
          {heatAlert && (
            <section className="dashboard__heatwave dashboard__advisory" aria-label="Heat advisory" role="note">
              <h2 className="dashboard__section-title">🔥 {t('heatwave.title')}</h2>
              <p className="heatwave__advice">{t('heatwave.advice')}</p>
              <p className="heatwave__threshold"><small>{t('heatwave.threshold')}</small></p>
            </section>
          )}
          {droughtAlert && (
            <section className="dashboard__advisory" aria-label="Drought advisory" role="note">
              <h2 className="dashboard__section-title">🏜️ Drought Warning</h2>
              <p>Water scarcity conditions active. Conserve water. Check on vulnerable communities in affected LGAs.</p>
            </section>
          )}
          {landslideAlert && (
            <section className="dashboard__advisory" aria-label="Landslide advisory" role="note">
              <h2 className="dashboard__section-title">⛰️ Landslide Warning</h2>
              <p>Avoid hilly terrain and unstable slopes. Do not cross flooded roads or embankments in affected areas.</p>
            </section>
          )}
          {securityAlert && (
            <section className="dashboard__advisory dashboard__advisory--security" aria-label="Security advisory" role="alert">
              <h2 className="dashboard__section-title">
                🔫 Security Alert — {securityAlert.alert_type.replace(/_/g, ' ')}
              </h2>
              <p>{securityAlert.body}</p>
              <p className="dashboard__advisory-action">
                <strong>Stay indoors. Avoid the affected area. Call 112 for emergencies.</strong>
              </p>
              <p className="dashboard__advisory-source">
                <small>Source: {securityAlert.data_source_label} · {securityAlert.last_updated}</small>
              </p>
            </section>
          )}

          {/* Seasonal outlook */}
          <section className="dashboard__afo-callout">
            <h2 className="dashboard__section-title">📋 Seasonal Hazard Outlook</h2>
            <div className="dashboard__outlook-grid">
              <div className="dashboard__outlook-item">
                <span>🌊</span>
                <span><strong>{t('forecast.afo_window')}</strong> · <Link to="/forecast">{t('forecast.afo_title')}</Link></span>
              </div>
              <div className="dashboard__outlook-item">
                <span>🔥</span>
                <span>Heatwave: <strong>Sokoto, Borno, Yobe</strong> (Apr–Jun)</span>
              </div>
              <div className="dashboard__outlook-item">
                <span>🏜️</span>
                <span>Drought: <strong>Northeast / Sahel belt</strong></span>
              </div>
              <div className="dashboard__outlook-item">
                <span>⛰️</span>
                <span>Landslide: <strong>Anambra, Enugu, Cross River</strong></span>
              </div>
            </div>
          </section>

          {/* USSD hint */}
          <div className="dashboard__ussd-hint">
            No smartphone? <a href="tel:*384*3566*3%23" className="ussd-link">Dial *384*FLOOD#</a> on any phone.
          </div>
        </div>
      </div>
    </div>
  )
}
