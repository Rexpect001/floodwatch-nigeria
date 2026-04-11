/**
 * Canvas-based waveform visualization using 200-point amplitude array.
 * Renders static waveform with playback position overlay.
 * Click-to-seek: passes normalized (0-1) position to parent.
 */
import React, { useRef, useEffect, useCallback } from 'react'

interface Props {
  waveformData: number[]    // 200 normalized amplitude values (0-1)
  playPosition: number      // 0-1 current position
  onClick: (pct: number) => void
  height?: number
  'aria-label'?: string
}

const PLAYED_COLOR   = '#1565C0'   // dark blue — played portion
const UNPLAYED_COLOR = '#90CAF9'   // light blue — unplayed
const BAR_GAP        = 2
const MIN_BAR_HEIGHT = 3

export default function WaveformCanvas({
  waveformData, playPosition, onClick, height = 56, 'aria-label': ariaLabel
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || !waveformData.length) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { width } = canvas
    const barCount = waveformData.length
    const barWidth = Math.max(1, (width - barCount * BAR_GAP) / barCount)
    const playedX = playPosition * width

    ctx.clearRect(0, 0, width, height)

    waveformData.forEach((amplitude, i) => {
      const x = i * (barWidth + BAR_GAP)
      const barH = Math.max(MIN_BAR_HEIGHT, amplitude * (height - 8))
      const y = (height - barH) / 2

      ctx.fillStyle = x <= playedX ? PLAYED_COLOR : UNPLAYED_COLOR
      ctx.beginPath()
      ctx.roundRect(x, y, barWidth, barH, 2)
      ctx.fill()
    })
  }, [waveformData, playPosition, height])

  useEffect(() => {
    draw()
  }, [draw])

  // Resize observer for responsive canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ro = new ResizeObserver(() => {
      canvas.width = canvas.offsetWidth
      draw()
    })
    ro.observe(canvas)
    return () => ro.disconnect()
  }, [draw])

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    onClick(Math.max(0, Math.min(1, pct)))
  }, [onClick])

  return (
    <canvas
      ref={canvasRef}
      className="waveform-canvas"
      height={height}
      onClick={handleClick}
      role="img"
      aria-label={ariaLabel ?? 'Audio waveform'}
      style={{ width: '100%', cursor: 'pointer', display: 'block' }}
    />
  )
}
