/**
 * ForecastPanel — 5-day flood forecast per LGA + Annual Flood Outlook
 * LGAs loaded dynamically from API (all 774, all 36 states + FCT)
 */
import React, { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { forecastsApi, type ForecastPoint, type AfoCommunity } from '../../api/forecastsApi'
import { apiClient } from '../../api/client'
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

interface LgaItem   { id: number; name: string; flood_risk_class: string }
interface StateGroup { state_id: number; state_name: string; state_code: string; lgas: LgaItem[] }

const SEVERITY_COLORS: Record<string, string> = {
  RED: '#D32F2F', ORANGE: '#F57C00', YELLOW: '#F9A825',
  GREEN: '#388E3C', NONE: '#9E9E9E',
}

// ── Probability bar ───────────────────────────────────────────
function ProbabilityBar({ point }: { point: ForecastPoint }) {
  const { t } = useTranslation()
  const pct   = Math.min(100, Math.max(0, point.probability_pct))
  const color = SEVERITY_COLORS[point.severity] ?? SEVERITY_COLORS.NONE

  return (
    <div className="forecast-bar" aria-label={`${point.date}: ${pct}%`}>
      <div className="forecast-bar__date">
        <span className="forecast-bar__day">
          {new Date(point.date).toLocaleDateString('en-NG', {
            weekday: 'short', month: 'short', day: 'numeric',
          })}
        </span>
      </div>
      <div className="forecast-bar__track" aria-hidden>
        <div className="forecast-bar__fill" style={{ width: `${pct}%`, background: color }} />
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

// ── AFO Table ─────────────────────────────────────────────────
function AfoTable({ communities, stateFilter }: { communities: AfoCommunity[]; stateFilter: string }) {
  const { t } = useTranslation()
  const filtered = stateFilter
    ? communities.filter(c => c.state_code === stateFilter)
    : communities

  const colors: Record<string, string> = {
    HIGHLY_PROBABLE: '#D32F2F',
    PROBABLE:        '#F57C00',
    LOW_RISK:        '#388E3C',
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
                <span className="afo-badge" style={{ background: colors[c.afo_class] }}>
                  {c.afo_label}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length === 0 && (
        <p className="afo-table__truncated">No communities found for this filter.</p>
      )}
      {filtered.length > 50 && (
        <p className="afo-table__truncated">
          Showing 50 of {filtered.length} communities. Filter by state to see more.
        </p>
      )}
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────
export default function ForecastPanel({ lang }: Props) {
  const { t } = useTranslation()
  const [selectedLgaId, setSelectedLgaId] = useState<number>(0)
  const [stateFilter,   setStateFilter]   = useState('')
  const [lgaSearch,     setLgaSearch]     = useState('')
  const [selectedState, setSelectedState] = useState('')

  // Load all LGAs grouped by state
  const { data: lgaData, isLoading: lgaLoading } = useQuery({
    queryKey: ['lgas'],
    queryFn: () => apiClient.get<{ states: StateGroup[]; total_lgas: number }>('/stations/lgas').then(r => r.data),
    staleTime: 24 * 60 * 60 * 1000,  // 24h — static data
  })

  // Flatten LGAs for search, filtered by selected state
  const filteredLgas = useMemo(() => {
    if (!lgaData) return []
    const allLgas = lgaData.states.flatMap(s =>
      s.lgas.map(l => ({ ...l, state_name: s.state_name, state_code: s.state_code }))
    )
    return allLgas.filter(l => {
      const matchesState = !selectedState || l.state_code === selectedState
      const matchesSearch = !lgaSearch || l.name.toLowerCase().includes(lgaSearch.toLowerCase())
      return matchesState && matchesSearch
    })
  }, [lgaData, selectedState, lgaSearch])

  // Auto-select first LGA when data loads
  const effectiveLgaId = selectedLgaId || filteredLgas[0]?.id || 0

  const { data: forecast, isLoading: forecastLoading, isError: forecastError } = useQuery({
    queryKey: ['forecast', effectiveLgaId, lang],
    queryFn: () => forecastsApi.getFlood(effectiveLgaId, { days: 5, lang }),
    enabled: effectiveLgaId > 0,
    retry: 1,
  })

  const { data: afo, isLoading: afoLoading } = useQuery({
    queryKey: ['afo', lang, stateFilter],
    queryFn: () => forecastsApi.getAfo({ lang, state_code: stateFilter || undefined }),
  })

  const states = lgaData?.states ?? []

  return (
    <div className="forecast-panel">
      <h1 className="forecast-panel__title">{t('forecast.title')}</h1>

      {/* State + LGA Selector */}
      <section className="forecast-panel__lga-select" aria-label="Select LGA for forecast">

        {/* State filter */}
        <label className="forecast-panel__label" htmlFor="state-select">
          State ({states.length} states)
        </label>
        <select
          id="state-select"
          value={selectedState}
          onChange={e => { setSelectedState(e.target.value); setSelectedLgaId(0); setLgaSearch('') }}
          className="forecast-panel__select"
          style={{ marginBottom: 10 }}
        >
          <option value="">All States</option>
          {states.map(s => (
            <option key={s.state_code} value={s.state_code}>
              {s.state_name} ({s.lgas.length} LGAs)
            </option>
          ))}
        </select>

        {/* LGA search */}
        <label className="forecast-panel__label" htmlFor="lga-search">
          Search LGA ({filteredLgas.length} available)
        </label>
        <input
          id="lga-search"
          type="search"
          value={lgaSearch}
          onChange={e => setLgaSearch(e.target.value)}
          placeholder="Type LGA name…"
          className="form-input"
          style={{ marginBottom: 10 }}
        />

        {/* LGA list */}
        {lgaLoading ? (
          <div className="forecast-panel__loading" role="status">Loading LGAs…</div>
        ) : (
          <select
            value={effectiveLgaId}
            onChange={e => setSelectedLgaId(Number(e.target.value))}
            className="forecast-panel__select"
            size={Math.min(6, filteredLgas.length)}
            style={{ height: 'auto' }}
          >
            {filteredLgas.map(l => (
              <option key={l.id} value={l.id}>
                {l.name} — {l.state_name}
                {l.flood_risk_class === 'HIGH' ? ' ⚠️' : ''}
              </option>
            ))}
            {filteredLgas.length === 0 && (
              <option disabled>No LGAs match your search</option>
            )}
          </select>
        )}
      </section>

      {/* 5-day forecast */}
      <section className="forecast-panel__5day" aria-label="5-day flood forecast" style={{ marginTop: 24 }}>

        {forecastLoading && (
          <div className="forecast-panel__loading" role="status">
            <div className="spinner" aria-hidden /> Loading forecast…
          </div>
        )}

        {forecastError && (
          <div className="dashboard__error" role="alert">
            Could not load forecast. The data ingestion service may still be warming up.
            Try again in a few minutes.
          </div>
        )}

        {forecast && (
          <>
            <h2 className="forecast-panel__lga-name">
              {forecast.lga_name}, {forecast.state_name}
              <span className={`flood-risk-badge flood-risk-badge--${forecast.flood_risk_class?.toLowerCase()}`}>
                {forecast.flood_risk_class}
              </span>
            </h2>

            {forecast.data_staleness_hours != null && forecast.data_staleness_hours > 6 && (
              <p className="forecast-panel__stale" role="status">
                ⚠ Data is {forecast.data_staleness_hours.toFixed(1)}h old.
              </p>
            )}

            {forecast.forecast.length > 0 ? (
              <div className="forecast-bars" role="list" aria-label="Daily forecast">
                {forecast.forecast.map(point => (
                  <ProbabilityBar key={point.date} point={point} />
                ))}
              </div>
            ) : (
              <div className="forecast-panel__no-data">
                <p>📡 No forecast data yet for <strong>{forecast.lga_name}</strong>.</p>
                <p style={{ marginTop: 8, fontSize: '0.82rem', opacity: 0.7 }}>
                  The ingestion service polls NIHSA and NiMet every 15 minutes.
                  Forecast data will appear once the first poll cycle completes.
                </p>
              </div>
            )}
          </>
        )}
      </section>

      {/* Annual Flood Outlook */}
      <section className="forecast-panel__afo" aria-label="Annual Flood Outlook" style={{ marginTop: 32 }}>
        <div className="afo-header">
          <h2>{t('forecast.afo_title')}</h2>
          <p className="afo-window">{t('forecast.afo_window')}</p>
          {afo && (
            <p className="afo-source">{afo.data_source_label} · {afo.total} communities</p>
          )}
        </div>

        {/* State filter for AFO */}
        <div className="afo-filter">
          <label htmlFor="afo-state">Filter by state:</label>
          <select
            id="afo-state"
            value={stateFilter}
            onChange={e => setStateFilter(e.target.value)}
          >
            <option value="">All states</option>
            {states.map(s => (
              <option key={s.state_code} value={s.state_code}>{s.state_name}</option>
            ))}
          </select>
        </div>

        {/* Legend */}
        <div className="afo-legend" aria-label="AFO classification legend">
          {([
            ['HIGHLY_PROBABLE', '#D32F2F', t('forecast.highly_probable')],
            ['PROBABLE',        '#F57C00', t('forecast.probable')],
            ['LOW_RISK',        '#388E3C', t('forecast.low_risk')],
          ] as [string, string, string][]).map(([cls, color, label]) => (
            <span key={cls} className="afo-legend__item">
              <span className="afo-legend__dot" style={{ background: color }} aria-hidden />
              {label}
            </span>
          ))}
        </div>

        {afoLoading && <div className="afo-loading" role="status">Loading AFO data…</div>}

        {afo && afo.communities.length > 0 && (
          <AfoTable communities={afo.communities} stateFilter={stateFilter} />
        )}

        {afo && afo.communities.length === 0 && (
          <div className="forecast-panel__no-data">
            <p>📡 Annual Flood Outlook data not yet available.</p>
            <p style={{ marginTop: 8, fontSize: '0.82rem', opacity: 0.7 }}>
              NIHSA community data will appear after ingestion completes.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
