# HazardWatch Nigeria — Product Requirements Document

**Last updated:** 2026-04-23
**Status:** In development
**Live URLs:** Frontend → https://floodwatch-nigeria.vercel.app | API → https://floodwatch-api-is3d.onrender.com

---

## 1. Problem Statement

Nigeria is the most flood-affected country in West Africa. In 2024 alone: 5 million people affected, 1,000+ deaths, ₦100B in damage. The 2024 Alau Dam breach (230+ deaths, 600,000 displaced) and the Maiduguri cellular failure during peak flooding exposed two critical gaps:

1. **No reliable early warning reaches the last mile** — government alerts exist but don't reach rural and low-income communities in time, in their language, on the channels they use.
2. **No offline-capable system** — existing apps fail precisely when floods knock out cell towers.

---

## 2. Product Vision

A 3-tier, offline-first Progressive Web App delivering life-safety flood and climate alerts to all 774 Nigerian LGAs in 5 languages (English, Hausa, Yoruba, Igbo, Pidgin), with <2-minute latency from government alert issuance to end-user SMS delivery.

---

## 3. Target Users

| User | Context | Key Need |
|------|---------|----------|
| At-risk residents (774 LGAs) | Low-bandwidth, feature phones, rural | SMS + USSD alerts in local language |
| NEMA/SEMA officers | Emergency operations center | Push alerts, issue orders, dual-auth voice approval |
| NiMet/NIHSA data officers | Government agencies | Feed authoritative data into system |
| Community reporters (CBEWS) | Ground truth, field | Submit geo-tagged flood photos |
| Radio station operators | Broadcast | Receive audio alert files via FTP |

---

## 4. Data Architecture

### Source Tiers (automatic failover T1 → T2 → cache)

**Tier 1 — Authoritative Government (Primary)**
| Source | Data | Poll Interval |
|--------|------|--------------|
| NIHSA API | 273 hydrometric stations; AFO classifications for 302+ communities; 5-day QPF | 15 min |
| NiMet AWS | 54 synoptic + 6 RADAR stations; SCP data; heatwave >40°C threshold | 15 min |
| NEMA EOC | Verified disaster alerts, evacuation orders, shelter coords from SEMAs | Push + 5 min poll |

**Tier 2 — Global Validation**
| Source | Data | Constraint |
|--------|------|-----------|
| Google Flood Hub API | 7-day AI riverine forecasts; 20% inundation threshold | — |
| GloFAS (Copernicus) | Ensemble flood forecasting vs 2022/2024 baselines | — |
| OpenWeatherMap One Call 3.0 | Global coverage | 1,000 calls/day; hard stop at 900 |

**Tier 3 — Ground Truth**
- CBEWS: geo-tagged photo/video, AI flood-detection verification (GPT-4o, ≥75% confidence) before public display
- IoT Telemetry: NIHSA water-level sensor direct feeds
- Historical: 2024 flood data as severity benchmark

**Failover chain:**
1. T1 fails → T2
2. T2 fails → serve cached data (72h retention in Redis)
3. All stale → show `SERVICE_DEGRADED` banner with staleness timestamp
4. Network failure → PWA Service Worker serves offline cached maps (148 LGAs, 72h)

---

## 5. Alert System

### Severity Levels (NEMA Standard)

| Level | Trigger | Action | Channels |
|-------|---------|--------|---------|
| RED | Imminent danger (confirmed 2+ sources) | Evacuation order + shelter GPS | SMS + Push + IVR + WhatsApp |
| ORANGE | High risk, prepare | Secure property, check neighbors | SMS + Push + WhatsApp |
| YELLOW | Moderate, vigilance | Monitor every 3h | Push + In-App |
| GREEN | Low, awareness | Seasonal prep | In-App only |

**RED alert rules:**
- Requires 2+ independent source confirmations before dispatch
- Bypasses all rate limits
- Requires dual-officer approval (4-eyes) in voice pipeline
- Must carry NEMA/NIHSA identifiers

### Delivery Channels
- **SMS:** Africa's Talking (MTN/Airtel/Glo/9mobile primary), Twilio fallback
- **Push:** Firebase FCM/APNs
- **WhatsApp:** WhatsApp Business API
- **IVR / Voice Calls:** Africa's Talking Voice API
- **USSD:** `*384*FLOOD#` — works on any phone, no internet required
- **Community Radio:** FTP drop to station endpoints (WAV PCM 16-bit)

---

## 6. Features

### 6.1 Dashboard (PWA)
- Map-first layout — Leaflet map fills left column, info panels scroll right
- Auto-geolocation with Nigeria bounding-box guard (lat 4–14, lng 2.5–15); falls back to centroid [9.08, 8.68]
- Real-time active alerts panel (RED first)
- 48-hour weather forecast widget
- Offline mode indicator + data staleness timestamps

### 6.2 Flood Forecast
- 5-day riverine forecast per LGA (NIHSA + Google Flood Hub + GloFAS merged)
- AFO (Annual Flood Outlook) for 302+ NIHSA-classified communities
- Heatwave risk map (>40°C threshold; Sokoto 2024 = 44.8°C baseline)
- Sentinel-1 SAR overlays (where available)

### 6.3 Alerts & Subscriptions
- Browse active alerts filtered by severity / LGA / state
- Subscribe via phone number: choose language + LGA(s) + severity threshold
- View evacuation shelter GPS coordinates + capacity
- Report alert errors → NiMet/NEMA verification team

### 6.4 USSD Interface (`*384*FLOOD#`)
- Works on any phone, zero internet required
- Menu: Flood Risk | Weather Alert | Evacuation Help | Language Select
- Responses ≤160 chars (`CON` or `END`)

### 6.5 Community Reports (CBEWS)
- Submit geo-tagged photo + description
- AI verification pipeline: GPT-4o flood confidence ≥75% + geotag drift <2km
- Verified reports visible on public map within minutes

### 6.6 Voice Alert Pipeline (NEMA Officer Tool)
A human-in-the-loop 5-step governance workflow before any RED/ORANGE alert enters dispatch:

```
Step 1: Compose English alert draft (≤280 chars)
Step 2: AI batch translation → HA/YO/IG/PG (Claude API, atomic)
Step 3: Audio synthesis → Google Cloud TTS / Coqui / Phrase Bank (atomic)
Step 4: Officer review — must play >50% of each clip; RED = dual-auth (4-eyes)
Step 5: Dispatch → Redis Stream → AT Voice + Radio FTP + IVR
```

**Target latency:** Steps 1→3 <30s; Steps 4→5 <2 min total

**TTS tiers by language:**
| Language | Now | Q2 2026 |
|----------|-----|---------|
| English (NG) | en-NG Neural2 | — |
| Yoruba | yo-NG Chirp HD / Neural2 | Same |
| Hausa | ha-NG Standard → Coqui fallback | Coqui VITS fine-tuned |
| Igbo | Phrase Bank (50 phrases) | Google ig + disclaimer |
| Pidgin | en-NG Neural2 (0.85x speed) | — |

**Translation rules (Claude API):**
- Enforces native flood vocabulary (e.g. `ambaliya` HA, `iṣan omi` YO, `mmiri ịda` IG)
- Confidence threshold ≥0.85; below threshold → flags clip, blocks auto-TTS for that language
- Forbidden loanwords: "flood" / "evacuate" in HA/YO/IG

**Governance:**
- Playback gate: officer must play >50% of each clip before Approve is enabled
- RED dual-auth: 2 different officers must both play + approve
- Rejection requires reason ≥10 chars (stored permanently in audit log)
- Emergency override: DIRECTOR role + valid TOTP → 24h post-incident audit
- Audio SHA-256 checksum verified against S3 before dispatch

### 6.7 Offline Mode
- Service Worker caches 72h of data
- Offline flood risk maps for 148 high-risk LGAs
- Voice clip approvals cached in IndexedDB; sync on reconnect (server timestamp wins)
- Data Saver Mode: <50KB/session

### 6.8 Multilingual UI
- 5 languages: EN, HA, YO, IG, PG with full diacritic support
- All alert payloads carry all 5 language fields
- UI language persists per user

---

## 7. API Surface (summary)

Base URL: `https://api.floodwatch.ng/api/v1`

| Group | Key Endpoints |
|-------|--------------|
| Forecasts | `GET /forecasts/flood/{lga_id}`, `/forecasts/afo`, `/forecasts/weather/{lga_id}`, `/forecasts/heatwave` |
| Alerts | `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/subscribe`, `GET /alerts/shelters/{lga_id}` |
| Stations | `GET /stations/gauges`, `/stations/weather`, `/stations/dams` |
| Reports | `POST /reports`, `GET /reports` |
| USSD | `POST /ussd/callback` |
| Voice | `POST /voice/sessions`, `POST /voice/sessions/{id}/translate`, `POST /voice/sessions/{id}/synthesize`, `POST /voice/sessions/{id}/approve`, `POST /voice/sessions/{id}/dispatch` |
| Admin | `GET /admin/ingestion/status`, `/admin/alerts/pending-red`, `/admin/sms/delivery-stats` |

Auth: JWT Bearer (public read endpoints: no auth required)

---

## 8. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Page load (3G) | <3 seconds |
| Alert latency (issue → SMS) | <2 minutes |
| Voice pipeline latency (Steps 1→3) | <30 seconds |
| Uptime (July–September peak) | 99.9% |
| SMS delivery rate | ≥90% (Africa's Talking) |
| RED alert pending threshold | <5 minutes for 2nd-source confirmation |
| Offline cache duration | 72 hours |
| Audio loudness | -16 LUFS (IVR standard) |
| Audio max duration | 60 seconds |
| Translation confidence | ≥0.85 per language |
| CBEWS photo confidence | ≥75% (GPT-4o vision) |

---

## 9. Infrastructure

| Service | Platform | Notes |
|---------|---------|-------|
| Frontend PWA | Vercel | Vite/React, proxies `/api/*` to Render |
| API Gateway | Render (Docker) | FastAPI, 2 workers, starter plan |
| Ingestion Scheduler | Render (Worker) | APScheduler, 15-min polls |
| Alert Orchestrator | Render (Worker) | Redis pub/sub consumer |
| Alert Router | Render (Worker) | Redis Stream `alerts:voice:approved` |
| Database | Render PostgreSQL (PostGIS 15) | Free tier; upgrade to RDS Multi-AZ in prod |
| Cache / Streams | Render Redis 7 | 512MB allkeys-lru |
| Voice clips | AWS S3 Standard-IA | CloudFront CDN, 30-day lifecycle |
| TTS fallback | Coqui (self-hosted Docker) | Hausa VITS model |

**Production target:** AWS EKS af-south-1 (Lagos) + RDS Multi-AZ + ElastiCache

---

## 10. Open Items / Known Gaps

- [ ] NIHSA, NiMet, NEMA API keys not yet provisioned (placeholder URLs in `.env.example`)
- [ ] Coqui Hausa VITS model not yet fine-tuned (Q2 2026)
- [ ] WhatsApp Community Validator (Phase 2 — YELLOW/GREEN alerts) not yet built
- [ ] Sentinel-1 SAR WMS URL not configured (`REACT_APP_SAR_WMS_URL` empty)
- [ ] PostgreSQL on free Render tier (90-day expiry) — needs upgrade before July peak season
- [ ] Security checklist incomplete: OAuth 2.0 for NiMet, phone number hashing for CBEWS reports
- [ ] SMS load test (`10,000 concurrent, <5 min wall-clock`) not yet run
- [ ] Igbo Phrase Bank coverage: only 50 phrases (needs expansion before launch)
