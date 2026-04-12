/**
 * FloodRiskMap — Interactive flood risk + alert map
 * Uses Leaflet + OpenStreetMap (free, no token required)
 *
 * Layers (toggleable):
 *  1. LGA flood risk classification (148 HIGH / moderate / low) — PostGIS GeoJSON
 *  2. Annual Flood Outlook communities (NIHSA — Highly Probable / Probable / Low Risk)
 *  3. Active alerts overlay (RED/ORANGE/YELLOW polygons)
 *  4. Evacuation shelters (markers)
 *  5. River gauges — 273 NIHSA stations
 *  6. Community CBEWS reports (verified only)
 */
import React, { useEffect, useState, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  CircleMarker,
  Marker,
  Popup,
  useMap,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { GeoContext } from '../../App'

// Fix Leaflet default marker icon path broken by bundlers
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

// User location marker icon — amber glow to match new brand
const USER_ICON = L.divIcon({
  className: '',
  html: '<div style="width:16px;height:16px;background:#14B8A6;border:3px solid #fff;border-radius:50%;box-shadow:0 0 0 5px rgba(20,184,166,0.35)"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
})

const SEVERITY_COLORS: Record<string, string> = {
  HIGH:            '#D32F2F',
  MODERATE:        '#F57C00',
  LOW:             '#FBC02D',
  HIGHLY_PROBABLE: '#B71C1C',
  PROBABLE:        '#E64A19',
  LOW_RISK:        '#F9A825',
}

const ALERT_COLORS: Record<string, string> = {
  RED:    '#D32F2F',
  ORANGE: '#F57C00',
  YELLOW: '#F9A825',
  GREEN:  '#388E3C',
}

type LayerKey = 'floodRisk' | 'afo' | 'alerts' | 'shelters' | 'gauges' | 'reports'

interface GeoData {
  floodRisk: GeoJSON.FeatureCollection | null
  afo:       GeoJSON.FeatureCollection | null
  alerts:    GeoJSON.FeatureCollection | null
  shelters:  GeoJSON.FeatureCollection | null
  gauges:    any[]
  reports:   GeoJSON.FeatureCollection | null
}

interface Props {
  lang?: string
  heroMode?:       boolean            // compact view inside Dashboard hero card
  onAlertClick?:   (alertId: string) => void
  onShelterClick?: (shelter: object)  => void
}

// Fly to user position when GeoContext updates (only inside MapContainer)
function AutoLocate({ userPos }: { userPos: [number,number] | null }) {
  const map = useMap()
  useEffect(() => {
    if (userPos) {
      map.flyTo(userPos, 10, { animate: true, duration: 1.5 })
    }
  }, [userPos?.[0], userPos?.[1]])
  return null
}

// ── Locate Me button (inside MapContainer) ───────────────────
function LocateMeButton({ onLocate }: { onLocate: (latlng: [number,number]) => void }) {
  const map = useMap()
  const [locating, setLocating] = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const locate = () => {
    if (!navigator.geolocation) { setError('GPS not available'); return }
    setLocating(true); setError(null)
    navigator.geolocation.getCurrentPosition(
      pos => {
        const latlng: [number,number] = [pos.coords.latitude, pos.coords.longitude]
        map.flyTo(latlng, 12, { animate: true, duration: 1.2 })
        onLocate(latlng)
        setLocating(false)
      },
      () => { setError('Location denied'); setLocating(false) },
      { timeout: 8000, maximumAge: 60000 }
    )
  }

  return (
    <div className="map-locate-btn" title="Centre map on my location">
      <button onClick={locate} disabled={locating} aria-label="Locate me">
        {locating ? '⏳' : '📍'}
      </button>
      {error && <span className="map-locate-btn__error">{error}</span>}
    </div>
  )
}

export default function FloodRiskMap({ onAlertClick, onShelterClick, heroMode }: Props) {
  const { t } = useTranslation()
  const geo = useContext(GeoContext)
  const [isOffline, setIsOffline] = useState(!navigator.onLine)
  const [dataAge,   setDataAge]   = useState<string | null>(null)

  // Seed position from GeoContext; user can also tap "Locate Me" to update
  const [userPos, setUserPos] = useState<[number,number] | null>(
    geo.location ? [geo.location.lat, geo.location.lng] : null
  )

  // When GeoContext resolves, update userPos
  useEffect(() => {
    if (geo.location && !userPos) {
      setUserPos([geo.location.lat, geo.location.lng])
    }
  }, [geo.location])
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    floodRisk: true,
    afo:       true,
    alerts:    true,
    shelters:  true,
    gauges:    false,
    reports:   false,
  })
  const [data, setData] = useState<GeoData>({
    floodRisk: null, afo: null, alerts: null,
    shelters: null,  gauges: [], reports: null,
  })

  useEffect(() => {
    window.addEventListener('online',  () => setIsOffline(false))
    window.addEventListener('offline', () => setIsOffline(true))

    const load = async (url: string) => {
      try {
        const r = await fetch(url)
        if (!r.ok) return null
        return await r.json()
      } catch { return null }
    }

    Promise.all([
      load('/maps/lga-flood-risk.geojson'),
      load('/maps/afo-communities.geojson'),
      load('/api/v1/alerts?format=geojson'),
      load('/maps/shelter-locations.geojson'),
      load('/api/v1/stations/gauges'),
      load('/api/v1/reports?verified_only=true'),
    ]).then(([floodRisk, afo, alerts, shelters, gaugesResp, reports]) => {
      if (floodRisk?._cached_at_ms) {
        const age = ((Date.now() - floodRisk._cached_at_ms) / 3_600_000).toFixed(1)
        setDataAge(`${age}h ago`)
      }
      setData({
        floodRisk: floodRisk ?? null,
        afo:       afo       ?? null,
        alerts:    alerts    ?? null,
        shelters:  shelters  ?? null,
        gauges:    gaugesResp?.stations ?? [],
        reports:   reports   ?? null,
      })
    })
  }, [])

  const toggleLayer = (key: LayerKey) =>
    setLayers(prev => ({ ...prev, [key]: !prev[key] }))

  // Initial map center: user location if known, else Nigeria centroid
  const initialCenter: [number, number] = userPos ?? [9.08, 8.68]
  const initialZoom = userPos ? 10 : 6

  return (
    <div className="flood-risk-map" aria-label={t('map.aria_label', 'Flood risk map')}>
      {isOffline && (
        <div className="flood-risk-map__offline-banner" role="status" aria-live="polite">
          {t('offline.banner', { age: dataAge || t('map.unknown_age', 'unknown') })}
        </div>
      )}

      <MapContainer
        center={initialCenter}
        zoom={initialZoom}
        minZoom={4}
        maxZoom={16}
        className="flood-risk-map__canvas"
        style={{ height: heroMode ? 280 : '100%', width: '100%' }}
        zoomControl={!heroMode}
        attributionControl={!heroMode}
      >
        {/* Auto-fly to user position when GeoContext resolves */}
        <AutoLocate userPos={userPos} />
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        {/* LGA Flood Risk Layer */}
        {layers.floodRisk && data.floodRisk && (
          <GeoJSON
            key="flood-risk"
            data={data.floodRisk}
            style={(feature) => ({
              fillColor: SEVERITY_COLORS[feature?.properties?.flood_risk_class] ?? SEVERITY_COLORS.LOW,
              fillOpacity: 0.35,
              color: '#555',
              weight: 0.5,
              opacity: 0.4,
            })}
            onEachFeature={(feature, layer) => {
              const p = feature.properties || {}
              layer.bindPopup(`
                <div class="map-popup">
                  <strong>${p.name_en ?? ''}</strong><br/>
                  <span>${p.state_name ?? ''}</span><br/>
                  <span class="map-popup__risk">${p.flood_risk_class ?? ''} FLOOD RISK</span>
                </div>
              `)
            }}
          />
        )}

        {/* AFO Communities Layer */}
        {layers.afo && data.afo && (
          <GeoJSON
            key="afo"
            data={data.afo}
            pointToLayer={(feature, latlng) =>
              L.circleMarker(latlng, {
                radius: 6,
                fillColor: SEVERITY_COLORS[feature.properties?.afo_class] ?? SEVERITY_COLORS.LOW_RISK,
                color: '#fff',
                weight: 1,
                fillOpacity: 0.85,
              })
            }
            onEachFeature={(feature, layer) => {
              const p = feature.properties || {}
              layer.bindPopup(`<strong>${p.community ?? ''}</strong><br/>${p.afo_class ?? ''}`)
            }}
          />
        )}

        {/* Active Alerts Layer */}
        {layers.alerts && data.alerts && (
          <GeoJSON
            key="alerts"
            data={data.alerts}
            style={(feature) => ({
              fillColor: ALERT_COLORS[feature?.properties?.severity] ?? '#9E9E9E',
              fillOpacity: 0.25,
              color: ALERT_COLORS[feature?.properties?.severity] ?? '#9E9E9E',
              weight: 1,
            })}
            onEachFeature={(feature, layer) => {
              const p = feature.properties || {}
              layer.on('click', () => { if (p.alert_id) onAlertClick?.(p.alert_id) })
              layer.bindPopup(`<strong>${p.severity ?? ''}</strong><br/>${p.description ?? ''}`)
            }}
          />
        )}

        {/* Evacuation Shelters */}
        {layers.shelters && data.shelters && (
          <GeoJSON
            key="shelters"
            data={data.shelters}
            onEachFeature={(feature, layer) => {
              const p = feature.properties || {}
              onShelterClick?.(p)
              layer.bindPopup(`
                <div class="map-popup">
                  <strong>🏥 ${p.name ?? ''}</strong><br/>
                  Capacity: ${p.capacity ?? 'Unknown'}<br/>
                  <small>${p.address ?? ''}</small>
                </div>
              `)
            }}
          />
        )}

        {/* River Gauges */}
        {layers.gauges && data.gauges.map((s: any, i: number) => (
          <CircleMarker
            key={i}
            center={[s.lat, s.lng]}
            radius={5}
            pathOptions={{ fillColor: '#1565C0', color: '#fff', weight: 1.5, fillOpacity: 1 }}
          >
            <Popup><strong>{s.name}</strong><br/>Stage: {s.stage_trend ?? 'N/A'}</Popup>
          </CircleMarker>
        ))}

        {/* CBEWS Community Reports */}
        {layers.reports && data.reports && (
          <GeoJSON
            key="reports"
            data={data.reports}
            pointToLayer={(_, latlng) =>
              L.circleMarker(latlng, { radius: 5, fillColor: '#1565C0', fillOpacity: 0.9 })
            }
          />
        )}

        {/* User location marker — "You are here" */}
        {userPos && (
          <Marker position={userPos} icon={USER_ICON}>
            <Popup>
              <div className="map-popup">
                <strong>📍 You are here</strong>
                {geo.location?.placeName && <span>{geo.location.placeName}</span>}
              </div>
            </Popup>
          </Marker>
        )}

        {/* Locate Me button (hidden in heroMode — location auto-set) */}
        {!heroMode && <LocateMeButton onLocate={setUserPos} />}
      </MapContainer>

      {/* Layer toggle panel — hidden in heroMode */}
      {heroMode && dataAge && (
        <div className="flood-risk-map__staleness" aria-live="polite">
          Data: {dataAge}
        </div>
      )}
      {!heroMode && (
        <>
          <aside className="flood-risk-map__layers" aria-label={t('map.layers_label', 'Map layers')}>
            <h3 className="flood-risk-map__layers-title">{t('map.layers_title', 'Layers')}</h3>
            {(Object.entries(layers) as [LayerKey, boolean][]).map(([key, active]) => (
              <label key={key} className={`map-layer-toggle ${active ? 'active' : ''}`}>
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => toggleLayer(key)}
                  aria-label={t(`map.layers.${key}`, key)}
                />
                <span className="map-layer-toggle__label">{t(`map.layers.${key}`, key)}</span>
              </label>
            ))}
            <div className="flood-risk-map__accuracy-notes">
              <p className="map-accuracy-note">{t('map.lake_chad', 'Lake Chad: ~24,500 km²')}</p>
              <p className="map-accuracy-note">{t('map.deforestation', 'Deforestation: 3.67%/yr (FAO)')}</p>
            </div>
          </aside>

          {dataAge && (
            <div className="flood-risk-map__staleness" aria-live="polite">
              {t('offline.cache_age', { timestamp: dataAge })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
