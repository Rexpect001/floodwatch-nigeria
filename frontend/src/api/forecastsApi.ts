import { apiClient } from './client'
import type { SupportedLang } from '../i18n'

export interface ForecastPoint {
  date: string
  severity: string
  probability_pct: number
  inundation_pct: number | null
  discharge_m3s: number | null
  baseline_2024_m3s: number | null
  source: string
  severity_label: string
  last_updated: string
  data_source_label: string
}

export interface FloodForecast {
  lga_id: number
  lga_name: string
  state_name: string
  flood_risk_class: string
  forecast: ForecastPoint[]
  data_staleness_hours: number | null
  is_cached: boolean
}

export interface AfoCommunity {
  id: number
  name: string
  afo_class: 'HIGHLY_PROBABLE' | 'PROBABLE' | 'LOW_RISK'
  afo_label: string
  lga: string
  state: string
  state_code: string
  lat: number
  lng: number
}

export interface AfoResponse {
  total: number
  source: string
  window: string
  data_source_label: string
  communities: AfoCommunity[]
}

export const forecastsApi = {
  getFlood: (lgaId: number, params: { days?: number; lang?: SupportedLang } = {}): Promise<FloodForecast> =>
    apiClient.get<FloodForecast>(`/forecasts/flood/${lgaId}`, { params }).then(r => r.data),

  getAfo: (params: { lang?: SupportedLang; state_code?: string } = {}): Promise<AfoResponse> =>
    apiClient.get<AfoResponse>('/forecasts/afo', { params }).then(r => r.data),
}
