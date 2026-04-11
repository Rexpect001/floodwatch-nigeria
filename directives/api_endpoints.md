# API Endpoint Specification

Base URL: `https://api.floodwatch.ng/api/v1`
Auth: JWT Bearer token (public read endpoints: no auth required)
Format: JSON; UTF-8; WAT timestamps as `DD/MM/YYYY HH:MM WAT`

---

## Forecasts

### `GET /forecasts/flood/{lga_id}`
5-day riverine flood forecast. Merges NIHSA (T1) + Google Flood Hub + GloFAS.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 5 | 1–7 |
| `lang` | str | `en` | `en\|ha\|yo\|ig\|pg` |

**Response:**
```json
{
  "lga_id": 123,
  "lga_name": "Lokoja",
  "state_name": "Kogi",
  "flood_risk_class": "HIGH",
  "forecast": [
    {
      "date": "2025-09-01",
      "severity": "HIGHLY_PROBABLE",
      "probability_pct": 82.5,
      "inundation_pct": 34.1,
      "discharge_m3s": 18450.0,
      "baseline_2024_m3s": 16200.0,
      "source": "NIHSA",
      "severity_label": "Highly Probable",
      "last_updated": "01/09/2025 06:00 WAT",
      "data_source_label": "Data: NIHSA"
    }
  ],
  "is_cached": false
}
```

### `GET /forecasts/flood/community/{community_id}`
Same as above but for a specific community (AFO classification level).

### `GET /forecasts/afo`
Annual Flood Outlook — all 302+ NIHSA-classified communities.

| Param | Type | Notes |
|-------|------|-------|
| `lang` | str | |
| `state_code` | str | Filter by 2-char state code |

### `GET /forecasts/weather/{lga_id}`
48-hour weather forecast (NiMet primary, OWM supplement).

### `GET /forecasts/heatwave`
Active heatwave risk areas. Threshold: >40°C. Reference: Sokoto 2024 = 44.8°C.

| Param | Type | Notes |
|-------|------|-------|
| `state_code` | str | Optional filter |

---

## Alerts

### `GET /alerts`
Active alerts ordered by severity (RED first).

| Param | Type | Notes |
|-------|------|-------|
| `lang` | str | Response language |
| `severity` | str | Filter: RED\|ORANGE\|YELLOW\|GREEN |
| `lga_id` | int | Filter by LGA |
| `state_id` | int | Filter by state |

**Response includes:**
- `confirmed_by`: array of sources (RED requires 2+)
- `nema_alert_id` / `nihsa_alert_id`: official identifiers
- `shelter_coords`: GPS coordinates + capacity
- `data_source_label`: "Data: NEMA/NIHSA (Official)" vs "Data: OpenWeatherMap (Global)"
- `last_updated`: "DD/MM/YYYY HH:MM WAT"

### `GET /alerts/{alert_id}`
Full alert detail including all 5-language fields.

### `POST /alerts/subscribe`
Register phone number for SMS alerts.

```json
{
  "msisdn": "+2348012345678",
  "lang": "yo",
  "lga_ids": [123, 456],
  "severity_threshold": "ORANGE"
}
```

### `GET /alerts/shelters/{lga_id}`
Evacuation shelter GPS coords from active RED/ORANGE alerts + NEMA EOC.

### `POST /alerts/report-error`
In-app error report → NiMet/NEMA verification team.

```json
{
  "alert_id": "uuid",
  "lga_id": 123,
  "description": "No flooding visible in this area",
  "reporter_contact": "optional"
}
```

---

## Stations

### `GET /stations/gauges`
List hydrometric stations (273). Filter: `?state_id=&active=true`

### `GET /stations/gauges/{station_id}/readings`
Time-series river gauge readings.

| Param | Type | Notes |
|-------|------|-------|
| `hours` | int | Default 24, max 168 (7 days) |

**Response includes:** water_level_m, discharge_m3s, stage_trend, bankfull comparison

### `GET /stations/weather`
List NiMet weather stations (54 synoptic + 6 RADAR).

### `GET /stations/dams`
Dam registry with Laggo Dam (Cameroon) included. Downstream LGA risk mapping.

---

## Community Reports (CBEWS)

### `POST /reports`
Submit geo-tagged flood report with photo.

```json
{
  "lat": 7.733,
  "lng": 6.741,
  "report_type": "FLOOD_ACTIVE",
  "description": "Water level rising on main road",
  "photo_url": "https://..."
}
```
Auto-routes to `cbews_verifier.py` AI pipeline. Public visibility requires:
- Photo flood confidence ≥ 75% (GPT-4o vision)
- Geotag drift < 2km

### `GET /reports`
Public verified community reports (geojson format).

| Param | Type | Notes |
|-------|------|-------|
| `lga_id` | int | |
| `hours` | int | Default 24 |
| `verified_only` | bool | Default true |

---

## USSD

### `POST /ussd/callback`
Africa's Talking USSD callback handler.
USSD code: `*384*FLOOD#`
- `1` = Flood Risk (enter LGA code)
- `2` = Weather Alert
- `3` = Evacuation Help
- `4` = Language Select

Response: `CON ...` (continue) or `END ...` (terminal, ≤160 chars)

---

## Admin (JWT required)

### `GET /admin/ingestion/status`
Data freshness per source. Shows: last_success, consecutive_failures, current_tier, is_degraded.

### `GET /admin/alerts/pending-red`
RED alerts awaiting 2nd-source confirmation.

### `GET /admin/sms/delivery-stats`
SMS delivery rates by carrier and language.

### `POST /admin/alerts` (NEMA/SEMA integration)
Create official alert with NEMA identifier. Bypasses AI classifier.

---

## Error Responses

```json
{
  "error": "string",
  "code": "RESOURCE_NOT_FOUND | RATE_LIMITED | DATA_STALE | SERVICE_DEGRADED",
  "data_staleness_hours": 2.5,
  "fallback_tier": 2,
  "timestamp": "DD/MM/YYYY HH:MM WAT"
}
```

`SERVICE_DEGRADED` returned when all Tier 1 sources are unavailable; Tier 2 cached data served with staleness timestamp displayed to user.

---

## Rate Limits

| Endpoint | Limit | Notes |
|----------|-------|-------|
| Public read | 100 req/min/IP | |
| POST /reports | 10 req/hour/IP | Flood report |
| POST /alerts/subscribe | 5 req/hour/IP | |
| Admin | 1,000 req/min | JWT required |
| OWM upstream | 1,000/day | Enforced server-side; stops at 900 (10% buffer) |
