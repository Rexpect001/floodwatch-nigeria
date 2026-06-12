/**
 * Dashboard — Map-first, location-aware landing page
 */
import React, { useContext, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  MapPin, Thermometer, Wind, Droplets, CloudRain,
  Phone, Building2, Map, Bell, FileText, Volume2,
  Waves, Flame, CloudSun, Mountain,
  ArrowUpRight, AlertCircle, CheckCircle, Loader2,
  TrendingUp,
} from 'lucide-react'
import { alertsApi, type Alert } from '../../api/alertsApi'
import { forecastsApi, type CurrentWeather } from '../../api/forecastsApi'
import type { SupportedLang } from '../../i18n'
import { GeoContext } from '../../App'
import SiteFooter from '../SiteFooter'

const FloodRiskMap = React.lazy(() => import('../Map/FloodRiskMap'))

interface Props { lang: SupportedLang }

const SEVERITY_ORDER = ['RED', 'ORANGE', 'YELLOW', 'GREEN'] as const

// ── Location Banner ───────────────────────────────────────────────
function LocationBanner() {
  const { location, status } = useContext(GeoContext)

  if (status === 'loading') {
    return (
      <div className="location-banner location-banner__loading" aria-live="polite">
        <Loader2 size={14} className="location-banner__spin" aria-hidden />
        <span>Detecting your location…</span>
      </div>
    )
  }

  if (!location) {
    return (
      <div className="location-banner location-banner__error" aria-live="polite">
        <MapPin size={14} aria-hidden />
        Location unavailable — showing Nigeria overview
      </div>
    )
  }

  return (
    <div className="location-banner" aria-live="polite" aria-label={`Your location: ${location.placeName}`}>
      <div className="location-banner__dot" aria-hidden />
      <div className="location-banner__text">
        <span className="location-banner__here">Current location</span>
        <span className="location-banner__place">{location.placeName}</span>
      </div>
      {location.source === 'fallback' && (
        <span className="location-banner__hint">
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
        <span className="dashboard-hero__label">
          <Map size={11} aria-hidden />
          Live Hazard Map
        </span>
        <Link to="/map" className="dashboard-hero__expand">
          Expand <ArrowUpRight size={12} aria-hidden />
        </Link>
      </div>
      <div className="dashboard-hero__map">
        <Suspense fallback={
          <div style={{ height: '100%', background: 'var(--surface)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Loader2 size={24} className="location-banner__spin" style={{ color: 'var(--text-3)' }} aria-hidden />
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
  const LGA_ABUJA = 1
  const { data: weather, isLoading } = useQuery<CurrentWeather>({
    queryKey: ['weather', lang],
    queryFn: () => forecastsApi.getWeather(LGA_ABUJA, lang),
    refetchInterval: 15 * 60 * 1000,
    retry: 1,
  })

  if (isLoading) return (
    <div className="weather-widget weather-widget--loading" aria-label="Loading weather">
      <Loader2 size={20} className="location-banner__spin" style={{ color: 'var(--text-3)' }} aria-hidden />
    </div>
  )

  if (!weather) return null

  return (
    <div className={`weather-widget ${weather.is_heatwave ? 'weather-widget--heatwave' : ''}`}
         role="region" aria-label="Current weather">
      <div className="weather-widget__location">
        <MapPin size={11} aria-hidden />
        {weather.lga_name}, {weather.state_name}
      </div>
      <div className="weather-widget__main">
        <span className="weather-widget__temp">
          {weather.temp_c != null ? `${Math.round(weather.temp_c)}°C` : '--'}
        </span>
        {weather.is_heatwave && (
          <span className="weather-widget__heatwave-badge">
            <Flame size={11} aria-hidden /> HEATWAVE
          </span>
        )}
        <span className="weather-widget__condition">{weather.condition ?? 'N/A'}</span>
      </div>
      <div className="weather-widget__stats">
        {weather.rainfall_mm != null && (
          <span className="weather-widget__stat">
            <CloudRain size={13} aria-hidden /> {weather.rainfall_mm.toFixed(1)} mm
          </span>
        )}
        {weather.humidity_pct != null && (
          <span className="weather-widget__stat">
            <Droplets size={13} aria-hidden /> {weather.humidity_pct}%
          </span>
        )}
        {weather.wind_kmh != null && (
          <span className="weather-widget__stat">
            <Wind size={13} aria-hidden /> {Math.round(weather.wind_kmh)} km/h
          </span>
        )}
      </div>
      <div className="weather-widget__source">{weather.data_source_label}</div>
    </div>
  )
}

// ── Quick Actions ─────────────────────────────────────────────────
function QuickActions() {
  const actions = [
    { icon: Phone,     label: 'Call NEMA',     href: 'tel:08000636261', variant: 'emergency' },
    { icon: Building2, label: 'Find Shelter',  to:   '/shelters',       variant: 'warning'   },
    { icon: Map,       label: 'Evacuation Map',to:   '/map',            variant: 'watch'     },
    { icon: Bell,      label: 'Subscribe',     to:   '/subscribe',      variant: 'advisory'  },
    { icon: FileText,  label: 'Report Hazard', to:   '/report',         variant: 'advisory'  },
    { icon: Volume2,   label: 'Listen',        to:   '/voice',          variant: 'advisory'  },
  ]
  return (
    <section className="quick-actions" aria-label="Quick actions">
      <h2 className="dashboard__section-title">Quick Actions</h2>
      <div className="quick-actions__grid">
        {actions.map(a => {
          const Icon = a.icon
          const cls = `quick-action quick-action--${a.variant}`
          return a.href
            ? <a key={a.label} href={a.href} className={cls} aria-label={a.label}>
                <Icon size={22} strokeWidth={1.75} className="quick-action__icon" aria-hidden />
                <span className="quick-action__label">{a.label}</span>
              </a>
            : <Link key={a.label} to={a.to!} className={cls} aria-label={a.label}>
                <Icon size={22} strokeWidth={1.75} className="quick-action__icon" aria-hidden />
                <span className="quick-action__label">{a.label}</span>
              </Link>
        })}
      </div>
    </section>
  )
}

// ── Capability strip (trust signals, FloodMapp-style) ─────────────
function FeatureStrip() {
  const features = [
    { icon: MapPin,      title: 'LGA-level coverage',  desc: 'All 774 Local Government Areas, street-level relevance' },
    { icon: CloudRain,   title: 'Real-time data',      desc: '24/7 monitoring, 365 days a year'                       },
    { icon: Phone,       title: 'Works without internet', desc: 'Offline maps, SMS alerts and *384*FLOOD# USSD'       },
    { icon: CheckCircle, title: 'Official sources',    desc: 'NEMA, NIHSA and NiMet verified feeds'                   },
  ]
  return (
    <section className="feature-strip" aria-label="Platform capabilities">
      <div className="feature-strip__grid">
        {features.map(f => {
          const Icon = f.icon
          return (
            <div key={f.title} className="feature-card">
              <span className="feature-card__icon" aria-hidden>
                <Icon size={17} strokeWidth={2} />
              </span>
              <span className="feature-card__title">{f.title}</span>
              <span className="feature-card__desc">{f.desc}</span>
            </div>
          )
        })}
      </div>
    </section>
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

          {/* Quick actions */}
          <QuickActions />

          {/* Critical alert banner */}
          {topAlert && <AlertBanner alert={topAlert} />}

          {!topAlert && !isLoading && (
            <div className="dashboard__all-clear" role="status">
              <CheckCircle size={18} aria-hidden /> {t('alerts.none')}
            </div>
          )}
          {isLoading && (
            <div className="dashboard__loading" role="status" aria-live="polite">
              <Loader2 size={16} className="location-banner__spin" aria-hidden /> {t('alerts.active')}…
            </div>
          )}
          {isError && (
            <div className="dashboard__error" role="alert">
              <AlertCircle size={15} style={{ display: 'inline', marginRight: 6 }} aria-hidden />
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
              <h2 className="dashboard__section-title dashboard__section-title--icon">
                <Flame size={14} aria-hidden /> {t('heatwave.title')}
              </h2>
              <p className="heatwave__advice">{t('heatwave.advice')}</p>
              <p className="heatwave__threshold"><small>{t('heatwave.threshold')}</small></p>
            </section>
          )}
          {droughtAlert && (
            <section className="dashboard__advisory" aria-label="Drought advisory" role="note">
              <h2 className="dashboard__section-title dashboard__section-title--icon">
                <CloudSun size={14} aria-hidden /> Drought Warning
              </h2>
              <p>Water scarcity conditions active. Conserve water. Check on vulnerable communities in affected LGAs.</p>
            </section>
          )}
          {landslideAlert && (
            <section className="dashboard__advisory" aria-label="Landslide advisory" role="note">
              <h2 className="dashboard__section-title dashboard__section-title--icon">
                <Mountain size={14} aria-hidden /> Landslide Warning
              </h2>
              <p>Avoid hilly terrain and unstable slopes. Do not cross flooded roads or embankments in affected areas.</p>
            </section>
          )}
          {securityAlert && (
            <section className="dashboard__advisory dashboard__advisory--security" aria-label="Security advisory" role="alert">
              <h2 className="dashboard__section-title dashboard__section-title--icon">
                <AlertCircle size={14} aria-hidden /> Security Alert — {securityAlert.alert_type.replace(/_/g, ' ')}
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
            <h2 className="dashboard__section-title dashboard__section-title--icon">
              <TrendingUp size={14} aria-hidden /> Seasonal Hazard Outlook
            </h2>
            <div className="dashboard__outlook-grid">
              <div className="dashboard__outlook-item">
                <Waves size={16} className="dashboard__outlook-icon" aria-hidden />
                <span><strong>{t('forecast.afo_window')}</strong> · <Link to="/forecast">{t('forecast.afo_title')}</Link></span>
              </div>
              <div className="dashboard__outlook-item">
                <Flame size={16} className="dashboard__outlook-icon" aria-hidden />
                <span>Heatwave: <strong>Sokoto, Borno, Yobe</strong> (Apr–Jun)</span>
              </div>
              <div className="dashboard__outlook-item">
                <CloudSun size={16} className="dashboard__outlook-icon" aria-hidden />
                <span>Drought: <strong>Northeast / Sahel belt</strong></span>
              </div>
              <div className="dashboard__outlook-item">
                <Mountain size={16} className="dashboard__outlook-icon" aria-hidden />
                <span>Landslide: <strong>Anambra, Enugu, Cross River</strong></span>
              </div>
            </div>
          </section>

          {/* USSD hint */}
          <div className="dashboard__ussd-hint">
            No smartphone? <a href="tel:*384*3566*3%23" className="ussd-link">Dial *384*FLOOD#</a> on any phone.
          </div>

          {/* Capability strip */}
          <FeatureStrip />

          {/* Site footer */}
          <SiteFooter />
        </div>
      </div>
    </div>
  )
}
