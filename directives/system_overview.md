# Nigeria Climate Early Warning System — System Overview

## Purpose
A 3-tier, offline-first Progressive Web App delivering life-safety flood and climate alerts
to all 774 Nigerian LGAs in 5 languages (EN, HA, YO, IG, PG), with <2-minute latency
from government alert issuance to end-user SMS delivery.

---

## Data Source Tiers

### Tier 1 — Authoritative Government (Primary)
| Source | Data | Poll Interval | Key Notes |
|--------|------|--------------|-----------|
| NIHSA API | 273 hydrometric stations; AFO classifications for 302+ communities; 5-day QPF | 15 min | Cross-ref Laggo Dam (Cameroon) release notifications |
| NiMet AWS | 54 synoptic + 6 RADAR stations; SCP data (74% accuracy 2024 baseline); heatwave >40°C | 15 min | WAT (UTC+1) timestamps |
| NEMA EOC | Verified disaster alerts, evacuation orders, shelter coords from SEMAs | On push + 5 min poll | RED alerts bypass rate limits |

### Tier 2 — Global Validation
| Source | Data | Rate Limit |
|--------|------|-----------|
| Google Flood Hub API | 7-day AI riverine forecasts; 20% area inundation threshold | — |
| GloFAS (Copernicus) | Ensemble flood forecasting; compare vs 2022/2024 baselines | — |
| OpenWeatherMap One Call 3.0 | Global coverage, NiMet aggregation | 1,000 calls/day; 10-30 min cache |

### Tier 3 — Ground Truth
- CBEWS: Geo-tagged photo/video with AI flood-detection verification before public display
- IoT Telemetry: NIHSA water-level sensor direct feeds where available
- Historical: 2024 flood data (5M affected, 1,000+ deaths, ₦100B damage) as severity benchmark

---

## Alert Severity Levels (NEMA Standard)

| Level | Trigger | Action | Channels |
|-------|---------|--------|---------|
| RED | Imminent danger (confirmed 2+ sources) | Evacuation order + shelter GPS | SMS + Push + IVR + WhatsApp |
| ORANGE | High risk, prepare | Secure property, check neighbors | SMS + Push + WhatsApp |
| YELLOW | Moderate, vigilance | Monitor every 3h | Push + In-App |
| GREEN | Low, awareness | Seasonal prep | In-App only |

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA SOURCES (Tier 1/2/3)                                      │
│  NIHSA ─── NiMet ─── NEMA ─── GoogleFloodHub ─── GloFAS ─── OWM │
└────────────────────┬────────────────────────────────────────────┘
                     │ 15-min polls + push webhooks
┌────────────────────▼────────────────────────────────────────────┐
│  INGESTION SERVICE (Python/FastAPI microservice)                 │
│  • Exponential backoff on API failure                            │
│  • Tier failover: T1 → T2 → cached data                         │
│  • Cross-reference RED alerts (2+ source confirmation)           │
│  • Writes raw + processed data to PostgreSQL/PostGIS             │
│  • Publishes to Redis pub/sub for real-time alert routing        │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  ALERT ORCHESTRATION SERVICE                                     │
│  • Severity classifier (RED/ORANGE/YELLOW/GREEN)                 │
│  • Deduplication + rate-limit guard                              │
│  • Multilingual payload builder (5 languages)                    │
│  • Priority queue: RED bypasses all rate limits                  │
└──────┬──────────────┬───────────────┬──────────────┬────────────┘
       │              │               │              │
  SMS Gateway    Push Notif.    WhatsApp Biz    IVR Service
  Africa's Talking  FCM/APNs     Business API   (voice synthesis)
  (MTN/Airtel/Glo/9mobile)
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  API GATEWAY (FastAPI)                                           │
│  • REST endpoints for PWA frontend                              │
│  • USSD handler (*384*FLOOD#)                                    │
│  • Community radio feed endpoints                               │
│  • SEMA integration API                                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  PWA FRONTEND (React/TypeScript)                                 │
│  • Service Worker: 72h offline cache                             │
│  • Offline flood risk maps for 148 high-risk LGAs               │
│  • 5-language UI with diacritic support                          │
│  • Data Saver Mode: <50KB/session                                │
│  • Sentinel-1 SAR overlays + evacuation routing                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Constraints
- **Offline-First**: Assume network failure during major floods (2024 Maiduguri precedent)
- **No speculative narratives**: Lake Chad = ~24,500 km² (current stable), deforestation = 3.67%/yr FAO
- **Institutional credibility**: All life-safety alerts carry NEMA/NIHSA identifiers
- **Performance**: <3s load on 3G; 99.9% uptime July-September peak season

---

## Reference Events
- 2024 Alau Dam breach: 230+ deaths, 600,000 displaced — integrated into dam-breach model
- 2024 Maiduguri: cellular failure precedent for offline-first requirement
- 2024 Sokoto heatwave: 44.8°C verified record — heatwave threshold baseline
- 2024 aggregate: 5M affected, 1,000+ deaths, ₦100B damage — severity classification benchmark
