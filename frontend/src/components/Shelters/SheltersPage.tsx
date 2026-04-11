/**
 * SheltersPage — Evacuation shelter locator
 *
 * Shows all NEMA/Red Cross shelters from shelter-locations.geojson
 * with a mini Leaflet map and searchable card list.
 */
import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { SupportedLang } from '../../i18n'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl:       'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const SHELTER_ICON = L.divIcon({
  className: '',
  html: '<div style="background:#388E3C;color:#fff;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:13px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.4)">🏥</div>',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

interface Shelter {
  name: string
  capacity: number
  address: string
  status: 'OPEN' | 'FULL' | 'CLOSED'
  lat: number
  lng: number
}

function FlyTo({ pos }: { pos: [number,number] | null }) {
  const map = useMap()
  useEffect(() => { if (pos) map.flyTo(pos, 13, { animate: true, duration: 1 }) }, [pos, map])
  return null
}

interface Props { lang?: SupportedLang }

export default function SheltersPage({ lang }: Props) {
  const { t } = useTranslation()
  const [shelters, setShelters] = useState<Shelter[]>([])
  const [query,    setQuery]    = useState('')
  const [focused,  setFocused]  = useState<[number,number] | null>(null)
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    fetch('/maps/shelter-locations.geojson')
      .then(r => r.json())
      .then((fc: any) => {
        const list: Shelter[] = fc.features.map((f: any) => ({
          name:     f.properties.name,
          capacity: f.properties.capacity,
          address:  f.properties.address,
          status:   f.properties.status as Shelter['status'],
          lng:      f.geometry.coordinates[0],
          lat:      f.geometry.coordinates[1],
        }))
        setShelters(list)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = shelters.filter(s =>
    s.name.toLowerCase().includes(query.toLowerCase()) ||
    s.address.toLowerCase().includes(query.toLowerCase())
  )

  return (
    <div className="shelters-page">
      <h1 className="shelters-page__title">🏥 {t('shelters.title', 'Evacuation Shelters')}</h1>
      <p className="shelters-page__subtitle">
        {t('shelters.subtitle', 'NEMA-approved evacuation centres — open during flood emergencies')}
      </p>

      {/* Mini map */}
      <div className="shelters-page__map">
        <MapContainer
          center={[9.08, 8.68]}
          zoom={6}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={false}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
          {shelters.map((s, i) => (
            <Marker key={i} position={[s.lat, s.lng]} icon={SHELTER_ICON}>
              <Popup>
                <strong>{s.name}</strong><br/>
                Capacity: {s.capacity.toLocaleString()}<br/>
                <small>{s.address}</small><br/>
                <span style={{ color: s.status === 'OPEN' ? '#388E3C' : '#D32F2F', fontWeight: 700 }}>
                  {s.status}
                </span>
              </Popup>
            </Marker>
          ))}
          <FlyTo pos={focused} />
        </MapContainer>
      </div>

      {/* Search */}
      <div className="shelters-page__search">
        <input
          className="form-input"
          type="search"
          placeholder={t('shelters.search_placeholder', 'Search by name or address…')}
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label="Search shelters"
        />
        <span className="shelters-page__count">
          {filtered.length} {t('shelters.count_label', 'shelters')}
        </span>
      </div>

      {/* Card list */}
      {loading ? (
        <div className="shelters-page__loading" role="status">
          <div className="spinner" aria-hidden /> Loading shelters…
        </div>
      ) : (
        <ul className="shelters-list" aria-label="Shelter list">
          {filtered.map((s, i) => (
            <li
              key={i}
              className={`shelter-card shelter-card--${s.status.toLowerCase()}`}
              onClick={() => setFocused([s.lat, s.lng])}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && setFocused([s.lat, s.lng])}
              aria-label={`${s.name}, capacity ${s.capacity}`}
            >
              <div className="shelter-card__header">
                <span className="shelter-card__name">🏥 {s.name}</span>
                <span className={`shelter-card__status shelter-card__status--${s.status.toLowerCase()}`}>
                  {s.status}
                </span>
              </div>
              <div className="shelter-card__meta">
                <span className="shelter-card__capacity">
                  👥 {s.capacity.toLocaleString()} capacity
                </span>
                <span className="shelter-card__address">📍 {s.address}</span>
              </div>
              <button
                className="shelter-card__directions"
                onClick={e => {
                  e.stopPropagation()
                  window.open(`https://maps.google.com/?q=${s.lat},${s.lng}`, '_blank', 'noopener')
                }}
                aria-label={`Get directions to ${s.name}`}
              >
                🗺 Get Directions
              </button>
            </li>
          ))}
        </ul>
      )}

      {!loading && filtered.length === 0 && (
        <p className="shelters-page__empty">No shelters found for "{query}"</p>
      )}

      <div className="shelters-page__footer">
        <p><strong>Emergency:</strong> Call NEMA 0800-CALL-NEMA (0800-2255-6362)</p>
        <p><strong>USSD:</strong> <a href="tel:*384*3566*3%23" className="ussd-link">*384*FLOOD#</a> on any phone</p>
      </div>
    </div>
  )
}
