/**
 * Responsive clip card grid.
 * 1 col mobile (320px), 2 col tablet (768px), 3+ col desktop (1200px+)
 * Shows all 5 language variants simultaneously during review.
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import ClipCard from './ClipCard'
import type { VoiceClip } from '../../../types/voice'

interface Props {
  clips: VoiceClip[]
  langs: string[]
  isLoading: boolean
  onPlaybackUpdate?: (lang: string, durationS: number) => void
}

const LANG_ORDER = ['en', 'ha', 'yo', 'ig', 'pg']

export default function ClipCardGrid({ clips, langs, isLoading, onPlaybackUpdate }: Props) {
  const { t } = useTranslation()
  const orderedLangs = LANG_ORDER.filter(l => langs.includes(l))
  const clipsByLang = Object.fromEntries(clips.map(c => [c.lang, c]))

  return (
    <section
      className="clip-card-grid"
      aria-label={t('voice.clip_grid_label')}
    >
      <h3 className="clip-card-grid__title">{t('voice.clip_grid_title')}</h3>

      <div className="clip-card-grid__grid">
        {orderedLangs.map(lang => (
          isLoading ? (
            <div key={lang} className="clip-card-grid__skeleton" aria-busy="true">
              <div className="skeleton-lang-badge" />
              <div className="skeleton-waveform" />
              <div className="skeleton-text" />
            </div>
          ) : (
            <ClipCard
              key={lang}
              clip={clipsByLang[lang] ?? null}
              lang={lang}
              onPlaybackUpdate={onPlaybackUpdate}
            />
          )
        ))}
      </div>
    </section>
  )
}
