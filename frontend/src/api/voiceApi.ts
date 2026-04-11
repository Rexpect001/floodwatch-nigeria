/**
 * Voice Pipeline API client
 * All calls require X-Officer-Id header (JWT in production)
 */
import type { VoiceSession } from '../types/voice'

const BASE = '/api/v1/voice'

function headers(officerId: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-Officer-Id': officerId,
  }
}

async function unwrap(res: Response) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

export const voiceApi = {
  createDraft: (alertId: string, sourceTextEn: string, officerId = '') =>
    fetch(`${BASE}/sessions`, {
      method: 'POST',
      headers: headers(officerId),
      body: JSON.stringify({ alert_id: alertId, source_text_en: sourceTextEn }),
    }).then(unwrap),

  generate: (sessionId: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/generate`, {
      method: 'POST',
      headers: headers(officerId),
    }).then(unwrap),

  getSession: (sessionId: string, officerId = ''): Promise<VoiceSession> =>
    fetch(`${BASE}/sessions/${sessionId}`, {
      headers: headers(officerId),
    }).then(unwrap),

  trackPlayback: (sessionId: string, lang: string, durationS: number, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/playback`, {
      method: 'POST',
      headers: headers(officerId),
      body: JSON.stringify({ lang, playback_duration_s: durationS }),
    }).then(unwrap),

  checkApproveEligibility: (sessionId: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/approve-check`, {
      headers: headers(officerId),
    }).then(unwrap),

  approve: (sessionId: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/approve`, {
      method: 'POST',
      headers: headers(officerId),
    }).then(unwrap),

  reject: (sessionId: string, reason: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/reject`, {
      method: 'POST',
      headers: headers(officerId),
      body: JSON.stringify({ reason }),
    }).then(unwrap),

  override: (sessionId: string, totpCode: string, justification: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/override`, {
      method: 'POST',
      headers: headers(officerId),
      body: JSON.stringify({ totp_code: totpCode, justification }),
    }).then(unwrap),

  getAuditLog: (sessionId: string, officerId = '') =>
    fetch(`${BASE}/sessions/${sessionId}/audit`, {
      headers: headers(officerId),
    }).then(unwrap),
}
