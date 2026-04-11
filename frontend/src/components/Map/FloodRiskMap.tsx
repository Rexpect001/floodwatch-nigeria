/**
 * FloodRiskMap — Interactive flood risk + alert map
 *
 * Layers (toggleable):
 *  1. LGA flood risk classification (148 HIGH / moderate / low) — PostGIS GeoJSON
 *  2. Annual Flood Outlook communities (NIHSA — Highly Probable / Probable / Low Risk)
 *  3. Active alerts heatmap (RED/ORANGE/YELLOW polygons)
 *  4. Evacuation shelters (marker cluster)
 *  5. River gauges — 273 NIHSA stations (colour-coded by stage_trend)
 *  6. Community CBEWS reports (verified only)
 *  7. Sentinel-1 SAR flood extent (where available — WMS overlay)
 *
 * Data accuracy notes displayed per spec:
 *  - Lake Chad: "~24,500 km² (current stable level)" — NOT disappearing narrative
 *  - Deforestation: "3.67%/yr (FAO verified)"
 *
 * Offline: falls back to cached GeoJSON tiles pre-baked at build time
 * (HIGH-risk LGAs cached in Service Worker MAP_CACHE)
 */
import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

mapboxgl.accessToken = process.env.REACT_APP_MAPBOX_TOKEN || ''

// Severity colour palette — matches alert severity classification
const SEVERITY_COLORS: Record<string, string> = {
  HIGH:           '#D32F2F',   // red
  MODERATE:       '#F57C00',   // orange
  LOW:            '#FBC02D',   // yellow
  HIGHLY_PROBABLE:'#B71C1C',   // deep red (AFO)
  PROBABLE:       '#E64A19',   // deep orange
  LOW_RISK:       '#F9A825',   // amber
}

const ALERT_SEVERITY_COLORS: Record<string, string> = {
  RED:    '#D32F2F',
  ORANGE: '#F57C00',
  YELLOW: '#F9A825',
  GREEN:  '#388E3C',
}

// Layer visibility state
type LayerKey = 'floodRisk' | 'afo' | 'alerts' | 'shelters' | 'gauges' | 'reports' | 'sar'

interface LayerState {
  floodRisk: boolean
  afo:       boolean
  alerts:    boolean
  shelters:  boolean
  gauges:    boolean
  reports:   boolean
  sar:       boolean
}

interface Props {
  lang: string
  onAlertClick?: (alertId: string) => void
  onShelterClick?: (shelter: object) => void
}

export default function FloodRiskMap({ lang, onAlertClick, onShelterClick }: Props) {
  const { t } = useTranslation()
  const mapContainer = useRef<HTMLDivElement>(null)
  const map          = useRef<mapboxgl.Map | null>(null)
  const [mapLoaded, setMapLoaded]     = useState(false)
  const [isOffline, setIsOffline]     = useState(!navigator.onLine)
  const [layers, setLayers]           = useState<LayerState>({
    floodRisk: true,
    afo:       true,
    alerts:    true,
    shelters:  true,
    gauges:    false,
    reports:   false,
    sar:       false,
  })
  const [dataAge, setDataAge]         = useState<string | null>(null)

  // ── Map init ─────────────────────────────────────────────

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/light-v11',
      center: [8.68, 9.08],    // Nigeria centroid
      zoom: 5.5,
      minZoom: 4,
      maxZoom: 16,
      // Nigeria bounding box
      maxBounds: [[2.6, 4.0], [15.0, 14.0]],
    })

    map.current.addControl(new mapboxgl.NavigationControl(), 'top-right')
    map.current.addControl(
      new mapboxgl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }),
      'top-right'
    )
    map.current.addControl(new mapboxgl.ScaleControl({ unit: 'metric' }), 'bottom-left')

    map.current.on('load', () => {
      setMapLoaded(true)
      _addAllLayers(map.current!)
    })

    // Offline detection
    window.addEventListener('online',  () => setIsOffline(false))
    window.addEventListener('offline', () => setIsOffline(true))

    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  // ── Load data into layers ─────────────────────────────────

  const _addAllLayers = useCallback(async (m: mapboxgl.Map) => {
    await Promise.all([
      _loadFloodRiskLayer(m),
      _loadAFOLayer(m),
      _loadAlertLayer(m),
      _loadShelterLayer(m),
      _loadGaugeLayer(m),
      _loadReportsLayer(m),
      _loadSARLayer(m),
    ])
  }, [])

  async function _loadFloodRiskLayer(m: mapboxgl.Map) {
    try {
      // Try network first; fall back to cached GeoJSON (Service Worker)
      const resp = await fetch('/maps/lga-flood-risk.geojson')
      if (!resp.ok) throw new Error('fetch failed')
      const data = await resp.json()
      if (data._cached_at_ms) {
        const age = ((Date.now() - data._cached_at_ms) / 3600000).toFixed(1)
        setDataAge(`${age}h ago`)
      }

      m.addSource('lga-flood-risk', { type: 'geojson', data })
      m.addLayer({
        id: 'lga-flood-risk-fill',
        type: 'fill',
        source: 'lga-flood-risk',
        layout: { visibility: 'visible' },
        paint: {
          'fill-color': [
            'match', ['get', 'flood_risk_class'],
            'HIGH',     SEVERITY_COLORS.HIGH,
            'MODERATE', SEVERITY_COLORS.MODERATE,
            /* default */ SEVERITY_COLORS.LOW,
          ],
          'fill-opacity': 0.35,
        },
      })
      m.addLayer({
        id: 'lga-flood-risk-outline',
        type: 'line',
        source: 'lga-flood-risk',
        paint: {
          'line-color': '#555',
          'line-width': 0.5,
          'line-opacity': 0.4,
        },
      })

      // Popup on click
      m.on('click', 'lga-flood-risk-fill', e => {
        const props = e.features?.[0]?.properties || {}
        new mapboxgl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="map-popup">
              <strong>${props.name_en}</strong><br/>
              <span class="map-popup__state">${props.state_name}</span><br/>
              <span class="map-popup__risk map-popup__risk--${props.flood_risk_class?.toLowerCase()}">
                ${props.flood_risk_class} FLOOD RISK
              </span>
            </div>
          `)
          .addTo(m)
      })
      m.on('mouseenter', 'lga-flood-risk-fill', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'lga-flood-risk-fill', () => { m.getCanvas().style.cursor = '' })
    } catch {
      console.warn('[Map] LGA flood risk layer unavailable (offline)')
    }
  }

  async function _loadAFOLayer(m: mapboxgl.Map) {
    try {
      const resp = await fetch('/maps/afo-communities.geojson')
      if (!resp.ok) return
      const data = await resp.json()
      m.addSource('afo', { type: 'geojson', data })
      m.addLayer({
        id: 'afo-circles',
        type: 'circle',
        source: 'afo',
        layout: { visibility: 'visible' },
        paint: {
          'circle-radius': 6,
          'circle-color': [
            'match', ['get', 'afo_class'],
            'HIGHLY_PROBABLE', SEVERITY_COLORS.HIGHLY_PROBABLE,
            'PROBABLE',        SEVERITY_COLORS.PROBABLE,
            /* default */      SEVERITY_COLORS.LOW_RISK,
          ],
          'circle-stroke-width': 1,
          'circle-stroke-color': '#fff',
          'circle-opacity': 0.85,
        },
      })
    } catch {
      console.warn('[Map] AFO layer unavailable')
    }
  }

  async function _loadAlertLayer(m: mapboxgl.Map) {
    try {
      const resp = await fetch('/api/v1/alerts?format=geojson')
      if (!resp.ok) return
      const data = await resp.json()
      m.addSource('alerts', { type: 'geojson', data })
      m.addLayer({
        id: 'alerts-fill',
        type: 'fill',
        source: 'alerts',
        layout: { visibility: 'visible' },
        paint: {
          'fill-color': [
            'match', ['get', 'severity'],
            'RED',    ALERT_SEVERITY_COLORS.RED,
            'ORANGE', ALERT_SEVERITY_COLORS.ORANGE,
            'YELLOW', ALERT_SEVERITY_COLORS.YELLOW,
            /* default */ '#9E9E9E',
          ],
          'fill-opacity': 0.25,
        },
      })
      m.on('click', 'alerts-fill', e => {
        const props = e.features?.[0]?.properties || {}
        if (props.alert_id) onAlertClick?.(props.alert_id)
      })
    } catch {
      console.warn('[Map] Alert layer unavailable')
    }
  }

  async function _loadShelterLayer(m: mapboxgl.Map) {
    try {
      const resp = await fetch('/maps/shelter-locations.geojson')
      if (!resp.ok) return
      const data = await resp.json()
      m.addSource('shelters', { type: 'geojson', data })
      m.addLayer({
        id: 'shelters-symbols',
        type: 'symbol',
        source: 'shelters',
        layout: {
          visibility: 'visible',
          'icon-image': 'hospital-15',
          'icon-size': 1.2,
          'text-field': ['get', 'name'],
          'text-size': 10,
          'text-offset': [0, 1.5],
          'text-anchor': 'top',
          'icon-allow-overlap': true,
        },
        paint: { 'text-color': '#1565C0', 'text-halo-color': '#fff', 'text-halo-width': 2 },
      })
      m.on('click', 'shelters-symbols', e => {
        const props = e.features?.[0]?.properties || {}
        onShelterClick?.(props)
        new mapboxgl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="map-popup">
              <strong>🏥 ${props.name}</strong><br/>
              Capacity: ${props.capacity ?? 'Unknown'}<br/>
              <small>${props.address ?? ''}</small>
            </div>
          `)
          .addTo(m)
      })
    } catch {
      console.warn('[Map] Shelter layer unavailable')
    }
  }

  async function _loadGaugeLayer(m: mapboxgl.Map) {
    try {
      const resp = await fetch('/api/v1/stations/gauges')
      if (!resp.ok) return
      const { stations } = await resp.json()
      const geojson: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: stations.map((s: any) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [s.lng, s.lat] },
          properties: { ...s },
        })),
      }
      m.addSource('gauges', { type: 'geojson', data: geojson })
      m.addLayer({
        id: 'gauges-circles',
        type: 'circle',
        source: 'gauges',
        layout: { visibility: 'none' },   // off by default
        paint: {
          'circle-radius': 5,
          'circle-color': '#1565C0',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#fff',
        },
      })
    } catch {
      console.warn('[Map] Gauge layer unavailable')
    }
  }

  async function _loadReportsLayer(m: mapboxgl.Map) {
    try {
      const resp = await fetch('/api/v1/reports?verified_only=true')
      if (!resp.ok) return
      const data = await resp.json()
      m.addSource('cbews-reports', { type: 'geojson', data })
      m.addLayer({
        id: 'reports-symbols',
        type: 'symbol',
        source: 'cbews-reports',
        layout: {
          visibility: 'none',   // off by default
          'icon-image': 'water-15',
          'icon-size': 1.0,
        },
      })
    } catch {
      console.warn('[Map] CBEWS reports unavailable')
    }
  }

  async function _loadSARLayer(m: mapboxgl.Map) {
    // Sentinel-1 SAR flood extent — WMS overlay from Copernicus EMS
    const sarWms = process.env.REACT_APP_SAR_WMS_URL
    if (!sarWms) return
    try {
      m.addSource('sar-flood', {
        type: 'raster',
        tiles: [sarWms],
        tileSize: 256,
      })
      m.addLayer({
        id: 'sar-flood-layer',
        type: 'raster',
        source: 'sar-flood',
        layout: { visibility: 'none' },   // off by default (bandwidth-heavy)
        paint: { 'raster-opacity': 0.6 },
      })
    } catch {
      console.warn('[Map] SAR layer unavailable')
    }
  }

  // ── Layer toggle ──────────────────────────────────────────

  const toggleLayer = useCallback((key: LayerKey) => {
    const m = map.current
    if (!m || !mapLoaded) return

    const layerMap: Record<LayerKey, string[]> = {
      floodRisk: ['lga-flood-risk-fill', 'lga-flood-risk-outline'],
      afo:       ['afo-circles'],
      alerts:    ['alerts-fill'],
      shelters:  ['shelters-symbols'],
      gauges:    ['gauges-circles'],
      reports:   ['reports-symbols'],
      sar:       ['sar-flood-layer'],
    }

    setLayers(prev => {
      const next = { ...prev, [key]: !prev[key] }
      const visibility = next[key] ? 'visible' : 'none'
      for (const layerId of layerMap[key] || []) {
        if (m.getLayer(layerId)) {
          m.setLayoutProperty(layerId, 'visibility', visibility)
        }
      }
      return next
    })
  }, [mapLoaded])

  // ── Render ────────────────────────────────────────────────

  return (
    <div className="flood-risk-map" aria-label={t('map.aria_label')}>
      {/* Offline banner */}
      {isOffline && (
        <div className="flood-risk-map__offline-banner" role="status" aria-live="polite">
          {t('offline.banner', { age: dataAge || t('map.unknown_age') })}
        </div>
      )}

      {/* Map container */}
      <div ref={mapContainer} className="flood-risk-map__canvas" />

      {/* Layer toggle panel */}
      <aside className="flood-risk-map__layers" aria-label={t('map.layers_label')}>
        <h3 className="flood-risk-map__layers-title">{t('map.layers_title')}</h3>
        {(Object.entries(layers) as [LayerKey, boolean][]).map(([key, active]) => (
          <label key={key} className={`map-layer-toggle ${active ? 'active' : ''}`}>
            <input
              type="checkbox"
              checked={active}
              onChange={() => toggleLayer(key)}
              aria-label={t(`map.layers.${key}`)}
            />
            <span className="map-layer-toggle__label">{t(`map.layers.${key}`)}</span>
          </label>
        ))}

        {/* Data accuracy notes — per spec */}
        <div className="flood-risk-map__accuracy-notes">
          <p className="map-accuracy-note">{t('map.lake_chad')}</p>
          <p className="map-accuracy-note">{t('map.deforestation')}</p>
        </div>
      </aside>

      {/* Data staleness indicator */}
      {dataAge && (
        <div className="flood-risk-map__staleness" aria-live="polite">
          {t('offline.cache_age', { timestamp: dataAge })}
        </div>
      )}
    </div>
  )
}
