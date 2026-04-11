/**
 * Left-panel step tracker — locked sequence wizard.
 * Steps unlock only after predecessor completes.
 * Visual states: completed (✓), active (●), locked (○)
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import type { PipelineStep } from '../../types/voice'

interface Props {
  steps: PipelineStep[]
  activeStep: PipelineStep
  completedSteps: PipelineStep[]
  isRedAlert: boolean
  primaryApproved?: boolean
}

const STEP_META: Record<PipelineStep, { labelKey: string; icon: string; saveable?: boolean }> = {
  source_composition: { labelKey: 'voice.step.source',    icon: '✏️',  saveable: true },
  ai_translation:     { labelKey: 'voice.step.translate',  icon: '🌐' },
  audio_synthesis:    { labelKey: 'voice.step.audio',      icon: '🎙️' },
  officer_review:     { labelKey: 'voice.step.review',     icon: '👮' },
  queued_dispatch:    { labelKey: 'voice.step.dispatch',   icon: '📡' },
}

export default function StepTracker({
  steps, activeStep, completedSteps, isRedAlert, primaryApproved
}: Props) {
  const { t } = useTranslation()

  return (
    <nav className="step-tracker" aria-label={t('voice.steps_label')}>
      <h2 className="step-tracker__title">{t('voice.pipeline_title')}</h2>

      <ol className="step-tracker__list" role="list">
        {steps.map((step, idx) => {
          const meta = STEP_META[step]
          const isActive    = step === activeStep
          const isCompleted = completedSteps.includes(step)
          const isLocked    = !isActive && !isCompleted

          let stateClass = 'step-tracker__item--locked'
          if (isCompleted) stateClass = 'step-tracker__item--completed'
          if (isActive)    stateClass = 'step-tracker__item--active'

          return (
            <li
              key={step}
              className={`step-tracker__item ${stateClass}`}
              aria-current={isActive ? 'step' : undefined}
            >
              <span className="step-tracker__number" aria-hidden="true">
                {isCompleted ? '✓' : isActive ? '●' : '○'}
              </span>

              <div className="step-tracker__content">
                <span className="step-tracker__icon" aria-hidden="true">
                  {meta.icon}
                </span>
                <span className="step-tracker__label">
                  {t(meta.labelKey)}
                </span>

                {/* Step 1: Save Draft badge */}
                {meta.saveable && (isActive || isCompleted) && (
                  <span className="step-tracker__badge step-tracker__badge--save">
                    {t('voice.save_draft_available')}
                  </span>
                )}

                {/* Step 4: Dual-auth indicator for RED */}
                {step === 'officer_review' && isRedAlert && (
                  <span className="step-tracker__badge step-tracker__badge--dual-auth">
                    {primaryApproved
                      ? t('voice.second_approval_needed')
                      : t('voice.dual_auth_required')}
                  </span>
                )}

                {/* Locked badge */}
                {isLocked && (
                  <span className="step-tracker__badge step-tracker__badge--locked" aria-label={t('voice.step_locked')}>
                    🔒
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ol>

      {/* RED alert dual-auth progress */}
      {isRedAlert && (
        <div className="step-tracker__red-auth" role="status" aria-live="polite">
          <div className="step-tracker__auth-dot" data-approved={primaryApproved ? 'true' : 'false'}>
            {t('voice.officer_1')}
          </div>
          <div className="step-tracker__auth-connector" aria-hidden="true">→</div>
          <div className="step-tracker__auth-dot" data-approved="false">
            {t('voice.officer_2')}
          </div>
        </div>
      )}
    </nav>
  )
}
