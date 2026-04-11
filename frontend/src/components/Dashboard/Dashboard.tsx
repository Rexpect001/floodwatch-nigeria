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
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const SEVERITY_ORDER = ['RED', 'ORANGE', 'YELLOW', 'GREEN'] as const

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
        {t('subscribe.ussd_hint')}
      </div>
    </div>
  )
}
