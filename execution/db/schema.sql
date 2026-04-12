-- ============================================================
-- Nigeria Climate Early Warning System — PostGIS Schema
-- PostgreSQL 15+ with PostGIS 3.x
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- fuzzy text search for LGA names

-- ============================================================
-- REFERENCE DATA
-- ============================================================

CREATE TABLE states (
    id          SERIAL PRIMARY KEY,
    code        CHAR(2) NOT NULL UNIQUE,               -- NG state codes
    name_en     VARCHAR(64) NOT NULL,
    name_ha     VARCHAR(64),
    name_yo     VARCHAR(64),
    name_ig     VARCHAR(64),
    geom        GEOMETRY(MULTIPOLYGON, 4326),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_states_geom ON states USING GIST(geom);

CREATE TABLE lgas (
    id              SERIAL PRIMARY KEY,
    state_id        INTEGER REFERENCES states(id),
    name_en         VARCHAR(128) NOT NULL,
    name_ha         VARCHAR(128),
    name_yo         VARCHAR(128),
    name_ig         VARCHAR(128),
    flood_risk_class VARCHAR(16) CHECK (flood_risk_class IN ('HIGH', 'MODERATE', 'LOW')),
    -- 148 HIGH, 72 flash-flood probable per AFO
    flash_flood_probable BOOLEAN DEFAULT FALSE,
    afo_community_count  INTEGER DEFAULT 0,   -- AFO classified communities within LGA
    geom            GEOMETRY(MULTIPOLYGON, 4326),
    centroid        GEOMETRY(POINT, 4326),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_lgas_geom     ON lgas USING GIST(geom);
CREATE INDEX idx_lgas_state    ON lgas(state_id);
CREATE INDEX idx_lgas_risk     ON lgas(flood_risk_class);

CREATE TABLE communities (
    id              SERIAL PRIMARY KEY,
    lga_id          INTEGER REFERENCES lgas(id),
    name_en         VARCHAR(128) NOT NULL,
    afo_class       VARCHAR(16) CHECK (afo_class IN ('HIGHLY_PROBABLE', 'PROBABLE', 'LOW_RISK')),
    geom            GEOMETRY(POINT, 4326),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_communities_geom ON communities USING GIST(geom);
CREATE INDEX idx_communities_lga  ON communities(lga_id);

-- ============================================================
-- MONITORING INFRASTRUCTURE
-- ============================================================

CREATE TABLE hydrometric_stations (
    id              SERIAL PRIMARY KEY,
    nihsa_station_id VARCHAR(32) UNIQUE NOT NULL,
    name            VARCHAR(128) NOT NULL,
    river_name      VARCHAR(128),
    state_id        INTEGER REFERENCES states(id),
    lga_id          INTEGER REFERENCES lgas(id),
    geom            GEOMETRY(POINT, 4326),
    elevation_m     NUMERIC(8,2),
    bankfull_m      NUMERIC(6,3),   -- bankfull discharge threshold (m)
    danger_level_m  NUMERIC(6,3),   -- danger level in metres
    is_active       BOOLEAN DEFAULT TRUE,
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_hydro_geom   ON hydrometric_stations USING GIST(geom);

CREATE TABLE weather_stations (
    id              SERIAL PRIMARY KEY,
    nimet_station_id VARCHAR(32) UNIQUE NOT NULL,
    name            VARCHAR(128) NOT NULL,
    station_type    VARCHAR(16) CHECK (station_type IN ('SYNOPTIC', 'RADAR', 'AWS')),
    state_id        INTEGER REFERENCES states(id),
    geom            GEOMETRY(POINT, 4326),
    elevation_m     NUMERIC(8,2),
    is_active       BOOLEAN DEFAULT TRUE,
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_weather_geom ON weather_stations USING GIST(geom);

CREATE TABLE dam_registry (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    country         CHAR(2) NOT NULL DEFAULT 'NG',   -- 'NG' or 'CM' (Cameroon - Laggo)
    operator        VARCHAR(128),
    capacity_mm3    NUMERIC(12,2),
    geom            GEOMETRY(POINT, 4326),
    downstream_lgas INTEGER[],                        -- array of lga.id at risk
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- REAL-TIME OBSERVATIONS
-- ============================================================

CREATE TABLE river_gauge_readings (
    id              BIGSERIAL PRIMARY KEY,
    station_id      INTEGER REFERENCES hydrometric_stations(id),
    observed_at     TIMESTAMPTZ NOT NULL,
    water_level_m   NUMERIC(6,3),
    discharge_m3s   NUMERIC(10,3),
    stage_trend     VARCHAR(8) CHECK (stage_trend IN ('RISING', 'FALLING', 'STEADY')),
    source_tier     SMALLINT DEFAULT 1,               -- 1=NIHSA, 2=IoT
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_gauge_station_time ON river_gauge_readings(station_id, observed_at DESC);
CREATE INDEX idx_gauge_time         ON river_gauge_readings(observed_at DESC);

CREATE TABLE weather_observations (
    id              BIGSERIAL PRIMARY KEY,
    station_id      INTEGER REFERENCES weather_stations(id),
    observed_at     TIMESTAMPTZ NOT NULL,
    temp_c          NUMERIC(5,2),
    humidity_pct    NUMERIC(5,2),
    wind_speed_kmh  NUMERIC(6,2),
    wind_dir_deg    SMALLINT,
    precip_mm_1h    NUMERIC(6,2),
    visibility_m    INTEGER,
    pressure_hpa    NUMERIC(7,2),
    is_heatwave     BOOLEAN GENERATED ALWAYS AS (temp_c > 40.0) STORED,
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_weather_obs_station ON weather_observations(station_id, observed_at DESC);
CREATE INDEX idx_weather_obs_heatwave ON weather_observations(observed_at DESC) WHERE is_heatwave = TRUE;

CREATE TABLE dam_release_events (
    id              BIGSERIAL PRIMARY KEY,
    dam_id          INTEGER REFERENCES dam_registry(id),
    reported_at     TIMESTAMPTZ NOT NULL,
    release_m3s     NUMERIC(12,2),
    source          VARCHAR(64),
    verified        BOOLEAN DEFAULT FALSE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- FORECASTS
-- ============================================================

CREATE TABLE flood_forecasts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(32) NOT NULL CHECK (source IN (
                        'NIHSA', 'GOOGLE_FLOOD_HUB', 'GLOFAS', 'OWM', 'DERIVED'
                    )),
    lga_id          INTEGER REFERENCES lgas(id),
    community_id    INTEGER REFERENCES communities(id),
    forecast_for    DATE NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    probability_pct NUMERIC(5,2) CHECK (probability_pct BETWEEN 0 AND 100),
    severity        VARCHAR(16) CHECK (severity IN ('HIGHLY_PROBABLE', 'PROBABLE', 'LOW_RISK', 'NONE')),
    afo_class       VARCHAR(16),                       -- NIHSA AFO classification
    inundation_pct  NUMERIC(5,2),                      -- % community area flooded (Flood Hub)
    discharge_m3s   NUMERIC(10,3),                     -- GloFAS/NIHSA discharge
    baseline_2024_m3s NUMERIC(10,3),                   -- reference: 2024 flood discharge
    geom            GEOMETRY(POLYGON, 4326),            -- predicted flood extent
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_forecast_lga_date  ON flood_forecasts(lga_id, forecast_for);
CREATE INDEX idx_forecast_date      ON flood_forecasts(forecast_for);
CREATE INDEX idx_forecast_severity  ON flood_forecasts(severity);
CREATE INDEX idx_forecast_geom      ON flood_forecasts USING GIST(geom);

CREATE TABLE precipitation_forecasts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(32) NOT NULL,
    lga_id          INTEGER REFERENCES lgas(id),
    forecast_for    TIMESTAMPTZ NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    precip_mm       NUMERIC(7,2),
    precip_prob_pct NUMERIC(5,2),
    wind_speed_kmh  NUMERIC(6,2),
    temp_max_c      NUMERIC(5,2),
    temp_min_c      NUMERIC(5,2),
    is_heatwave_risk BOOLEAN GENERATED ALWAYS AS (temp_max_c > 40.0) STORED,
    confidence_pct  NUMERIC(5,2),
    raw_payload     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_precip_lga_time ON precipitation_forecasts(lga_id, forecast_for);

-- ============================================================
-- ALERTS
-- ============================================================

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type      VARCHAR(32) NOT NULL CHECK (alert_type IN (
                        -- Flood hazards
                        'FLOOD_RIVERINE', 'FLOOD_FLASH', 'FLOOD_COASTAL',
                        -- Heat / atmospheric
                        'HEATWAVE', 'THUNDERSTORM', 'DUST_HARMATTAN', 'WINDSTORM',
                        -- Geological / land
                        'LANDSLIDE', 'EARTHQUAKE', 'EROSION',
                        -- Fire / drought
                        'WILDFIRE', 'DROUGHT',
                        -- Infrastructure
                        'DAM_RELEASE',
                        -- Health / bio (climate-linked)
                        'DISEASE_OUTBREAK',
                        -- Security / public safety
                        'BANDITRY', 'INSURGENCY', 'COMMUNAL_CONFLICT',
                        'CIVIL_UNREST', 'KIDNAPPING_HOTSPOT', 'TERRORISM',
                        -- Civil / response
                        'EVACUATION', 'ALL_CLEAR'
                    )),
    severity        VARCHAR(8) NOT NULL CHECK (severity IN ('RED', 'ORANGE', 'YELLOW', 'GREEN')),
    status          VARCHAR(16) DEFAULT 'ACTIVE' CHECK (status IN (
                        'DRAFT', 'ACTIVE', 'SUPERSEDED', 'CANCELLED', 'EXPIRED'
                    )),

    -- Geographic scope
    state_ids       INTEGER[],
    lga_ids         INTEGER[],
    community_ids   INTEGER[],
    affected_geom   GEOMETRY(MULTIPOLYGON, 4326),

    -- Content (multilingual)
    title_en        TEXT NOT NULL,
    title_ha        TEXT,
    title_yo        TEXT,
    title_ig        TEXT,
    title_pg        TEXT,
    body_en         TEXT NOT NULL,
    body_ha         TEXT,
    body_yo         TEXT,
    body_ig         TEXT,
    body_pg         TEXT,
    sms_en          VARCHAR(160),                      -- GSM 7-bit optimised
    sms_ha          VARCHAR(160),
    sms_yo          VARCHAR(160),
    sms_ig          VARCHAR(160),
    sms_pg          VARCHAR(160),

    -- Verification (RED requires 2+ sources)
    source_primary   VARCHAR(32),
    source_secondary VARCHAR(32),
    confirmed_by     VARCHAR(32)[],                    -- e.g. ['NIHSA', 'GOOGLE_FLOOD_HUB']
    nema_alert_id    VARCHAR(64),                      -- official NEMA identifier
    nihsa_alert_id   VARCHAR(64),

    -- Shelter/evacuation data
    shelter_coords   JSONB,                            -- [{name, lat, lng, capacity}]
    evacuation_routes JSONB,

    -- Lifecycle
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ,
    issued_by       VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_alerts_severity   ON alerts(severity, status);
CREATE INDEX idx_alerts_lgas       ON alerts USING GIN(lga_ids);
CREATE INDEX idx_alerts_geom       ON alerts USING GIST(affected_geom);
CREATE INDEX idx_alerts_valid      ON alerts(valid_from, valid_until);

CREATE TABLE alert_deliveries (
    id              BIGSERIAL PRIMARY KEY,
    alert_id        UUID REFERENCES alerts(id),
    channel         VARCHAR(16) CHECK (channel IN ('SMS', 'PUSH', 'WHATSAPP', 'IVR', 'EMAIL')),
    language        CHAR(2) CHECK (language IN ('en', 'ha', 'yo', 'ig', 'pg')),
    recipient_msisdn VARCHAR(16),
    recipient_token  TEXT,
    status          VARCHAR(16) DEFAULT 'QUEUED' CHECK (status IN (
                        'QUEUED', 'SENT', 'DELIVERED', 'FAILED', 'UNDELIVERABLE'
                    )),
    gateway_ref     VARCHAR(128),
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_delivery_alert   ON alert_deliveries(alert_id);
CREATE INDEX idx_delivery_status  ON alert_deliveries(status, created_at DESC);

-- ============================================================
-- COMMUNITY REPORTS (CBEWS Ground Truth)
-- ============================================================

CREATE TABLE community_reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_hash   VARCHAR(64),                       -- hashed phone (privacy)
    lga_id          INTEGER REFERENCES lgas(id),
    geom            GEOMETRY(POINT, 4326),
    report_type     VARCHAR(32),
    description     TEXT,
    photo_url       TEXT,
    photo_verified  BOOLEAN DEFAULT FALSE,             -- AI flood-detection result
    photo_confidence NUMERIC(5,4),
    geotag_verified BOOLEAN DEFAULT FALSE,
    is_false_report BOOLEAN DEFAULT FALSE,
    public_visible  BOOLEAN DEFAULT FALSE,
    verified_by     VARCHAR(64),
    verified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_reports_geom   ON community_reports USING GIST(geom);
CREATE INDEX idx_reports_public ON community_reports(public_visible, created_at DESC);

-- ============================================================
-- SECURITY INCIDENTS (ACLED + DSS + Community)
-- ============================================================

CREATE TABLE security_incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    acled_event_id  BIGINT UNIQUE,                        -- ACLED data_id (dedup key)
    event_type      VARCHAR(32) NOT NULL CHECK (event_type IN (
                        'BANDITRY', 'INSURGENCY', 'COMMUNAL_CONFLICT',
                        'CIVIL_UNREST', 'KIDNAPPING_HOTSPOT', 'TERRORISM',
                        'ARMED_CLASH', 'PROTEST', 'RIOT', 'OTHER'
                    )),
    -- ACLED raw fields
    event_date      DATE NOT NULL,
    actor1          VARCHAR(256),                         -- Perpetrator name
    actor2          VARCHAR(256),
    inter1          SMALLINT,                             -- ACLED interaction code
    fatalities      INTEGER DEFAULT 0,
    source          VARCHAR(256),                         -- e.g. "ACLED", "DSS", "COMMUNITY"
    source_scale    VARCHAR(32),                          -- "National", "Subnational"
    notes           TEXT,

    -- Geography
    state_id        INTEGER REFERENCES states(id),
    lga_id          INTEGER REFERENCES lgas(id),
    geom            GEOMETRY(POINT, 4326),
    location_name   VARCHAR(256),

    -- Alert linkage
    alert_id        UUID REFERENCES alerts(id),           -- generated alert if severity RED/ORANGE
    severity        VARCHAR(8) CHECK (severity IN ('RED', 'ORANGE', 'YELLOW', 'GREEN')),
    verified        BOOLEAN DEFAULT FALSE,
    public_visible  BOOLEAN DEFAULT TRUE,

    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_security_geom     ON security_incidents USING GIST(geom);
CREATE INDEX idx_security_lga      ON security_incidents(lga_id, event_date DESC);
CREATE INDEX idx_security_type     ON security_incidents(event_type, severity);
CREATE INDEX idx_security_date     ON security_incidents(event_date DESC);

-- ============================================================
-- SUBSCRIPTIONS (SMS + Push + WhatsApp)
-- ============================================================

CREATE TABLE sms_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    msisdn          VARCHAR(16) NOT NULL UNIQUE,          -- +234XXXXXXXXXX
    lang            CHAR(2) NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),
    lga_ids         INTEGER[] NOT NULL,                   -- max 10 LGAs
    severity_threshold VARCHAR(8) DEFAULT 'ORANGE' CHECK (severity_threshold IN ('RED', 'ORANGE', 'YELLOW', 'GREEN')),
    -- Hazard category preferences (null = all)
    alert_types     VARCHAR(32)[],                        -- null = receive all types
    -- Security alerts opt-in (explicit consent required)
    security_alerts BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    subscribed_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sms_sub_lgas     ON sms_subscriptions USING GIN(lga_ids);
CREATE INDEX idx_sms_sub_active   ON sms_subscriptions(is_active, severity_threshold);

CREATE TABLE push_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    fcm_token       TEXT NOT NULL UNIQUE,                 -- Firebase Cloud Messaging token
    lang            CHAR(2) NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),
    lga_ids         INTEGER[] NOT NULL,
    severity_threshold VARCHAR(8) DEFAULT 'ORANGE',
    security_alerts BOOLEAN DEFAULT FALSE,
    platform        VARCHAR(16) CHECK (platform IN ('web', 'android', 'ios')),
    is_active       BOOLEAN DEFAULT TRUE,
    last_seen       TIMESTAMPTZ DEFAULT NOW(),
    subscribed_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_push_sub_lgas    ON push_subscriptions USING GIN(lga_ids);
CREATE INDEX idx_push_sub_active  ON push_subscriptions(is_active);

CREATE TABLE whatsapp_subscriptions (
    id              BIGSERIAL PRIMARY KEY,
    wa_id           VARCHAR(20) NOT NULL UNIQUE,          -- WhatsApp number (without +)
    lang            CHAR(2) NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),
    lga_ids         INTEGER[] NOT NULL,
    severity_threshold VARCHAR(8) DEFAULT 'ORANGE',
    security_alerts BOOLEAN DEFAULT FALSE,
    opted_in        BOOLEAN DEFAULT TRUE,                 -- WhatsApp requires explicit opt-in
    opted_in_at     TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_wa_sub_lgas      ON whatsapp_subscriptions USING GIN(lga_ids);
CREATE INDEX idx_wa_sub_active    ON whatsapp_subscriptions(is_active);

-- ============================================================
-- HISTORICAL BASELINES
-- ============================================================

CREATE TABLE flood_events_historical (
    id              SERIAL PRIMARY KEY,
    event_year      SMALLINT NOT NULL,
    event_name      VARCHAR(128),
    affected_count  INTEGER,
    deaths          INTEGER,
    displaced       INTEGER,
    damage_ngn      BIGINT,
    lga_ids         INTEGER[],
    geom            GEOMETRY(MULTIPOLYGON, 4326),
    notes           TEXT,
    source          VARCHAR(128)
);

-- Seed 2024 baseline
INSERT INTO flood_events_historical
    (event_year, event_name, affected_count, deaths, displaced, damage_ngn, notes, source)
VALUES
    (2024, 'Nigeria Flood Season 2024', 5000000, 1000, 0, 100000000000,
     'Reference baseline for severity classification. Includes Alau Dam breach (Maiduguri): 230+ deaths, 600,000 displaced.',
     'NEMA 2024 Annual Report'),
    (2022, 'Nigeria Flood Season 2022', 2500000, 600, 1300000, 45000000000,
     'Major Niger/Benue confluence flooding. GloFAS comparison baseline.',
     'NEMA 2022');

-- ============================================================
-- SYSTEM & AUDIT
-- ============================================================

CREATE TABLE api_ingestion_log (
    id              BIGSERIAL PRIMARY KEY,
    source          VARCHAR(32) NOT NULL,
    tier            SMALLINT NOT NULL,
    endpoint        VARCHAR(256),
    status_code     SMALLINT,
    records_fetched INTEGER,
    latency_ms      INTEGER,
    error_msg       TEXT,
    data_timestamp  TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_ingest_log_source ON api_ingestion_log(source, ingested_at DESC);

CREATE TABLE data_staleness (
    source          VARCHAR(32) PRIMARY KEY,
    last_success    TIMESTAMPTZ,
    last_attempt    TIMESTAMPTZ,
    consecutive_failures INTEGER DEFAULT 0,
    current_tier    SMALLINT DEFAULT 1,
    is_degraded     BOOLEAN DEFAULT FALSE
);

-- ============================================================
-- VIEWS
-- ============================================================

CREATE VIEW v_current_high_risk_lgas AS
SELECT
    l.id,
    l.name_en,
    s.name_en AS state_name,
    l.flood_risk_class,
    l.flash_flood_probable,
    COALESCE(
        (SELECT MAX(ff.probability_pct)
         FROM flood_forecasts ff
         WHERE ff.lga_id = l.id
           AND ff.forecast_for >= CURRENT_DATE
           AND ff.forecast_for <= CURRENT_DATE + INTERVAL '7 days'),
        0
    ) AS max_7d_flood_prob,
    (SELECT a.severity
     FROM alerts a
     WHERE l.id = ANY(a.lga_ids)
       AND a.status = 'ACTIVE'
     ORDER BY
       CASE a.severity WHEN 'RED' THEN 1 WHEN 'ORANGE' THEN 2
                       WHEN 'YELLOW' THEN 3 ELSE 4 END
     LIMIT 1
    ) AS current_alert_severity
FROM lgas l
JOIN states s ON s.id = l.state_id
WHERE l.flood_risk_class = 'HIGH';

CREATE VIEW v_active_alerts AS
SELECT
    a.*,
    array_length(a.lga_ids, 1) AS affected_lga_count
FROM alerts a
WHERE a.status = 'ACTIVE'
  AND a.valid_from <= NOW()
  AND (a.valid_until IS NULL OR a.valid_until > NOW())
ORDER BY
    CASE a.severity WHEN 'RED' THEN 1 WHEN 'ORANGE' THEN 2
                    WHEN 'YELLOW' THEN 3 ELSE 4 END,
    a.created_at DESC;

-- ============================================================
-- HYPERTABLE PARTITIONING (TimescaleDB-ready)
-- Partition large time-series tables by month
-- ============================================================

-- If TimescaleDB is available:
-- SELECT create_hypertable('river_gauge_readings', 'observed_at');
-- SELECT create_hypertable('weather_observations', 'observed_at');
-- SELECT create_hypertable('alert_deliveries', 'created_at');

-- Otherwise, range partition by year-month:
-- (To be applied via execution/db/partition_setup.py)
