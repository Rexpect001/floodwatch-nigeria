/**
 * Step 5: Dispatch Confirmation screen.
 * Shows: officer name, approval timestamps, per-language playback durations,
 * RabbitMQ message ID, and downstream dispatch targets.
 * Override flag prominently displayed with audit report due date.
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import type { VoiceSession } from '../../types/voice'

interface Props {
  session: VoiceSession
  isOverride: boolean
  onClose: () => void
}

const DISPATCH_TARGETS = [
  { icon: '📱', labelKey: 'voice.dispatch_at_voice' },       // Africa's Talking Voice
  { icon: '📻', labelKey: 'voice.dispatch_radio_ftp' },      // Radio station FTP drop
  { icon: '📞', labelKey: 'voice.dispatch_ivr' },            // IVR system update
]

const LANG_NAMES: Record<string, string> = {
  en: 'English', ha: 'Hausa', yo: 'Yoruba', ig: 'Igbo', pg: 'Pidgin'
}

export default function DispatchConfirmation({ session, isOverride, onClose }: Props) {
  const { t } = useTranslation()

  return (
    <div
      className="dispatch-confirmation"
      role="region"
      aria-label={t('voice.dispatch_confirmation_label')}
      aria-live="assertive"
    >
      {/* ── Success header ── */}
      <div className={`dispatch-confirmation__header ${isOverride ? 'dispatch-confirmation__header--override' : ''}`}>
        {isOverride ? (
          <>
            <span className="dispatch-confirmation__icon">⚡</span>
            <h2>{t('voice.override_dispatched_title')}</h2>
            <p className="dispatch-confirmation__override-notice" role="alert">
              {t('voice.override_dispatched_notice')}
            </p>
          </>
        ) : (
          <>
            <span className="dispatch-confirmation__icon">✅</span>
            <h2>{t('voice.dispatched_title')}</h2>
            <p>{t('voice.dispatched_subtitle')}</p>
          </>
        )}
      </div>

      {/* ── Message ID ── */}
      <div className="dispatch-confirmation__msg-id">
        <span className="label">{t('voice.rabbitmq_message_id')}</span>
        <code>{session.rabbitmqMessageId}</code>
      </div>

      {/* ── Downstream targets ── */}
      <ul className="dispatch-confirmation__targets" aria-label={t('voice.dispatch_targets')}>
        {DISPATCH_TARGETS.map(({ icon, labelKey }) => (
          <li key={labelKey} className="dispatch-confirmation__target">
            <span aria-hidden="true">{icon}</span>
            <span>{t(labelKey)}</span>
            <span className="dispatch-confirmation__target-status">
              {t('voice.queued')}
            </span>
          </li>
        ))}
      </ul>

      {/* ── Clip summary ── */}
      <table className="dispatch-confirmation__clips" aria-label={t('voice.clip_summary')}>
        <caption className="sr-only">{t('voice.clip_summary')}</caption>
        <thead>
          <tr>
            <th>{t('voice.language')}</th>
            <th>{t('voice.tts_engine')}</th>
            <th>{t('voice.duration')}</th>
            <th>{t('voice.playback_duration')}</th>
          </tr>
        </thead>
        <tbody>
          {session.clips.map(clip => (
            <tr key={clip.lang}>
              <td>{LANG_NAMES[clip.lang] ?? clip.lang.toUpperCase()}</td>
              <td>{clip.tts_engine ?? t('voice.disabled')}</td>
              <td>{clip.audio_duration_s ? `${clip.audio_duration_s.toFixed(1)}s` : '—'}</td>
              <td>{clip.playback_duration_s ? `${clip.playback_duration_s.toFixed(1)}s` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ── Approval audit trail ── */}
      <dl className="dispatch-confirmation__audit" aria-label={t('voice.approval_audit')}>
        {session.primaryApproverId && (
          <>
            <dt>{t('voice.first_approval')}</dt>
            <dd>{session.primaryApproverId} — {session.primaryApprovedAt}</dd>
          </>
        )}
        {session.secondaryApproverId && (
          <>
            <dt>{t('voice.second_approval')}</dt>
            <dd>{session.secondaryApproverId} — {session.secondaryApprovedAt}</dd>
          </>
        )}
        {isOverride && session.overrideAuditReportDue && (
          <>
            <dt className="dispatch-confirmation__audit-warning">
              {t('voice.audit_report_due')}
            </dt>
            <dd className="dispatch-confirmation__audit-warning">
              {session.overrideAuditReportDue}
            </dd>
          </>
        )}
      </dl>

      <button className="dispatch-confirmation__close-btn" onClick={onClose}>
        {t('voice.close')}
      </button>
    </div>
  )
}
