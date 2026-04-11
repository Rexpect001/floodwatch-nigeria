/**
 * Dashboard — landing page
 *
 * Sections:
 *   1. Active alert banner (RED/ORANGE if any) with evacuate CTA
 *   2. Severity summary cards (count per severity)
 *   3. Quick-access: Map, Forecast, Subscribe
 *   4. Heatwave advisory (when ORANGE+ heat alert active)
 *   5. Data source attribution
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { alertsApi, type Alert } from '../../api/alertsApi'
import { forecastsApi, type CurrentWeather } from '../../api/forecastsApi'
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const SEVERITY_ORDER = ['RED', 'ORANGE', 'YELLOW', 'GREEN'] as const

// ── Weather Widget ────────────────────────────────────────────
function WeatherWidget({ lang }: { lang: SupportedLang }) {
  const LGA_ABUJA = 1  // fallback LGA until geolocation is wired
  const { data: weather, isLoading } = useQuery<CurrentWeather>({
    queryKey: ['weather', lang],
    queryFn: () => forecastsApi.getWeather(LGA_ABUJA, lang),
    refetchInterval: 15 * 60 * 1000,  // 15 min
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
    <div className={`severity-card severity-card--${severity.toLowerCase()}`}>
      <span className="severity-card__label">{t(`severity.${severity}`)}</span>
      <span className="severity-card__count">{count}</span>
    </div>
  )
}

function QuickNav() {
  const { t } = useTranslation()
  const items = [
    { to: '/map',       label: t('nav.map'),      icon: '🗺️' },
    { to: '/forecast',  label: t('nav.forecast'), icon: '📊' },
    { to: '/subscribe', label: t('nav.subscribe'),icon: '📱' },
    { to: '/alerts',    label: t('nav.alerts'),   icon: '🚨' },
  ]
  return (
    <nav className="quick-nav" aria-label="Quick navigation">
      {items.map(item => (
        <Link key={item.to} to={item.to} className="quick-nav__item">
          <span className="quick-nav__icon" aria-hidden>{item.icon}</span>
          <span className="quick-nav__label">{item.label}</span>
        </Link>
      ))}
    </nav>
  )
}

export default function Dashboard({ lang }: Props) {
  const { t } = useTranslation()

  const { data: alerts = [], isLoading, isError } = useQuery({
    queryKey: ['alerts', lang],
    queryFn: () => alertsApi.list({ lang }),
    refetchInterval: 60_000,   // refresh every 60s
  })

  const topAlert = alerts.find(a => a.severity === 'RED') || alerts.find(a => a.severity === 'ORANGE')
  const heatAlert = alerts.find(a => a.alert_type === 'HEATWAVE_RISK' && ['RED','ORANGE'].includes(a.severity))

  const countBySeverity = SEVERITY_ORDER.reduce(
    (acc, s) => ({ ...acc, [s]: alerts.filter(a => a.severity === s).length }),
    {} as Record<string, number>
  )

  return (
    <div className="dashboard">
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

      {/* Heatwave advisory */}
      {heatAlert && (
        <section className="dashboard__heatwave" aria-label="Heat advisory" role="note">
          <h2 className="dashboard__section-title">{t('heatwave.title')}</h2>
          <p className="heatwave__advice">{t('heatwave.advice')}</p>
          <p className="heatwave__threshold"><small>{t('heatwave.threshold')}</small></p>
        </section>
      )}

      {/* Quick navigation */}
      <section className="dashboard__quick-nav" aria-label="Quick access">
        <QuickNav />
      </section>

      {/* Annual Flood Outlook callout */}
      <section className="dashboard__afo-callout">
        <h2 className="dashboard__section-title">{t('forecast.afo_title')}</h2>
        <p>
          <strong>{t('forecast.afo_window')}</strong> ·{' '}
          <Link to="/map">{t('map.layers.floodRisk')}</Link>
        </p>
        <p className="dashboard__accuracy-note">
          {t('map.lake_chad')} · {t('map.deforestation')}
        </p>
      </section>

      {/* USSD access hint */}
      <div className="dashboard__ussd-hint">
        No smartphone? <a href="tel:*384*3566*3%23" className="ussd-link">Dial *384*FLOOD#</a> on any phone.
      </div>
    </div>
  )
}
