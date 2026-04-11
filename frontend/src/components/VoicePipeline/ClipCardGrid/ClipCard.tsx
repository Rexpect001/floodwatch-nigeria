/**
 * Individual language clip card.
 *
 * Features:
 *  - Language badge (EN/HA/YO/IG/PG) + confidence score
 *  - Canvas waveform visualization (Web Audio API analyser)
 *  - Seekable HTML5 <audio> with custom skin (MM:SS display)
 *  - Collapsible script accordion (3 lines collapsed, full expanded)
 *  - "Copy Script" button (clipboard API) — radio station export
 *  - Disclaimer banner for Igbo phrase-bank / degraded quality TTS
 *  - IndexedDB audio cache for offline playback during review
 */
import React, { useRef, useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import WaveformCanvas from './WaveformCanvas'
import type { VoiceClip } from '../../../types/voice'

interface Props {
  clip: VoiceClip | null
  lang: string
  onPlaybackUpdate?: (lang: string, durationS: number) => void
}

const LANG_LABELS: Record<string, string> = {
  en: 'EN', ha: 'HA', yo: 'YO', ig: 'IG', pg: 'PG'
}

const CONFIDENCE_COLOR = (score: number) =>
  score >= 0.85 ? '#388E3C' : score >= 0.60 ? '#F57C00' : '#D32F2F'

export default function ClipCard({ clip, lang, onPlaybackUpdate }: Props) {
  const { t } = useTranslation()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [scriptExpanded, setScriptExpanded] = useState(false)
  const [copySuccess, setCopySuccess] = useState(false)
  const [audioBlob, setAudioBlob] = useState<string | null>(null)

  // Cache audio in IndexedDB for offline review (spec requirement)
  useEffect(() => {
    if (!clip?.audio_url) return
    cacheAudio(clip.audio_url, lang).then(url => setAudioBlob(url))
  }, [clip?.audio_url, lang])

  const handleTimeUpdate = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    setCurrentTime(audio.currentTime)
    onPlaybackUpdate?.(lang, audio.currentTime)
  }, [lang, onPlaybackUpdate])

  const handleLoadedMetadata = useCallback(() => {
    if (audioRef.current) setDuration(audioRef.current.duration)
  }, [])

  const handlePlayPause = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (isPlaying) { audio.pause() } else { audio.play() }
    setIsPlaying(!isPlaying)
  }, [isPlaying])

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = Number(e.target.value)
    setCurrentTime(audio.currentTime)
  }, [])

  const handleWaveformClick = useCallback((pct: number) => {
    const audio = audioRef.current
    if (!audio || !duration) return
    audio.currentTime = pct * duration
  }, [duration])

  const handleCopyScript = useCallback(async () => {
    if (!clip?.script_text) return
    await navigator.clipboard.writeText(clip.script_text)
    setCopySuccess(true)
    setTimeout(() => setCopySuccess(false), 2000)
  }, [clip?.script_text])

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  const playedPct = duration > 0 ? (currentTime / duration) * 100 : 0
  const hasPlayedThreshold = playedPct >= 50   // >50% triggers governance unlock

  if (!clip) {
    return (
      <div className="clip-card clip-card--empty" aria-label={`${LANG_LABELS[lang]} — ${t('voice.clip_not_generated')}`}>
        <span className="clip-card__lang-badge clip-card__lang-badge--empty">{LANG_LABELS[lang]}</span>
        <p className="clip-card__empty-message">{t('voice.clip_not_generated')}</p>
      </div>
    )
  }

  return (
    <article
      className={`clip-card ${clip.played_once ? 'clip-card--reviewed' : ''} ${clip.flagged ? 'clip-card--flagged' : ''}`}
      aria-label={`${t('voice.clip_label')} ${LANG_LABELS[lang]}`}
    >
      {/* ── Header: Language badge + confidence ── */}
      <header className="clip-card__header">
        <span
          className="clip-card__lang-badge"
          aria-label={`${t('voice.language')}: ${LANG_LABELS[lang]}`}
        >
          {LANG_LABELS[lang]}
        </span>

        {clip.translation_confidence !== undefined && (
          <span
            className="clip-card__confidence"
            style={{ color: CONFIDENCE_COLOR(clip.translation_confidence) }}
            title={t('voice.confidence_score')}
            aria-label={`${t('voice.confidence_score')}: ${Math.round(clip.translation_confidence * 100)}%`}
          >
            {Math.round(clip.translation_confidence * 100)}%
          </span>
        )}

        {clip.flagged && (
          <span className="clip-card__flag-badge" role="alert" aria-label={t('voice.flagged_for_review')}>
            ⚠ {t('voice.manual_review')}
          </span>
        )}

        {clip.played_once && (
          <span className="clip-card__reviewed-badge" aria-label={t('voice.clip_reviewed')}>
            ✓ {t('voice.reviewed')}
          </span>
        )}
      </header>

      {/* ── Disclaimer (Igbo/degraded TTS) ── */}
      {clip.disclaimer && (
        <div className="clip-card__disclaimer" role="note" aria-label={t('voice.tts_disclaimer')}>
          ℹ {clip.disclaimer}
        </div>
      )}

      {/* ── Waveform Canvas ── */}
      {clip.waveform_data && clip.waveform_data.length > 0 && (
        <WaveformCanvas
          waveformData={clip.waveform_data}
          playPosition={currentTime / (duration || 1)}
          onClick={handleWaveformClick}
          height={56}
          aria-label={t('voice.waveform_label')}
        />
      )}

      {/* ── Audio Player ── */}
      {(audioBlob || clip.audio_url) && (
        <div className="clip-card__player" role="region" aria-label={t('voice.audio_player')}>
          {/* Hidden native audio element */}
          <audio
            ref={audioRef}
            src={audioBlob || clip.audio_url!}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onEnded={() => setIsPlaying(false)}
            aria-label={`${t('voice.audio_for')} ${LANG_LABELS[lang]}`}
          />

          {/* Play/Pause */}
          <button
            className={`clip-card__play-btn ${isPlaying ? 'clip-card__play-btn--playing' : ''}`}
            onClick={handlePlayPause}
            aria-label={isPlaying ? t('voice.pause') : t('voice.play')}
          >
            {isPlaying ? '⏸' : '▶'}
          </button>

          {/* Seekable timeline */}
          <div className="clip-card__timeline">
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              className="clip-card__seek"
              aria-label={t('voice.seek')}
              aria-valuetext={`${formatTime(currentTime)} / ${formatTime(duration)}`}
            />
            {/* Progress bar visual overlay */}
            <div
              className="clip-card__progress-fill"
              style={{ width: `${playedPct}%` }}
              aria-hidden="true"
            />
          </div>

          {/* Time display */}
          <span className="clip-card__time" aria-live="off">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>

          {/* Playback threshold indicator */}
          <span
            className={`clip-card__threshold ${hasPlayedThreshold ? 'clip-card__threshold--met' : ''}`}
            aria-label={hasPlayedThreshold
              ? t('voice.threshold_met')
              : t('voice.threshold_unmet', { pct: Math.round(playedPct) })}
          >
            {hasPlayedThreshold ? '✓ 50%+' : `${Math.round(playedPct)}% / 50%`}
          </span>
        </div>
      )}

      {/* ── Script Accordion ── */}
      <div className="clip-card__script">
        <div
          className={`clip-card__script-text ${scriptExpanded ? '' : 'clip-card__script-text--collapsed'}`}
          lang={lang === 'pg' ? 'en' : lang}   // correct lang attr for screen readers
        >
          {clip.script_text}
        </div>
        <div className="clip-card__script-actions">
          <button
            className="clip-card__expand-btn"
            onClick={() => setScriptExpanded(v => !v)}
            aria-expanded={scriptExpanded}
            aria-label={scriptExpanded ? t('voice.collapse_script') : t('voice.expand_script')}
          >
            {scriptExpanded ? t('voice.show_less') : t('voice.show_more')}
          </button>

          {/* Copy Script — radio station export */}
          <button
            className={`clip-card__copy-btn ${copySuccess ? 'clip-card__copy-btn--success' : ''}`}
            onClick={handleCopyScript}
            aria-label={t('voice.copy_script')}
            title={t('voice.copy_for_radio')}
          >
            {copySuccess ? `✓ ${t('voice.copied')}` : t('voice.copy_script')}
          </button>
        </div>
      </div>

      {/* ── Forbidden word warnings ── */}
      {clip.forbidden_words_found && clip.forbidden_words_found.length > 0 && (
        <div className="clip-card__forbidden-words" role="alert">
          ⚠ {t('voice.forbidden_words')}: {clip.forbidden_words_found.join(', ')}
        </div>
      )}
    </article>
  )
}

// ── IndexedDB audio cache (offline resilience) ────────────────

const DB_NAME  = 'voice-audio-cache'
const DB_STORE = 'clips'

async function cacheAudio(url: string, lang: string): Promise<string> {
  try {
    const db = await openCache()
    const existing = await getFromCache(db, url)
    if (existing) return existing

    const resp = await fetch(url)
    const blob = await resp.blob()
    const objectUrl = URL.createObjectURL(blob)
    await saveToCache(db, url, objectUrl)
    return objectUrl
  } catch {
    return url   // fallback to direct URL if IndexedDB unavailable
  }
}

function openCache(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(DB_STORE)
    req.onsuccess = () => resolve(req.result)
    req.onerror   = () => reject(req.error)
  })
}

function getFromCache(db: IDBDatabase, key: string): Promise<string | null> {
  return new Promise(resolve => {
    const tx  = db.transaction(DB_STORE, 'readonly')
    const req = tx.objectStore(DB_STORE).get(key)
    req.onsuccess = () => resolve(req.result ?? null)
    req.onerror   = () => resolve(null)
  })
}

function saveToCache(db: IDBDatabase, key: string, value: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction(DB_STORE, 'readwrite')
    const req = tx.objectStore(DB_STORE).put(value, key)
    req.onsuccess = () => resolve()
    req.onerror   = () => reject(req.error)
  })
}
