/**
 * SiteFooter — comprehensive page footer (brand · emergency contact ·
 * services · data sources), styled after institutional agency sites.
 */
import { Link } from 'react-router-dom'
import { AlertTriangle, Phone } from 'lucide-react'

const SERVICES = [
  { to: '/',          label: 'Dashboard'       },
  { to: '/map',       label: 'Live Hazard Map' },
  { to: '/forecast',  label: 'Flood Forecast'  },
  { to: '/alerts',    label: 'Active Alerts'   },
  { to: '/shelters',  label: 'Find a Shelter'  },
  { to: '/subscribe', label: 'SMS Alerts'      },
  { to: '/report',    label: 'Report a Hazard' },
]

const SOURCES = [
  'NEMA — National Emergency Management Agency',
  'NIHSA — Nigeria Hydrological Services Agency',
  'NiMet — Nigerian Meteorological Agency',
  'ACLED — Conflict & security incident data',
]

export default function SiteFooter() {
  return (
    <footer className="site-footer" aria-label="Site information">
      <div className="site-footer__grid">
        <div className="site-footer__brand">
          <div className="site-footer__brand-row">
            <span className="site-footer__logo" aria-hidden>
              <AlertTriangle size={15} strokeWidth={2.5} />
            </span>
            <span className="site-footer__name">HazardWatch Nigeria</span>
          </div>
          <p className="site-footer__tagline">
            Official multi-hazard early warning for floods, heatwaves, drought,
            landslides and security incidents — covering all 774 Local
            Government Areas.
          </p>
        </div>

        <div className="site-footer__col">
          <h3 className="site-footer__heading">Emergency Contact</h3>
          <a href="tel:08000636261" className="site-footer__contact">
            <Phone size={13} aria-hidden /> 0800-063-6261 (NEMA)
          </a>
          <a href="tel:112" className="site-footer__contact">
            <Phone size={13} aria-hidden /> 112 — National Emergency
          </a>
          <span className="site-footer__contact site-footer__contact--ussd">
            No internet? Dial *384*FLOOD# on any phone
          </span>
        </div>

        <nav className="site-footer__col" aria-label="Services">
          <h3 className="site-footer__heading">Services</h3>
          <ul className="site-footer__links">
            {SERVICES.map(s => (
              <li key={s.to}><Link to={s.to}>{s.label}</Link></li>
            ))}
          </ul>
        </nav>

        <div className="site-footer__col">
          <h3 className="site-footer__heading">Data Sources</h3>
          <ul className="site-footer__sources">
            {SOURCES.map(s => <li key={s}>{s}</li>)}
          </ul>
        </div>
      </div>

      <div className="site-footer__bottom">
        © {new Date().getFullYear()} HazardWatch Nigeria · NEMA · NIHSA · NiMet
      </div>
    </footer>
  )
}
