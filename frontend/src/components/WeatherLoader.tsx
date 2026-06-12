/**
 * WeatherLoader — animated cloud/sun/rain mark used as the loading
 * state across the app. Mirrors the pre-hydration splash in index.html.
 */

interface Props {
  label?: string
  size?: number
}

export default function WeatherLoader({ label = 'Loading…', size = 96 }: Props) {
  return (
    <div className="weather-loader" role="status" aria-live="polite">
      <svg
        width={size}
        height={Math.round(size * 0.96)}
        viewBox="0 0 110 106"
        fill="none"
        aria-hidden
      >
        <g className="loader-sun" stroke="#B47910" strokeWidth="2.4" strokeLinecap="round">
          <circle cx="82" cy="24" r="8.5" fill="#FFF7E6" />
          <line x1="82" y1="7"  x2="82" y2="11" />
          <line x1="82" y1="37" x2="82" y2="41" />
          <line x1="65" y1="24" x2="69" y2="24" />
          <line x1="95" y1="24" x2="99" y2="24" />
          <line x1="70" y1="12" x2="73" y2="15" />
          <line x1="91" y1="33" x2="94" y2="36" />
          <line x1="94" y1="12" x2="91" y2="15" />
          <line x1="73" y1="33" x2="70" y2="36" />
        </g>
        <path
          d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"
          transform="translate(8 10) scale(3.6)"
          fill="#FFFFFF" stroke="#205493" strokeWidth="0.62"
          strokeLinecap="round" strokeLinejoin="round"
        />
        <g stroke="#2A6CB8" strokeWidth="3" strokeLinecap="round">
          <line className="loader-drop loader-drop--1" x1="36" y1="88" x2="36" y2="95" />
          <line className="loader-drop loader-drop--2" x1="54" y1="88" x2="54" y2="95" />
          <line className="loader-drop loader-drop--3" x1="72" y1="88" x2="72" y2="95" />
        </g>
      </svg>
      <span className="weather-loader__label">{label}</span>
    </div>
  )
}
