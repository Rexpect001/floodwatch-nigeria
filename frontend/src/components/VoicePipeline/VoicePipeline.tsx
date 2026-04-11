/**
 * Voice Alert Production & Governance Pipeline
 * Full-page wizard component. Left panel: step tracker. Right panel: clip cards.
 *
 * Steps:
 *  1. Source Composition  — English drafting (Save Draft available)
 *  2. AI Translation      — Claude API batch (atomic, no save)
 *  3. Audio Synthesis     — TTS generation (atomic)
 *  4. Officer Review      — play >50% each clip → Approve / Reject
 *  5. Queue for Dispatch  — handoff to Alert Router
 */
import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import StepTracker from './StepTracker'
import SourceComposer from './SourceComposer'
import ClipCardGrid from './ClipCardGrid/ClipCardGrid'
import ReviewPanel from './ReviewPanel'
import DispatchConfirmation from './DispatchConfirmation'
import { voiceApi } from '../../api/voiceApi'
import type { VoiceSession, PipelineStep } from '../../types/voice'

interface Props {
  alertId: string
  alertSeverity: 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN'
  officerId: string
  onClose: () => void
}

const STEP_SEQUENCE: PipelineStep[] = [
  'source_composition',
  'ai_translation',
  'audio_synthesis',
  'officer_review',
  'queued_dispatch',
]

export default function VoicePipeline({ alertId, alertSeverity, officerId, onClose }: Props) {
  const { t } = useTranslation()
  const [activeStep, setActiveStep] = useState<PipelineStep>('source_composition')
  const [session, setSession] = useState<VoiceSession | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [generateProgress, setGenerateProgress] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  // Poll session status while PENDING_REVIEW (after officer approves first RED approval)
  useEffect(() => {
    if (!session?.id || session.status !== 'PENDING_REVIEW') return
    const interval = setInterval(async () => {
      const updated = await voiceApi.getSession(session.id)
      setSession(updated)
    }, 5000)
    return () => clearInterval(interval)
  }, [session?.id, session?.status])

  // ── Step 1 handlers ───────────────────────────────────────

  const handleSaveDraft = useCallback(async (sourceText: string) => {
    try {
      setError(null)
      const { session_id } = await voiceApi.createDraft(alertId, sourceText)
      setSession({ id: session_id, status: 'DRAFT', sourceTextEn: sourceText, clips: [] })
    } catch (e: any) {
      setError(e.message)
    }
  }, [alertId])

  // ── Steps 2+3: Generate ───────────────────────────────────

  const handleGenerate = useCallback(async () => {
    if (!session?.id) return
    setIsGenerating(true)
    setError(null)

    try {
      // Step 2 progress feedback
      setGenerateProgress(t('voice.progress.translating'))
      setActiveStep('ai_translation')

      const result = await voiceApi.generate(session.id)

      // Steps 2+3 complete — move to synthesis step briefly for UX, then review
      setGenerateProgress(t('voice.progress.synthesising'))
      setActiveStep('audio_synthesis')
      await new Promise(r => setTimeout(r, 600))   // brief visual hold

      setSession(prev => prev ? { ...prev, ...result, status: 'PENDING_REVIEW' } : prev)
      setActiveStep('officer_review')
    } catch (e: any) {
      setError(e.message)
      setActiveStep('source_composition')
    } finally {
      setIsGenerating(false)
      setGenerateProgress('')
    }
  }, [session?.id, t])

  // ── Step 4: Review ────────────────────────────────────────

  const handlePlaybackUpdate = useCallback(async (lang: string, durationS: number) => {
    if (!session?.id) return
    const result = await voiceApi.trackPlayback(session.id, lang, durationS)
    setSession(prev => {
      if (!prev) return prev
      const clips = prev.clips.map(c =>
        c.lang === lang ? { ...c, played_once: result.played_once } : c
      )
      return { ...prev, clips, approveEligibility: result }
    })
  }, [session?.id])

  const handleApprove = useCallback(async () => {
    if (!session?.id) return
    setError(null)
    try {
      const result = await voiceApi.approve(session.id)
      if (result.queued) {
        setSession(prev => prev ? { ...prev, status: 'QUEUED', rabbitmqMessageId: result.rabbitmq_message_id } : prev)
        setActiveStep('queued_dispatch')
      } else if (result.awaiting_second) {
        // RED: first approval done, waiting for second officer
        setSession(prev => prev ? { ...prev, primaryApproved: true } : prev)
      }
    } catch (e: any) {
      setError(e.message)
    }
  }, [session?.id])

  const handleReject = useCallback(async (reason: string) => {
    if (!session?.id) return
    setError(null)
    try {
      await voiceApi.reject(session.id, reason)
      setSession(prev => prev ? { ...prev, status: 'REJECTED' } : prev)
      setActiveStep('source_composition')   // back to editing
    } catch (e: any) {
      setError(e.message)
    }
  }, [session?.id])

  const handleOverride = useCallback(async (totpCode: string, justification: string) => {
    if (!session?.id) return
    setError(null)
    try {
      const result = await voiceApi.override(session.id, totpCode, justification)
      setSession(prev => prev ? { ...prev, status: 'QUEUED', isOverride: true } : prev)
      setActiveStep('queued_dispatch')
    } catch (e: any) {
      setError(e.message)
    }
  }, [session?.id])

  // ── Render ────────────────────────────────────────────────

  const currentStepIndex = STEP_SEQUENCE.indexOf(activeStep)
  const isRedAlert = alertSeverity === 'RED'

  return (
    <div className="voice-pipeline" role="main" aria-label={t('voice.pipeline_title')}>
      {/* ── Error Banner ── */}
      {error && (
        <div className="voice-pipeline__error" role="alert">
          <span>⚠ {error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* ── Generation Progress Banner ── */}
      {isGenerating && (
        <div className="voice-pipeline__progress" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          {generateProgress}
        </div>
      )}

      {/* ── RED Alert Dual-Auth Banner ── */}
      {isRedAlert && (
        <div className="voice-pipeline__dual-auth-notice" role="status">
          🔴 {t('voice.red_dual_auth_notice')}
        </div>
      )}

      <div className="voice-pipeline__layout">
        {/* ── LEFT PANEL: Step Tracker ── */}
        <aside className="voice-pipeline__left" aria-label={t('voice.steps_label')}>
          <StepTracker
            steps={STEP_SEQUENCE}
            activeStep={activeStep}
            completedSteps={STEP_SEQUENCE.slice(0, currentStepIndex)}
            isRedAlert={isRedAlert}
            primaryApproved={session?.primaryApproved}
          />
        </aside>

        {/* ── RIGHT PANEL: Step Content ── */}
        <main className="voice-pipeline__right">
          {/* Step 1: Source Composition */}
          {activeStep === 'source_composition' && (
            <SourceComposer
              initialText={session?.sourceTextEn ?? ''}
              alertSeverity={alertSeverity}
              onSaveDraft={handleSaveDraft}
              onGenerate={handleGenerate}
              isGenerating={isGenerating}
              hasDraft={!!session?.id && session.status === 'DRAFT'}
            />
          )}

          {/* Steps 2+3 in progress — show skeleton clip grid */}
          {(activeStep === 'ai_translation' || activeStep === 'audio_synthesis') && (
            <ClipCardGrid clips={[]} isLoading langs={['en', 'ha', 'yo', 'ig', 'pg']} />
          )}

          {/* Step 4: Officer Review */}
          {activeStep === 'officer_review' && session && (
            <>
              <ClipCardGrid
                clips={session.clips}
                isLoading={false}
                langs={['en', 'ha', 'yo', 'ig', 'pg']}
                onPlaybackUpdate={handlePlaybackUpdate}
              />
              <ReviewPanel
                session={session}
                officerId={officerId}
                isRedAlert={isRedAlert}
                onApprove={handleApprove}
                onReject={handleReject}
                onOverride={handleOverride}
              />
            </>
          )}

          {/* Step 5: Dispatch Confirmation */}
          {activeStep === 'queued_dispatch' && session && (
            <DispatchConfirmation
              session={session}
              isOverride={session.isOverride ?? false}
              onClose={onClose}
            />
          )}
        </main>
      </div>
    </div>
  )
}
