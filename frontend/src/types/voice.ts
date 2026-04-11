export type PipelineStep =
  | 'source_composition'
  | 'ai_translation'
  | 'audio_synthesis'
  | 'officer_review'
  | 'queued_dispatch'

export type VoiceSessionStatus =
  | 'DRAFT'
  | 'TRANSLATING'
  | 'SYNTHESISING'
  | 'PENDING_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'QUEUED'
  | 'DISPATCHED'
  | 'FAILED'

export interface VoiceClip {
  lang: string
  script_text: string
  translation_confidence: number
  flagged: boolean
  forbidden_words_found: string[]
  audio_url: string | null
  waveform_data: number[]
  audio_duration_s: number
  tts_engine: string | null
  disclaimer: string | null
  played_once: boolean
  playback_duration_s: number
  waived: boolean
  tts_disabled: boolean
  synthesis_error: string | null
}

export interface ApproveEligibility {
  eligible: boolean
  reason: string
  missing_langs: string[]
  is_red_alert: boolean
  needs_second_approver: boolean
}

export interface VoiceSession {
  id: string
  status: VoiceSessionStatus
  sourceTextEn: string
  alertSeverity?: string
  clips: VoiceClip[]
  approveEligibility?: ApproveEligibility
  primaryApproved?: boolean
  secondaryApproved?: boolean
  primaryApproverId?: string
  primaryApprovedAt?: string
  secondaryApproverId?: string
  secondaryApprovedAt?: string
  isOverride?: boolean
  isDirectorRole?: boolean
  rabbitmqMessageId?: string
  overrideAuditReportDue?: string
}
