/**
 * Step 1: Source Composition
 * English alert drafting with 280-char limit and real-time character counter.
 * "Save Draft" available at this step only.
 * "Generate" triggers Steps 2+3 atomically.
 */
import React, { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  initialText: string
  alertSeverity: 'RED' | 'ORANGE' | 'YELLOW' | 'GREEN'
  onSaveDraft: (text: string) => Promise<void>
  onGenerate:  () => Promise<void>
  isGenerating: boolean
  hasDraft: boolean
}

const MAX_CHARS = 280
const WARN_THRESHOLD = 240   // yellow warning at 240+

const SEVERITY_GUIDANCE: Record<string, string> = {
  RED:    'voice.compose_guidance_red',
  ORANGE: 'voice.compose_guidance_orange',
  YELLOW: 'voice.compose_guidance_yellow',
  GREEN:  'voice.compose_guidance_green',
}

// Forbidden loanwords that will be blocked in HA/YO/IG translations
const ENGLISH_LOANWORD_HINTS = ['flood', 'evacuate', 'emergency']

export default function SourceComposer({
  initialText, alertSeverity, onSaveDraft, onGenerate, isGenerating, hasDraft
}: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState(initialText)
  const [isSaving, setIsSaving] = useState(false)
  const [savedAt, setSavedAt]   = useState<string | null>(null)

  const charCount = text.length
  const charsLeft = MAX_CHARS - charCount
  const isOverLimit = charCount > MAX_CHARS
  const isWarn      = charCount >= WARN_THRESHOLD && !isOverLimit

  // Hint about loanwords that will need translation
  const foundLoanwords = ENGLISH_LOANWORD_HINTS.filter(w =>
    text.toLowerCase().includes(w)
  )

  const handleSaveDraft = useCallback(async () => {
    if (isOverLimit || !text.trim()) return
    setIsSaving(true)
    try {
      await onSaveDraft(text)
      setSavedAt(new Date().toLocaleTimeString())
    } finally {
      setIsSaving(false)
    }
  }, [text, isOverLimit, onSaveDraft])

  const handleGenerate = useCallback(async () => {
    if (isOverLimit || !text.trim() || isGenerating) return
    if (!hasDraft) await onSaveDraft(text)
    await onGenerate()
  }, [text, isOverLimit, isGenerating, hasDraft, onSaveDraft, onGenerate])

  return (
    <section className="source-composer" aria-label={t('voice.step.source')}>
      <h2 className="source-composer__title">
        {t('voice.compose_title')}
      </h2>

      {/* Severity-specific guidance */}
      <div
        className={`source-composer__guidance source-composer__guidance--${alertSeverity.toLowerCase()}`}
        role="note"
      >
        {t(SEVERITY_GUIDANCE[alertSeverity])}
      </div>

      {/* Writing tips */}
      <ul className="source-composer__tips" aria-label={t('voice.writing_tips')}>
        <li>{t('voice.tip_action_first')}</li>
        <li>{t('voice.tip_location')}</li>
        <li>{t('voice.tip_shelter')}</li>
        <li>{t('voice.tip_contact')}</li>
      </ul>

      {/* Main textarea */}
      <div className="source-composer__textarea-wrap">
        <textarea
          className={`source-composer__textarea ${isOverLimit ? 'source-composer__textarea--error' : ''}`}
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={t('voice.compose_placeholder')}
          rows={6}
          maxLength={MAX_CHARS + 20}   // allow slight over for UX; validate on submit
          lang="en"
          aria-label={t('voice.source_text_label')}
          aria-describedby="char-counter loanword-hint"
        />

        {/* Character counter */}
        <div
          id="char-counter"
          className={`source-composer__counter ${isWarn ? 'warn' : ''} ${isOverLimit ? 'error' : ''}`}
          aria-live="polite"
          aria-atomic="true"
        >
          {isOverLimit
            ? t('voice.over_limit', { over: Math.abs(charsLeft) })
            : t('voice.chars_remaining', { count: charsLeft })}
        </div>
      </div>

      {/* Loanword hint */}
      {foundLoanwords.length > 0 && (
        <div id="loanword-hint" className="source-composer__loanword-hint" role="note">
          ℹ {t('voice.loanword_hint', { words: foundLoanwords.join(', ') })}
        </div>
      )}

      {/* Save confirmation */}
      {savedAt && (
        <p className="source-composer__saved-at" aria-live="polite">
          ✓ {t('voice.draft_saved_at', { time: savedAt })}
        </p>
      )}

      {/* Action buttons */}
      <div className="source-composer__actions">
        {/* Save Draft — Step 1 only */}
        <button
          className="source-composer__save-btn"
          onClick={handleSaveDraft}
          disabled={isSaving || isOverLimit || !text.trim()}
          aria-label={t('voice.save_draft')}
        >
          {isSaving ? t('voice.saving') : t('voice.save_draft')}
        </button>

        {/* Generate — triggers Steps 2+3 */}
        <button
          className={`source-composer__generate-btn source-composer__generate-btn--${alertSeverity.toLowerCase()}`}
          onClick={handleGenerate}
          disabled={isOverLimit || !text.trim() || isGenerating}
          aria-label={t('voice.generate_all_languages')}
        >
          {isGenerating ? (
            <><span className="spinner" aria-hidden="true" /> {t('voice.generating')}</>
          ) : (
            t('voice.generate_all_languages')
          )}
        </button>
      </div>

      {/* Generation time expectation */}
      <p className="source-composer__timing-hint">
        {t('voice.generation_timing')}   {/* "~15-30 seconds for 5 languages" */}
      </p>
    </section>
  )
}
