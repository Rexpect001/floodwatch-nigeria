/**
 * SubscribeForm — SMS alert subscription
 *
 * Fields:
 *   - Nigerian phone number (+234XXXXXXXXXX)
 *   - Language preference (en/ha/yo/ig/pg)
 *   - LGA selection (multi, up to 10)
 *   - Alert threshold (RED/ORANGE/YELLOW/GREEN)
 *
 * Features:
 *   - Offline-aware: queues subscription via Background Sync if offline
 *   - USSD fallback hint: Dial *384*FLOOD#
 *   - Validates Nigerian MSISDN format
 *   - Success state shows confirmation with LGA name
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { alertsApi } from '../../api/alertsApi'
import { SUPPORTED_LANGUAGES, type SupportedLang } from '../../i18n'

interface Props { lang: SupportedLang }

const SEVERITY_OPTIONS = [
  { value: 'RED',    label: 'severity.RED'    },
  { value: 'ORANGE', label: 'severity.ORANGE' },
  { value: 'YELLOW', label: 'severity.YELLOW' },
  { value: 'GREEN',  label: 'severity.GREEN'  },
] as const

// Key high-risk LGAs for quick selection
const LGA_OPTIONS = [
  { id: 1,  name: 'Lokoja',          state: 'Kogi'      },
  { id: 2,  name: 'Makurdi',         state: 'Benue'     },
  { id: 3,  name: 'Onitsha South',   state: 'Anambra'   },
  { id: 4,  name: 'Maiduguri',       state: 'Borno'     },
  { id: 5,  name: 'Yenagoa',         state: 'Bayelsa'   },
  { id: 6,  name: 'Port Harcourt',   state: 'Rivers'    },
  { id: 7,  name: 'Warri South',     state: 'Delta'     },
  { id: 8,  name: 'Birnin Kebbi',    state: 'Kebbi'     },
  { id: 9,  name: 'Hadejia',         state: 'Jigawa'    },
  { id: 10, name: 'Sokoto North',    state: 'Sokoto'    },
  { id: 11, name: 'Calabar South',   state: 'Cross River'},
  { id: 12, name: 'Ibaji',           state: 'Kogi'      },
  { id: 13, name: 'Wukari',          state: 'Taraba'    },
  { id: 14, name: 'Ogbaru',          state: 'Anambra'   },
  { id: 15, name: 'Ilaje',           state: 'Ondo'      },
]

function normalizePhone(raw: string): string {
  // Accept 080XXXXXXXX or +2348XXXXXXXXX or 2348XXXXXXXXX
  const digits = raw.replace(/\D/g, '')
  if (digits.startsWith('234') && digits.length === 13) return `+${digits}`
  if (digits.startsWith('0') && digits.length === 11) return `+234${digits.slice(1)}`
  return raw
}

function isValidNigerianPhone(msisdn: string): boolean {
  return /^\+234[789][01]\d{8}$/.test(msisdn)
}

async function queueOfflineSubscription(data: object) {
  if ('serviceWorker' in navigator && 'SyncManager' in window) {
    const db = await openIDB()
    await addToStore(db, 'pending-subscriptions', { data, queued_at: Date.now() })
    const sw = await navigator.serviceWorker.ready
    await (sw as any).sync.register('sync-subscriptions')
  }
}

function openIDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('floodwatch-sync', 1)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function addToStore(db: IDBDatabase, store: string, item: object): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).add(item)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export default function SubscribeForm({ lang }: Props) {
  const { t } = useTranslation()

  const [phone, setPhone] = useState('')
  const [selectedLang, setSelectedLang] = useState<SupportedLang>(lang)
  const [selectedLgas, setSelectedLgas] = useState<number[]>([])
  const [threshold, setThreshold] = useState<'RED'|'ORANGE'|'YELLOW'|'GREEN'>('ORANGE')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const msisdn = normalizePhone(phone)
  const phoneValid = isValidNigerianPhone(msisdn)
  const canSubmit = phoneValid && selectedLgas.length > 0 && !submitting

  const toggleLga = (id: number) => {
    setSelectedLgas(prev =>
      prev.includes(id)
        ? prev.filter(x => x !== id)
        : prev.length < 10 ? [...prev, id] : prev
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)

    const payload = { msisdn, lang: selectedLang, lga_ids: selectedLgas, severity_threshold: threshold }

    try {
      if (!navigator.onLine) {
        await queueOfflineSubscription(payload)
        setSuccess(true)
      } else {
        await alertsApi.subscribe(payload)
        setSuccess(true)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Subscription failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const selectedLgaNames = LGA_OPTIONS
    .filter(l => selectedLgas.includes(l.id))
    .map(l => l.name)
    .join(', ')

  if (success) {
    return (
      <div className="subscribe-success" role="status" aria-live="polite">
        <span className="subscribe-success__icon" aria-hidden>✅</span>
        <p>{t('subscribe.success', { lga: selectedLgaNames || 'your LGA' })}</p>
        <p className="subscribe-success__ussd">{t('subscribe.ussd_hint')}</p>
        <button className="btn btn--ghost" onClick={() => setSuccess(false)}>
          Subscribe another number
        </button>
      </div>
    )
  }

  return (
    <div className="subscribe-page">
      <h1 className="subscribe-page__title">{t('subscribe.title')}</h1>
      <p className="subscribe-page__ussd">
        No smartphone? <a href="tel:*384*3566*3%23" className="ussd-link">Dial *384*FLOOD#</a> on any phone.
      </p>

      <form className="subscribe-form" onSubmit={handleSubmit} noValidate>
        {/* Phone */}
        <div className="form-group">
          <label htmlFor="phone" className="form-label">
            {t('subscribe.phone_label')}
          </label>
          <input
            id="phone"
            type="tel"
            inputMode="tel"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="+234 8XX XXX XXXX"
            aria-describedby="phone-hint"
            aria-invalid={phone.length > 5 && !phoneValid}
            className={`form-input ${phone.length > 5 && !phoneValid ? 'form-input--error' : ''}`}
            required
          />
          <span id="phone-hint" className="form-hint">
            Enter your Nigerian number: 080XXXXXXXX or +2348XXXXXXXXX
          </span>
          {phone.length > 5 && !phoneValid && (
            <span className="form-error" role="alert">Invalid Nigerian number format</span>
          )}
        </div>

        {/* Language */}
        <div className="form-group">
          <label htmlFor="lang-select" className="form-label">
            {t('subscribe.language_label')}
          </label>
          <select
            id="lang-select"
            value={selectedLang}
            onChange={e => setSelectedLang(e.target.value as SupportedLang)}
            className="form-select"
          >
            {SUPPORTED_LANGUAGES.map(l => (
              <option key={l.code} value={l.code}>{l.nativeLabel}</option>
            ))}
          </select>
        </div>

        {/* LGA selection */}
        <fieldset className="form-group form-group--fieldset">
          <legend className="form-label">
            {t('subscribe.lga_label')} ({selectedLgas.length}/10 selected)
          </legend>
          <div className="lga-checkboxes">
            {LGA_OPTIONS.map(lga => (
              <label
                key={lga.id}
                className={`lga-checkbox ${selectedLgas.includes(lga.id) ? 'lga-checkbox--selected' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={selectedLgas.includes(lga.id)}
                  onChange={() => toggleLga(lga.id)}
                  disabled={!selectedLgas.includes(lga.id) && selectedLgas.length >= 10}
                />
                <span>{lga.name}</span>
                <small>{lga.state}</small>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Severity threshold */}
        <fieldset className="form-group form-group--fieldset">
          <legend className="form-label">{t('subscribe.threshold_label')}</legend>
          <div className="threshold-options">
            {SEVERITY_OPTIONS.map(opt => (
              <label
                key={opt.value}
                className={`threshold-option threshold-option--${opt.value.toLowerCase()} ${threshold === opt.value ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="threshold"
                  value={opt.value}
                  checked={threshold === opt.value}
                  onChange={() => setThreshold(opt.value)}
                />
                {t(opt.label)}
              </label>
            ))}
          </div>
        </fieldset>

        {error && (
          <div className="form-error-banner" role="alert">{error}</div>
        )}

        {!navigator.onLine && (
          <div className="form-offline-notice" role="note">
            You are offline. Your subscription will be sent when you reconnect.
          </div>
        )}

        <button
          type="submit"
          className="btn btn--primary btn--full"
          disabled={!canSubmit}
          aria-busy={submitting}
        >
          {submitting ? '…' : t('subscribe.submit')}
        </button>
      </form>
    </div>
  )
}
