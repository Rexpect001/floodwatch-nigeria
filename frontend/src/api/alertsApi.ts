import { apiClient } from './client'
import type { SupportedLang } from '../i18n'

export interface Alert {
  id: string
  alert_type: string
  severity: 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN'
  severity_color: string
  title: string
  body: string
  sms_text: string | null
  affected_lga_count: number
  nema_alert_id: string | null
  nihsa_alert_id: string | null
  confirmed_by: string[]
  shelter_coords: object[] | null
  evacuation_routes: object | null
  valid_from: string
  valid_until: string | null
  last_updated: string
  data_source_label: string
}

export interface Shelter {
  name: string
  capacity: number | null
  address: string | null
  lat: number
  lng: number
}

export interface SubscribeRequest {
  msisdn: string
  lang: SupportedLang
  lga_ids: number[]
  severity_threshold: 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN'
}

export const alertsApi = {
  list: (params: {
    lang?: SupportedLang
    severity?: string
    lga_id?: number
    state_id?: number
  } = {}): Promise<Alert[]> =>
    apiClient.get<Alert[]>('/alerts', { params }).then(r => r.data),

  get: (id: string, lang: SupportedLang = 'en'): Promise<Alert> =>
    apiClient.get<Alert>(`/alerts/${id}`, { params: { lang } }).then(r => r.data),

  getShelters: (lgaId: number): Promise<{ lga_id: number; shelters: Shelter[] }> =>
    apiClient.get(`/alerts/shelters/${lgaId}`).then(r => r.data),

  subscribe: (req: SubscribeRequest): Promise<{ status: string; msisdn: string }> =>
    apiClient.post('/alerts/subscribe', req).then(r => r.data),

  reportError: (report: {
    alert_id?: string
    lga_id?: number
    description: string
    reporter_contact?: string
  }): Promise<{ status: string; message: string }> =>
    apiClient.post('/alerts/report-error', report).then(r => r.data),
}
