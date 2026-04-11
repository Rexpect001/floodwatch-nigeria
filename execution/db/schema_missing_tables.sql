-- ============================================================
-- Missing tables referenced by API routers
-- Apply after schema.sql: psql $DATABASE_URL -f schema_missing_tables.sql
-- ============================================================

-- ── SMS Subscriptions (referenced by alerts.py router) ────────

CREATE TABLE sms_subscriptions (
    id                  SERIAL PRIMARY KEY,
    msisdn              VARCHAR(16) NOT NULL UNIQUE,          -- +234XXXXXXXXXX
    lang                CHAR(2) NOT NULL DEFAULT 'en'
                            CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),
    lga_ids             INTEGER[] NOT NULL DEFAULT '{}',
    severity_threshold  VARCHAR(8) NOT NULL DEFAULT 'ORANGE'
                            CHECK (severity_threshold IN ('RED', 'ORANGE', 'YELLOW', 'GREEN')),
    is_active           BOOLEAN DEFAULT TRUE,
    opted_out_at        TIMESTAMPTZ,                          -- STOP keyword
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sms_sub_lgas   ON sms_subscriptions USING GIN(lga_ids);
CREATE INDEX idx_sms_sub_active ON sms_subscriptions(is_active, severity_threshold);

-- Trigger: update sms_subscriptions.updated_at
CREATE TRIGGER trg_sms_sub_updated
    BEFORE UPDATE ON sms_subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Error Reports (referenced by alerts.py router) ─────────────

CREATE TABLE error_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id            UUID REFERENCES alerts(id),
    lga_id              INTEGER REFERENCES lgas(id),
    description         TEXT NOT NULL,
    reporter_contact    TEXT,                                 -- optional, not required
    status              VARCHAR(16) DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'REVIEWED', 'ACTIONED', 'DISMISSED')),
    reviewed_by         VARCHAR(64),
    reviewed_at         TIMESTAMPTZ,
    reviewer_notes      TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_error_report_alert  ON error_reports(alert_id);
CREATE INDEX idx_error_report_status ON error_reports(status, created_at DESC);

-- ── User Preferences (language, notification settings) ────────

CREATE TABLE user_preferences (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    msisdn          VARCHAR(16),
    device_token    TEXT,                                     -- FCM/APNs push token
    lang            CHAR(2) DEFAULT 'en'
                        CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),
    lga_ids         INTEGER[] DEFAULT '{}',
    dark_mode       BOOLEAN DEFAULT FALSE,
    data_saver      BOOLEAN DEFAULT FALSE,
    high_contrast   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Ingestion Rate Limit Counters (OWM quota enforcement) ─────
-- Managed in Redis at runtime, but persisted daily for audit

CREATE TABLE api_quota_log (
    id          BIGSERIAL PRIMARY KEY,
    source      VARCHAR(32) NOT NULL,
    date        DATE NOT NULL DEFAULT CURRENT_DATE,
    calls_made  INTEGER DEFAULT 0,
    quota_limit INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, date)
);
