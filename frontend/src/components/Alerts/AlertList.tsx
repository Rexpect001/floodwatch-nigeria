/**
 * AlertList — full alerts page
 *
 * Features:
 *   - Filter by severity (RED/ORANGE/YELLOW/GREEN/all)
 *   - Tab: Alerts | Shelters
 *   - Each alert card shows: severity badge, title, body, confirmed_by sources,
 *     timestamp, data source, report-error button
 *   - Shelter tab shows map-less list with capacity info
 *   - RED alerts pulse with animation and requireInteraction visual cue
 *   - Auto-refresh every 60s
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { alertsApi, type Alert, type Shelter } from '../../api/alertsApi'
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const SEVERITY_COLORS: Record<string, string> = {
  RED: '#D32F2F', ORANGE: '#F57C00', YELLOW: '#F9A825', GREEN: '#388E3C',
}

const ALERT_TYPE_ICONS: Record<string, string> = {
  FLOOD_RIVERINE:   '🌊',
  FLOOD_FLASH:      '⚡🌊',
  FLOOD_COASTAL:    '🌊',
  HEATWAVE:         '🔥',
  THUNDERSTORM:     '⛈️',
  DUST_HARMATTAN:   '🌫️',
  WINDSTORM:        '💨',
  LANDSLIDE:        '⛰️',
  EARTHQUAKE:       '📳',
  EROSION:          '🏔️',
  WILDFIRE:         '🔥',
  DROUGHT:          '🏜️',
  DAM_RELEASE:      '🚧',
  DISEASE_OUTBREAK: '🦠',
  EVACUATION:       '🚨',
  ALL_CLEAR:        '✅',
}

// Which alert_types belong to each category tab
const HAZARD_CATEGORIES: Record<string, string[]> = {
  all:    [],   // empty = show everything
  flood:  ['FLOOD_RIVERINE', 'FLOOD_FLASH', 'FLOOD_COASTAL', 'DAM_RELEASE'],
  storm:  ['THUNDERSTORM', 'WINDSTORM', 'DUST_HARMATTAN', 'HEATWAVE'],
  land:   ['LANDSLIDE', 'EARTHQUAKE', 'EROSION'],
  fire:   ['WILDFIRE', 'DROUGHT'],
  health: ['DISEASE_OUTBREAK'],
  other:  ['EVACUATION', 'ALL_CLEAR'],
}

function AlertCard({ alert, onReportError }: { alert: Alert; onReportError: (id: string) => void }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(alert.severity === 'RED')

  return (
    <article
      className={`alert-card alert-card--${alert.severity.toLowerCase()} ${alert.severity === 'RED' ? 'alert-card--pulse' : ''}`}
      aria-label={`${t(`severity.${alert.severity}`)} — ${alert.title}`}
    >
      <div className="alert-card__header">
        <span
          className="alert-card__badge"
          style={{ background: SEVERITY_COLORS[alert.severity] }}
          aria-label={t(`severity.${alert.severity}`)}
        >
          {t(`severity.${alert.severity}`)}
        </span>
        <span className="alert-card__type">
          <span aria-hidden>{ALERT_TYPE_ICONS[alert.alert_type] ?? '⚠️'}</span>
          {' '}{alert.alert_type.replace(/_/g, ' ')}
        </span>
        <button
          className="alert-card__expand"
          aria-expanded={expanded}
          onClick={() => setExpanded(e => !e)}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? '▲' : '▼'}
        </button>
      </div>

      <h3 className="alert-card__title">{alert.title}</h3>

      {expanded && (
        <>
          <p className="alert-card__body">{alert.body}</p>

          {alert.sms_text && (
            <p className="alert-card__sms">
              <small><strong>SMS:</strong> {alert.sms_text}</small>
            </p>
          )}

          <div className="alert-card__meta">
            <span>{alert.data_source_label}</span>
            {alert.confirmed_by.length > 1 && (
              <span className="alert-card__confirmed">
                {t('alerts.confirmed_by', { sources: alert.confirmed_by.join(' + ') })}
              </span>
            )}
            <span>{t('alerts.last_updated', { timestamp: alert.last_updated })}</span>
            {alert.valid_until && (
              <span>Valid until: {alert.valid_until}</span>
            )}
          </div>

          <div className="alert-card__actions">
            {alert.severity === 'RED' && (
              <a href="tel:08000636261" className="btn btn--primary btn--sm">
                {t('alerts.evacuate')} — 0800-NEMA
              </a>
            )}
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => onReportError(alert.id)}
            >
              {t('alerts.report_error')}
            </button>
          </div>
        </>
      )}
    </article>
  )
}

function ShelterList({ lgaId }: { lgaId: number }) {
  const { data } = useQuery({
    queryKey: ['shelters', lgaId],
    queryFn: () => alertsApi.getShelters(lgaId),
    enabled: !!lgaId,
  })

  if (!data?.shelters?.length) {
    return <p className="shelters__empty">No shelters loaded for this LGA. Call 0800-NEMA for nearest shelter.</p>
  }

  return (
    <ul className="shelter-list" role="list">
      {data.shelters.map((s: Shelter, i: number) => (
        <li key={i} className="shelter-list__item">
          <strong>{s.name}</strong>
          {s.capacity && <span> · Capacity: {s.capacity.toLocaleString()}</span>}
          {s.address && <p className="shelter-list__address">{s.address}</p>}
          <a
            href={`https://maps.google.com/?q=${s.lat},${s.lng}`}
            target="_blank" rel="noopener noreferrer"
            className="shelter-list__directions"
          >
            Get directions
          </a>
        </li>
      ))}
    </ul>
  )
}

export default function AlertList({ lang }: Props) {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') || 'alerts'
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [hazardCategory, setHazardCategory] = useState<string>('all')
  const [reportingId, setReportingId] = useState<string | null>(null)
  const [reportDesc, setReportDesc] = useState('')
  const [reportSent, setReportSent] = useState(false)

  const { data: alerts = [], isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ['alerts', lang, severityFilter],
    queryFn: () => alertsApi.list({
      lang,
      severity: severityFilter !== 'all' ? severityFilter : undefined,
    }),
    refetchInterval: 60_000,
  })

  const categoryTypes = HAZARD_CATEGORIES[hazardCategory] ?? []
  const visibleAlerts = alerts.filter((a: Alert) =>
    categoryTypes.length === 0 || categoryTypes.includes(a.alert_type)
  )

  const handleReportError = async () => {
    if (!reportingId || reportDesc.length < 10) return
    await alertsApi.reportError({ alert_id: reportingId, description: reportDesc })
    setReportSent(true)
    setTimeout(() => { setReportingId(null); setReportDesc(''); setReportSent(false) }, 3000)
  }

  return (
    <div className="alert-list-page">
      {/* Tabs */}
      <div className="alert-tabs" role="tablist">
        {['alerts', 'shelters'].map(t2 => (
          <button
            key={t2}
            role="tab"
            aria-selected={tab === t2}
            className={`alert-tab ${tab === t2 ? 'active' : ''}`}
            onClick={() => setSearchParams({ tab: t2 })}
          >
            {t2 === 'alerts' ? t('alerts.active') : t('nav.shelters')}
          </button>
        ))}
      </div>

      {tab === 'alerts' && (
        <div role="tabpanel" aria-label="Active alerts">
          {/* Hazard category tabs */}
          <div className="hazard-filter" role="group" aria-label="Filter by hazard type">
            {Object.keys(HAZARD_CATEGORIES).map(cat => (
              <button
                key={cat}
                className={`hazard-btn ${hazardCategory === cat ? 'active' : ''}`}
                onClick={() => setHazardCategory(cat)}
              >
                {cat === 'flood'  ? '🌊 ' :
                 cat === 'storm'  ? '⛈️ ' :
                 cat === 'land'   ? '⛰️ ' :
                 cat === 'fire'   ? '🔥 ' :
                 cat === 'health' ? '🦠 ' :
                 cat === 'other'  ? '🚨 ' : ''}
                {t(`hazard_category.${cat}`)}
              </button>
            ))}
          </div>

          {/* Severity filter */}
          <div className="alert-filter" role="group" aria-label="Filter by severity">
            {['all', 'RED', 'ORANGE', 'YELLOW', 'GREEN'].map(s => (
              <button
                key={s}
                className={`filter-btn filter-btn--${s.toLowerCase()} ${severityFilter === s ? 'active' : ''}`}
                onClick={() => setSeverityFilter(s)}
              >
                {s === 'all' ? 'All' : t(`severity.${s}`)}
              </button>
            ))}
          </div>

          {isLoading && <div className="alert-list__loading" role="status">Loading alerts…</div>}
          {isError  && <div className="alert-list__error" role="alert">Unable to load alerts. Showing cached data.</div>}

          {visibleAlerts.length === 0 && !isLoading && (
            <div className="alert-list__none" role="status">
              {t('alerts.none')}
            </div>
          )}

          <div className="alert-list" role="feed" aria-label="Alert list">
            {visibleAlerts.map((alert: Alert) => (
              <AlertCard key={alert.id} alert={alert} onReportError={setReportingId} />
            ))}
          </div>

          {dataUpdatedAt > 0 && (
            <p className="alert-list__updated" aria-live="polite">
              {t('alerts.last_updated', { timestamp: new Date(dataUpdatedAt).toLocaleTimeString() })}
              {' · '}{alerts[0]?.data_source_label}
            </p>
          )}
        </div>
      )}

      {tab === 'shelters' && (
        <div role="tabpanel" aria-label="Evacuation shelters">
          <p className="shelters__intro">
            Showing shelters from active RED/ORANGE alerts.
            Call <a href="tel:08000636261">0800-NEMA</a> for emergency assistance.
          </p>
          {alerts
            .filter(a => ['RED','ORANGE'].includes(a.severity))
            .slice(0, 3)
            .map(a => (
              <div key={a.id} className="shelters__section">
                <h3>{a.title}</h3>
                {a.affected_lga_count > 0 && <ShelterList lgaId={0} />}
              </div>
            ))
          }
        </div>
      )}

      {/* Report error dialog */}
      {reportingId && (
        <div className="report-dialog" role="dialog" aria-modal="true" aria-label="Report error">
          <div className="report-dialog__inner">
            <h2>{t('alerts.report_error')}</h2>
            {reportSent ? (
              <p>Report received. Thank you.</p>
            ) : (
              <>
                <textarea
                  value={reportDesc}
                  onChange={e => setReportDesc(e.target.value)}
                  placeholder="Describe the error (location, data issue, etc.)…"
                  rows={4}
                  minLength={10}
                  aria-label="Error description"
                />
                <div className="report-dialog__actions">
                  <button className="btn btn--primary" onClick={handleReportError} disabled={reportDesc.length < 10}>
                    Submit
                  </button>
                  <button className="btn btn--ghost" onClick={() => setReportingId(null)}>
                    {t('voice.cancel')}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
