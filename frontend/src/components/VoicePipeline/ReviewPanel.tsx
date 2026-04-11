/**
 * Governance review panel — Approve / Reject / Emergency Override.
 *
 * Approve button:
 *   - Disabled until officer has played >50% of every non-waived clip
 *   - Disabled if RED and same officer already gave first approval
 *   - Shows real-time eligibility reason when disabled
 *
 * Emergency Override:
 *   - Visible to DIRECTOR-role only (set via officer profile)
 *   - Requires justification text + TOTP code input
 *   - Red warning banner + irreversible action confirmation
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { VoiceSession } from '../../types/voice'

interface Props {
  session: VoiceSession
  officerId: string
  isRedAlert: boolean
  onApprove: () => Promise<void>
  onReject:  (reason: string) => Promise<void>
  onOverride: (totpCode: string, justification: string) => Promise<void>
}

export default function ReviewPanel({
  session, officerId, isRedAlert, onApprove, onReject, onOverride
}: Props) {
  const { t } = useTranslation()
  const [isApproving, setIsApproving]     = useState(false)
  const [showReject, setShowReject]       = useState(false)
  const [rejectReason, setRejectReason]   = useState('')
  const [showOverride, setShowOverride]   = useState(false)
  const [totpCode, setTotpCode]           = useState('')
  const [justification, setJustification] = useState('')
  const [overrideConfirmed, setOverrideConfirmed] = useState(false)

  const eligibility = session.approveEligibility
  const canApprove  = eligibility?.eligible ?? false
  const rejectReasonValid = rejectReason.trim().length >= 10

  const handleApprove = async () => {
    setIsApproving(true)
    try { await onApprove() }
    finally { setIsApproving(false) }
  }

  const handleReject = async () => {
    if (!rejectReasonValid) return
    await onReject(rejectReason)
    setShowReject(false)
    setRejectReason('')
  }

  const handleOverride = async () => {
    if (!overrideConfirmed || totpCode.length < 6 || justification.length < 20) return
    await onOverride(totpCode, justification)
    setShowOverride(false)
  }

  // Audit trail summary
  const primaryApproved  = session.primaryApproved
  const secondaryApproved = session.status === 'APPROVED'

  return (
    <div className="review-panel" role="region" aria-label={t('voice.review_panel_label')}>

      {/* ── Status summary ── */}
      <div className="review-panel__status">
        <h3 className="review-panel__title">{t('voice.review_title')}</h3>

        {/* Approval status pills for RED dual-auth */}
        {isRedAlert && (
          <div className="review-panel__dual-auth">
            <div className={`review-panel__auth-pill ${primaryApproved ? 'review-panel__auth-pill--done' : ''}`}>
              {t('voice.officer_1')}: {primaryApproved ? t('voice.approved') : t('voice.pending')}
            </div>
            <div className={`review-panel__auth-pill ${secondaryApproved ? 'review-panel__auth-pill--done' : ''}`}>
              {t('voice.officer_2')}: {secondaryApproved ? t('voice.approved') : t('voice.pending')}
            </div>
          </div>
        )}

        {/* Playback progress summary */}
        <div className="review-panel__playback-summary" aria-live="polite">
          {['en', 'ha', 'yo', 'ig', 'pg'].map(lang => {
            const clip = session.clips.find(c => c.lang === lang)
            if (!clip || clip.tts_disabled) return null
            return (
              <span
                key={lang}
                className={`review-panel__lang-dot ${clip.played_once ? 'review-panel__lang-dot--played' : ''}`}
                aria-label={`${lang.toUpperCase()}: ${clip.played_once ? t('voice.played') : t('voice.not_played')}`}
              >
                {lang.toUpperCase()} {clip.played_once ? '✓' : '○'}
              </span>
            )
          })}
        </div>

        {/* Eligibility message when disabled */}
        {!canApprove && eligibility?.reason && (
          <p className="review-panel__eligibility-msg" role="status" aria-live="polite">
            {eligibility.reason}
          </p>
        )}
      </div>

      {/* ── Primary actions ── */}
      <div className="review-panel__actions">
        {/* APPROVE */}
        <button
          className={`review-panel__approve-btn ${canApprove ? '' : 'review-panel__approve-btn--disabled'}`}
          onClick={handleApprove}
          disabled={!canApprove || isApproving}
          aria-disabled={!canApprove}
          aria-describedby="approve-eligibility"
        >
          {isApproving ? (
            <><span className="spinner" aria-hidden="true" /> {t('voice.approving')}</>
          ) : isRedAlert && !primaryApproved ? (
            t('voice.approve_first')
          ) : isRedAlert && primaryApproved ? (
            t('voice.approve_second')
          ) : (
            t('voice.approve_and_queue')
          )}
        </button>

        {/* REJECT */}
        <button
          className="review-panel__reject-btn"
          onClick={() => setShowReject(true)}
          disabled={isApproving}
        >
          {t('voice.reject')}
        </button>
      </div>

      {/* ── Reject Modal ── */}
      {showReject && (
        <div className="review-panel__modal" role="dialog" aria-modal="true" aria-label={t('voice.reject_dialog')}>
          <div className="review-panel__modal-content">
            <h4>{t('voice.reject_title')}</h4>
            <p className="review-panel__modal-hint">{t('voice.reject_reason_required')}</p>
            <textarea
              className="review-panel__reject-input"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              placeholder={t('voice.reject_placeholder')}
              rows={4}
              minLength={10}
              aria-label={t('voice.reject_reason_label')}
              aria-required="true"
            />
            <p className={`review-panel__char-count ${rejectReasonValid ? 'valid' : ''}`}>
              {rejectReason.trim().length}/10 {t('voice.chars_minimum')}
            </p>
            <div className="review-panel__modal-actions">
              <button
                onClick={handleReject}
                disabled={!rejectReasonValid}
                className="review-panel__reject-confirm-btn"
              >
                {t('voice.confirm_reject')}
              </button>
              <button onClick={() => setShowReject(false)} className="review-panel__cancel-btn">
                {t('voice.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Emergency Override (DIRECTOR only) ── */}
      {session.isDirectorRole && (
        <>
          <button
            className="review-panel__override-btn"
            onClick={() => setShowOverride(true)}
          >
            ⚡ {t('voice.dispatch_immediate')}
          </button>

          {showOverride && (
            <div className="review-panel__modal review-panel__modal--danger" role="dialog" aria-modal="true">
              <div className="review-panel__modal-content">
                <div className="review-panel__override-warning" role="alert">
                  🔴 {t('voice.override_warning')}
                </div>
                <p>{t('voice.override_audit_notice')}</p>

                <label className="review-panel__field">
                  {t('voice.override_justification')}
                  <textarea
                    value={justification}
                    onChange={e => setJustification(e.target.value)}
                    placeholder={t('voice.override_justification_placeholder')}
                    minLength={20}
                    rows={3}
                    aria-required="true"
                  />
                </label>

                <label className="review-panel__field">
                  {t('voice.totp_code')}
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={totpCode}
                    onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 8))}
                    placeholder="000000"
                    maxLength={8}
                    aria-required="true"
                  />
                </label>

                <label className="review-panel__checkbox">
                  <input
                    type="checkbox"
                    checked={overrideConfirmed}
                    onChange={e => setOverrideConfirmed(e.target.checked)}
                  />
                  {t('voice.override_confirm_check')}
                </label>

                <div className="review-panel__modal-actions">
                  <button
                    onClick={handleOverride}
                    disabled={!overrideConfirmed || totpCode.length < 6 || justification.length < 20}
                    className="review-panel__override-confirm-btn"
                  >
                    {t('voice.override_execute')}
                  </button>
                  <button onClick={() => setShowOverride(false)} className="review-panel__cancel-btn">
                    {t('voice.cancel')}
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Visual audit trail ── */}
      <details className="review-panel__audit-summary">
        <summary>{t('voice.view_audit_trail')}</summary>
        <dl className="review-panel__audit-list">
          {session.primaryApproved && (
            <>
              <dt>{t('voice.first_approval')}</dt>
              <dd>{session.primaryApproverId} — {session.primaryApprovedAt}</dd>
            </>
          )}
          {session.secondaryApproved && (
            <>
              <dt>{t('voice.second_approval')}</dt>
              <dd>{session.secondaryApproverId} — {session.secondaryApprovedAt}</dd>
            </>
          )}
        </dl>
      </details>
    </div>
  )
}
