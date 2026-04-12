/**
 * ReportForm — Community-Based Early Warning (CBEWS)
 *
 * Citizens report hazards and security incidents.
 * All reports are anonymous (phone never stored).
 * Security reports forwarded to relevant authorities.
 * Offline-capable: queued to IndexedDB and synced when back online.
 */
import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { alertsApi } from '../../api/alertsApi'
import type { SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const REPORT_TYPES = [
  { value: 'FLOOD_ACTIVE',        icon: '🌊', category: 'hazard'   },
  { value: 'FLOOD_RECEDING',      icon: '🌊', category: 'hazard'   },
  { value: 'ROAD_BLOCKED',        icon: '🚧', category: 'hazard'   },
  { value: 'SHELTER_FULL',        icon: '🏥', category: 'hazard'   },
  { value: 'DAMAGE',              icon: '🏚️', category: 'hazard'   },
  { value: 'BANDITRY',            icon: '🔫', category: 'security' },
  { value: 'CIVIL_UNREST',        icon: '⚡', category: 'security' },
  { value: 'KIDNAPPING',          icon: '🚨', category: 'security' },
  { value: 'SUSPICIOUS_ACTIVITY', icon: '👁️', category: 'security' },
  { value: 'ALL_CLEAR',           icon: '✅', category: 'hazard'   },
] as const

type ReportType = typeof REPORT_TYPES[number]['value']

interface LocationState {
  lat: number | null
  lng: number | null
  status: 'idle' | 'requesting' | 'granted' | 'denied'
  error?: string
}

export default function ReportForm({ lang }: Props) {
  const { t } = useTranslation()

  const [reportType,   setReportType]   = useState<ReportType | ''>('')
  const [description,  setDescription]  = useState('')
  const [photoFile,    setPhotoFile]    = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [location,     setLocation]     = useState<LocationState>({
    lat: null, lng: null, status: 'idle',
  })
  const [submitted, setSubmitted] = useState(false)

  const isSecurityReport = REPORT_TYPES.find(r => r.value === reportType)?.category === 'security'

  // ── Geolocation ───────────────────────────────────────────
  const requestLocation = () => {
    setLocation(prev => ({ ...prev, status: 'requesting' }))
    navigator.geolocation.getCurrentPosition(
      pos => setLocation({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        status: 'granted',
      }),
      err => setLocation({ lat: null, lng: null, status: 'denied', error: err.message }),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  useEffect(() => {
    // Auto-request location on mount
    if (navigator.geolocation) requestLocation()
  }, [])

  // ── Photo handling ────────────────────────────────────────
  const handlePhoto = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      alert('Photo must be under 5MB')
      return
    }
    setPhotoFile(file)
    const reader = new FileReader()
    reader.onload = ev => setPhotoPreview(ev.target?.result as string)
    reader.readAsDataURL(file)
  }

  // ── Submission ────────────────────────────────────────────
  const mutation = useMutation({
    mutationFn: async () => {
      if (!reportType) throw new Error('Select a report type')
      if (description.length < 10) throw new Error('Description too short')

      let photoUrl: string | undefined
      if (photoFile) {
        // Upload photo to /api/v1/upload first (multipart)
        const formData = new FormData()
        formData.append('file', photoFile)
        const uploadResp = await fetch('/api/v1/upload', {
          method: 'POST',
          body: formData,
        })
        if (uploadResp.ok) {
          const { url } = await uploadResp.json()
          photoUrl = url
        }
      }

      return alertsApi.submitReport({
        lat:         location.lat ?? 9.08,
        lng:         location.lng ?? 8.68,
        report_type: reportType,
        description,
        photo_url:   photoUrl,
        lang,
      })
    },
    onSuccess: () => {
      setSubmitted(true)
      // Queue for SW background sync if offline
      if (!navigator.onLine) {
        queueOfflineReport()
      }
    },
    onError: async (err) => {
      if (!navigator.onLine) {
        // Queue to IndexedDB for background sync
        await queueOfflineReport()
        setSubmitted(true)
      } else {
        console.error('Report submission failed:', err)
      }
    },
  })

  const queueOfflineReport = async () => {
    try {
      const db = await openIDB()
      const tx = db.transaction('pending-reports', 'readwrite')
      tx.objectStore('pending-reports').add({
        lat:         location.lat ?? 9.08,
        lng:         location.lng ?? 8.68,
        report_type: reportType,
        description,
        lang,
        queued_at:   Date.now(),
      })
      if ('serviceWorker' in navigator && 'SyncManager' in window) {
        const reg = await navigator.serviceWorker.ready
        await (reg as any).sync.register('sync-reports')
      }
    } catch (e) {
      console.warn('Offline queue failed:', e)
    }
  }

  const openIDB = (): Promise<IDBDatabase> =>
    new Promise((resolve, reject) => {
      const req = indexedDB.open('floodwatch-offline', 1)
      req.onsuccess = () => resolve(req.result)
      req.onerror   = () => reject(req.error)
    })

  const canSubmit = reportType !== '' && description.length >= 10 && !mutation.isPending

  // ── Success state ─────────────────────────────────────────
  if (submitted) {
    return (
      <div className="report-form report-form--success">
        <div className="report-form__success-icon" aria-hidden>✅</div>
        <h2 className="report-form__success-title">{t('report.success')}</h2>
        <p className="report-form__anon-note">{t('report.anonymous_note')}</p>
        {isSecurityReport && (
          <p className="report-form__security-note">{t('report.security_warning')}</p>
        )}
        <button
          className="btn btn--primary"
          onClick={() => {
            setSubmitted(false); setReportType(''); setDescription('')
            setPhotoFile(null); setPhotoPreview(null)
          }}
        >
          Submit Another Report
        </button>
      </div>
    )
  }

  return (
    <div className="report-form">
      <div className="report-form__header">
        <h1 className="report-form__title">{t('report.title')}</h1>
        <p className="report-form__subtitle">{t('report.subtitle')}</p>
      </div>

      {/* Incident type grid */}
      <section className="report-form__section">
        <label className="report-form__label">{t('report.type_label')}</label>
        <div className="report-type-grid">
          {REPORT_TYPES.map(rt => (
            <button
              key={rt.value}
              className={`report-type-btn ${reportType === rt.value ? 'active' : ''} ${
                rt.category === 'security' ? 'report-type-btn--security' : ''
              }`}
              onClick={() => setReportType(rt.value)}
              aria-pressed={reportType === rt.value}
            >
              <span className="report-type-btn__icon" aria-hidden>{rt.icon}</span>
              <span className="report-type-btn__label">
                {t(`report.types.${rt.value}`)}
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Security warning */}
      {isSecurityReport && (
        <div className="report-form__security-banner" role="alert">
          🔒 {t('report.security_warning')}
        </div>
      )}

      {/* Description */}
      <section className="report-form__section">
        <label className="report-form__label" htmlFor="report-desc">
          {t('report.description_label')}
        </label>
        <textarea
          id="report-desc"
          className="form-input report-form__textarea"
          rows={4}
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder={t('report.description_placeholder')}
          minLength={10}
          maxLength={500}
          aria-describedby="desc-count"
        />
        <span id="desc-count" className="report-form__char-count">
          {description.length}/500
        </span>
      </section>

      {/* Location */}
      <section className="report-form__section">
        <label className="report-form__label">{t('report.location_label')}</label>
        {location.status === 'requesting' && (
          <div className="report-form__location report-form__location--pending">
            <div className="spinner" aria-hidden style={{ width: 16, height: 16 }} />
            Detecting location…
          </div>
        )}
        {location.status === 'granted' && location.lat != null && (
          <div className="report-form__location report-form__location--ok">
            📍 {location.lat.toFixed(4)}, {location.lng?.toFixed(4)}
          </div>
        )}
        {location.status === 'denied' && (
          <div className="report-form__location report-form__location--denied">
            <span>Location access denied</span>
            <button className="btn btn--ghost btn--sm" onClick={requestLocation}>
              {t('report.location_allow')}
            </button>
          </div>
        )}
        <p className="report-form__location-hint">{t('report.location_hint')}</p>
      </section>

      {/* Photo (optional) */}
      <section className="report-form__section">
        <label className="report-form__label" htmlFor="report-photo">
          {t('report.photo_label')}
        </label>
        {photoPreview ? (
          <div className="report-form__photo-preview">
            <img src={photoPreview} alt="Preview" className="report-form__photo-img" />
            <button
              className="btn btn--ghost btn--sm"
              onClick={() => { setPhotoFile(null); setPhotoPreview(null) }}
            >
              Remove
            </button>
          </div>
        ) : (
          <label className="report-form__photo-upload" htmlFor="report-photo">
            <span aria-hidden>📷</span> Attach photo
            <input
              id="report-photo"
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              onChange={handlePhoto}
            />
          </label>
        )}
      </section>

      {/* Anonymous note */}
      <p className="report-form__anon-note">
        🔒 {t('report.anonymous_note')}
      </p>

      {/* Submit */}
      {mutation.isError && (
        <div className="report-form__error" role="alert">
          {navigator.onLine
            ? 'Submission failed. Please try again.'
            : 'You are offline. Report saved and will be sent when you reconnect.'}
        </div>
      )}

      <button
        className="btn btn--primary btn--full"
        onClick={() => mutation.mutate()}
        disabled={!canSubmit}
        aria-busy={mutation.isPending}
      >
        {mutation.isPending ? t('report.submitting') : t('report.submit')}
      </button>
    </div>
  )
}
