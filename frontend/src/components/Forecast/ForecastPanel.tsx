/**
 * ForecastPanel — 5-day flood forecast per LGA + Annual Flood Outlook
 *
 * Features:
 *   - LGA search/select (774 LGAs from AFO API)
 *   - 5-day probability bar chart (pure CSS, no chart library dep)
 *   - Source attribution: "Data: NIHSA/NiMet" vs "Data: OWM (Global)"
 *   - 2024 baseline discharge comparison
 *   - AFO community list (filterable by state)
 *   - Discharge baseline note: 2024 records from NIHSA
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { forecastsApi, type ForecastPoint, type AfoCommunity } from '../../api/forecastsApi'
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const SEVERITY_COLORS: Record<string, string> = {
  RED: '#D32F2F', ORANGE: '#F57C00', YELLOW: '#F9A825',
  GREEN: '#388E3C', NONE: '#9E9E9E',
}

// Hardcoded representative LGA list for search; real app fetches from /api/v1/lgas
const QUICK_LGAS = [
  { id: 1, name: 'Lokoja', state: 'Kogi' },
  { id: 2, name: 'Makurdi', state: 'Benue' },
  { id: 3, name: 'Onitsha South', state: 'Anambra' },
  { id: 4, name: 'Maiduguri', state: 'Borno' },
  { id: 5, name: 'Yenagoa', state: 'Bayelsa' },
  { id: 6, name: 'Port Harcourt', state: 'Rivers' },
  { id: 7, name: 'Warri South', state: 'Delta' },
  { id: 8, name: 'Birnin Kebbi', state: 'Kebbi' },
]

function ProbabilityBar({ point }: { point: ForecastPoint }) {
  const { t } = useTranslation()
  const pct = Math.min(100, Math.max(0, point.probability_pct))
  const color = SEVERITY_COLORS[point.severity] || SEVERITY_COLORS.NONE

  return (
    <div className="forecast-bar" aria-label={`${point.date}: ${point.severity_label} — ${pct}%`}>
      <div className="forecast-bar__date">
        <span className="forecast-bar__day">
          {new Date(point.date).toLocaleDateString('en-NG', { weekday: 'short', month: 'short', day: 'numeric' })}
        </span>
      </div>
      <div className="forecast-bar__track" aria-hidden>
        <div
          className="forecast-bar__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <div className="forecast-bar__labels">
        <span className="forecast-bar__prob">{t('forecast.probability', { prob: pct.toFixed(0) })}</span>
        <span className="forecast-bar__severity" style={{ color }}>{point.severity_label}</span>
      </div>
      {point.inundation_pct != null && (
        <p className="forecast-bar__inundation">
          <small>{t('forecast.inundation', { pct: point.inundation_pct.toFixed(0) })}</small>
        </p>
      )}
      {point.discharge_m3s != null && (
        <p className="forecast-bar__discharge">
          <small>
            {t('forecast.discharge', { m3s: point.discharge_m3s.toLocaleString() })}
            {point.baseline_2024_m3s != null && (
              <> · {t('forecast.baseline', { m3s: point.baseline_2024_m3s.toLocaleString() })}</>
            )}
          </small>
        </p>
      )}
      <p className="forecast-bar__source"><small>{point.data_source_label}</small></p>
    </div>
  )
}

function AfoTable({ communities, stateFilter }: { communities: AfoCommunity[]; stateFilter: string }) {
  const { t } = useTranslation()
  const filtered = stateFilter
    ? communities.filter(c => c.state_code === stateFilter)
    : communities

  const highlightColors: Record<string, string> = {
    HIGHLY_PROBABLE: '#D32F2F',
    PROBABLE: '#F57C00',
    LOW_RISK: '#388E3C',
  }

  return (
    <div className="afo-table-wrapper" role="region" aria-label="Annual Flood Outlook communities">
      <table className="afo-table" aria-rowcount={filtered.length}>
        <thead>
          <tr>
            <th scope="col">Community</th>
            <th scope="col">LGA</th>
            <th scope="col">State</th>
            <th scope="col">{t('forecast.afo_title')}</th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 50).map(c => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td>{c.lga}</td>
              <td>{c.state}</td>
              <td>
                <span
                  className="afo-badge"
                  style={{ background: highlightColors[c.afo_class] }}
                  aria-label={c.afo_label}
                >
                  {c.afo_label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length > 50 && (
        <p className="afo-table__truncated">
          Showing 50 of {filtered.length} communities. Filter by state to narrow results.
        </p>
      )}
    </div>
  )
}

export default function ForecastPanel({ lang }: Props) {
  const { t } = useTranslation()
  const [selectedLgaId, setSelectedLgaId] = useState<number>(1)  // Lokoja default
  const [stateFilter, setStateFilter] = useState('')

  const { data: forecast, isLoading: forecastLoading } = useQuery({
    queryKey: ['forecast', selectedLgaId, lang],
    queryFn: () => forecastsApi.getFlood(selectedLgaId, { days: 5, lang }),
  })

  const { data: afo, isLoading: afoLoading } = useQuery({
    queryKey: ['afo', lang, stateFilter],
    queryFn: () => forecastsApi.getAfo({ lang, state_code: stateFilter || undefined }),
  })

  const states = [...new Set((afo?.communities || []).map(c => c.state_code))].sort()

  return (
    <div className="forecast-panel">
      <h1 className="forecast-panel__title">{t('forecast.title')}</h1>

      {/* LGA selector */}
      <section className="forecast-panel__lga-select" aria-label="Select LGA for forecast">
        <label htmlFor="lga-select" className="forecast-panel__label">
          Select LGA:
        </label>
        <select
          id="lga-select"
          value={selectedLgaId}
          onChange={e => setSelectedLgaId(Number(e.target.value))}
          className="forecast-panel__select"
        >
          {QUICK_LGAS.map(l => (
            <option key={l.id} value={l.id}>{l.name} ({l.state})</option>
          ))}
        </select>
      </section>

      {/* 5-day forecast */}
      <section className="forecast-panel__5day" aria-label="5-day flood forecast">
        {forecastLoading && <div className="forecast-panel__loading" role="status">Loading forecast…</div>}

        {forecast && (
          <>
            <h2 className="forecast-panel__lga-name">
              {forecast.lga_name}, {forecast.state_name}
              <span
                className={`flood-risk-badge flood-risk-badge--${forecast.flood_risk_class.toLowerCase()}`}
              >
                {forecast.flood_risk_class}
              </span>
            </h2>

            {forecast.data_staleness_hours != null && forecast.data_staleness_hours > 6 && (
              <p className="forecast-panel__stale" role="status">
                Data is {forecast.data_staleness_hours.toFixed(1)}h old.
              </p>
            )}

            <div className="forecast-bars" role="list" aria-label="Daily forecast">
              {forecast.forecast.map(point => (
                <ProbabilityBar key={point.date} point={point} />
              ))}
            </div>

            {forecast.forecast.length === 0 && (
              <p className="forecast-panel__no-data">
                No forecast data available for this LGA. Check back after the next NIHSA update.
              </p>
            )}
          </>
        )}
      </section>

      {/* Annual Flood Outlook */}
      <section className="forecast-panel__afo" aria-label="Annual Flood Outlook">
        <div className="afo-header">
          <h2>{t('forecast.afo_title')}</h2>
          <p className="afo-window">{t('forecast.afo_window')}</p>
          {afo && (
            <p className="afo-source">
              {afo.data_source_label} · {afo.total} communities
            </p>
          )}
        </div>

        {/* State filter */}
        <div className="afo-filter">
          <label htmlFor="state-filter">Filter by state:</label>
          <select
            id="state-filter"
            value={stateFilter}
            onChange={e => setStateFilter(e.target.value)}
          >
            <option value="">All states</option>
            {states.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        {/* Legend */}
        <div className="afo-legend" aria-label="AFO classification legend">
          {[
            ['HIGHLY_PROBABLE', '#D32F2F', t('forecast.highly_probable')],
            ['PROBABLE',        '#F57C00', t('forecast.probable')],
            ['LOW_RISK',        '#388E3C', t('forecast.low_risk')],
          ].map(([cls, color, label]) => (
            <span key={cls} className="afo-legend__item">
              <span className="afo-legend__dot" style={{ background: color as string }} aria-hidden />
              {label}
            </span>
          ))}
        </div>

        {afoLoading && <div className="afo-loading" role="status">Loading AFO…</div>}
        {afo && <AfoTable communities={afo.communities} stateFilter={stateFilter} />}
      </section>
    </div>
  )
}
