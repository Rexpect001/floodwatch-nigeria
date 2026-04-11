-- ============================================================
-- Voice Alert Production & Governance Pipeline — DB Schema
-- Extends schema.sql; apply with: psql $DATABASE_URL -f schema_voice.sql
-- ============================================================

-- ============================================================
-- VOICE ALERT SESSIONS (one per alert, tracks all 5 pipeline steps)
-- ============================================================

CREATE TYPE voice_pipeline_status AS ENUM (
    'DRAFT',           -- Step 1: English source being composed
    'TRANSLATING',     -- Step 2: Claude API batch in progress
    'SYNTHESISING',    -- Step 3: TTS generation in progress
    'PENDING_REVIEW',  -- Step 4: Officer review gate
    'APPROVED',        -- Step 4: Passed governance
    'REJECTED',        -- Step 4: Rejected — needs rework
    'QUEUED',          -- Step 5: In RabbitMQ, pending dispatch
    'DISPATCHED',      -- Handed to Africa's Talking Voice + Radio FTP
    'FAILED'
);

CREATE TABLE voice_alert_sessions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id            UUID REFERENCES alerts(id),          -- parent alert record

    -- Step 1: Source composition
    source_text_en      TEXT NOT NULL CHECK (char_length(source_text_en) <= 280),
    source_composed_at  TIMESTAMPTZ,
    source_composed_by  VARCHAR(64),                          -- officer user_id

    -- Step 2: AI Translation
    translation_job_id  VARCHAR(128),                         -- Claude API request_id
    translation_at      TIMESTAMPTZ,
    translation_ms      INTEGER,                              -- latency tracking

    -- Step 3: Audio Synthesis
    synthesis_started_at TIMESTAMPTZ,
    synthesis_completed_at TIMESTAMPTZ,
    tts_tier_used       VARCHAR(16) CHECK (tts_tier_used IN (
                            'BROWSER', 'GOOGLE_CLOUD', 'COQUI', 'PHRASE_BANK', 'DISABLED'
                        )),

    -- Step 4: Governance
    status              voice_pipeline_status DEFAULT 'DRAFT',
    primary_approver_id VARCHAR(64),
    primary_approved_at TIMESTAMPTZ,
    secondary_approver_id VARCHAR(64),                        -- RED: dual-auth
    secondary_approved_at TIMESTAMPTZ,
    rejection_reason    TEXT,
    is_emergency_override BOOLEAN DEFAULT FALSE,
    override_officer_id VARCHAR(64),
    override_at         TIMESTAMPTZ,
    override_audit_report_due TIMESTAMPTZ,                    -- 24h post-incident

    -- Step 5: Queue
    rabbitmq_message_id VARCHAR(256),
    queued_at           TIMESTAMPTZ,
    dispatched_at       TIMESTAMPTZ,

    -- Audio integrity
    audio_checksum_ha   CHAR(64),                            -- SHA-256
    audio_checksum_yo   CHAR(64),
    audio_checksum_ig   CHAR(64),
    audio_checksum_pg   CHAR(64),
    audio_checksum_en   CHAR(64),

    -- S3 paths (set after synthesis)
    s3_prefix           TEXT,                                -- nimet-plus-alerts/voice/{id}/

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_voice_session_alert  ON voice_alert_sessions(alert_id);
CREATE INDEX idx_voice_session_status ON voice_alert_sessions(status, created_at DESC);

-- ============================================================
-- LANGUAGE VARIANTS (one row per language per session)
-- ============================================================

CREATE TABLE voice_clips (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID REFERENCES voice_alert_sessions(id) ON DELETE CASCADE,
    lang                CHAR(2) NOT NULL CHECK (lang IN ('en', 'ha', 'yo', 'ig', 'pg')),

    -- Translation
    script_text         TEXT NOT NULL,
    translation_confidence NUMERIC(4,3) CHECK (translation_confidence BETWEEN 0 AND 1),
    translation_flagged BOOLEAN DEFAULT FALSE,               -- confidence < 0.85
    forbidden_words_found TEXT[],                            -- loanword violations

    -- Audio
    tts_engine          VARCHAR(32),
    tts_voice_id        VARCHAR(128),
    audio_duration_s    NUMERIC(6,2),
    audio_url           TEXT,                                -- S3 pre-signed or CloudFront
    audio_s3_key        TEXT,
    audio_checksum      CHAR(64),
    waveform_data       JSONB,                               -- amplitude array for canvas render
    lufs_level          NUMERIC(5,2),                        -- target -16 LUFS
    is_phrase_bank      BOOLEAN DEFAULT FALSE,               -- Igbo concatenative TTS
    tts_disabled        BOOLEAN DEFAULT FALSE,               -- Fulfulde: no TTS
    waived              BOOLEAN DEFAULT FALSE,               -- explicit officer waiver

    -- Officer review tracking
    playback_duration_s NUMERIC(6,2) DEFAULT 0,             -- must be > 50% of audio_duration_s
    played_once         BOOLEAN DEFAULT FALSE,
    review_complete     BOOLEAN DEFAULT FALSE,

    synthesis_error     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (session_id, lang)
);

CREATE INDEX idx_clip_session ON voice_clips(session_id);

-- ============================================================
-- APPROVAL AUDIT LOG (immutable)
-- ============================================================

CREATE TABLE voice_approval_audit (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID REFERENCES voice_alert_sessions(id),
    officer_id      VARCHAR(64) NOT NULL,
    action          VARCHAR(32) NOT NULL CHECK (action IN (
                        'PLAYBACK_STARTED', 'PLAYBACK_COMPLETED',
                        'APPROVED', 'REJECTED', 'WAIVED_LANG',
                        'EMERGENCY_OVERRIDE', 'QUEUED', 'DISPATCHED'
                    )),
    lang            CHAR(2),
    playback_pct    NUMERIC(5,2),                            -- % of clip played
    notes           TEXT,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_session ON voice_approval_audit(session_id);
CREATE INDEX idx_audit_officer ON voice_approval_audit(officer_id, created_at DESC);

-- ============================================================
-- NEMA OFFICER ROLES
-- ============================================================

CREATE TABLE nema_officers (
    id              VARCHAR(64) PRIMARY KEY,                 -- SSO user ID
    name            VARCHAR(128) NOT NULL,
    email           VARCHAR(256),
    role            VARCHAR(32) CHECK (role IN (
                        'OFFICER',        -- standard approver
                        'SENIOR_OFFICER', -- dual-auth second approver (RED)
                        'DIRECTOR',       -- emergency override
                        'ADMIN'
                    )),
    state_id        INTEGER REFERENCES states(id),           -- jurisdiction
    is_active       BOOLEAN DEFAULT TRUE,
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PHRASE BANK (Igbo/Fulfulde concatenative TTS)
-- ============================================================

CREATE TABLE phrase_bank (
    id              SERIAL PRIMARY KEY,
    lang            CHAR(2) NOT NULL,
    phrase_key      VARCHAR(128) NOT NULL,                   -- e.g. 'evacuate_now'
    phrase_text     TEXT NOT NULL,
    audio_s3_key    TEXT NOT NULL,
    audio_duration_s NUMERIC(5,2),
    recorded_by     VARCHAR(128),                            -- native speaker ID
    verified        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (lang, phrase_key)
);

-- Seed critical Igbo phrase keys (audio WAV assets to be recorded)
INSERT INTO phrase_bank (lang, phrase_key, phrase_text, audio_s3_key, recorded_by)
VALUES
    ('ig', 'evacuate_now',       'Pụọ ugbu a',                             'phrase-bank/ig/evacuate_now.wav',       'pending'),
    ('ig', 'flood_warning',      'Ịdá adá mmiri',                          'phrase-bank/ig/flood_warning.wav',      'pending'),
    ('ig', 'shelter_location',   'Ebe nchekwa dị na',                      'phrase-bank/ig/shelter_location.wav',   'pending'),
    ('ig', 'danger_imminent',    'Ihe ize ndụ dị nso',                     'phrase-bank/ig/danger_imminent.wav',    'pending'),
    ('ig', 'stay_indoors',       'Nọdị n''ime ụlọ',                        'phrase-bank/ig/stay_indoors.wav',       'pending'),
    ('ig', 'call_nema',          'Kpọọ NEMA ọnụ ihe ngwọta',               'phrase-bank/ig/call_nema.wav',          'pending'),
    ('ig', 'water_rising',       'Mmiri na-enweda',                        'phrase-bank/ig/water_rising.wav',       'pending'),
    ('ig', 'heatwave_warning',   'Okpomọkụ dị oke egwu',                   'phrase-bank/ig/heatwave_warning.wav',   'pending'),
    ('ig', 'all_clear',          'Ihe ize ndụ agafeela',                   'phrase-bank/ig/all_clear.wav',          'pending'),
    ('ig', 'this_is_official',   'Nke a bụ ọdịmara gọọmenti',              'phrase-bank/ig/this_is_official.wav',   'pending');

-- ============================================================
-- WHATSAPP COMMUNITY REVIEWER (Phase 2)
-- ============================================================

CREATE TABLE whatsapp_reviewers (
    id              SERIAL PRIMARY KEY,
    msisdn          VARCHAR(16) UNIQUE NOT NULL,
    name            VARCHAR(128),
    lang_expertise  CHAR(2)[] NOT NULL,                      -- languages they can review
    lga_id          INTEGER REFERENCES lgas(id),
    role_type       VARCHAR(32) CHECK (role_type IN (
                        'TRADITIONAL_RULER', 'SEMA_STAFF', 'COMMUNITY_VOLUNTEER'
                    )),
    approval_count  INTEGER DEFAULT 0,
    rejection_rate  NUMERIC(4,3) DEFAULT 0,
    is_blocked      BOOLEAN DEFAULT FALSE,                   -- >20% rejection rate
    airtime_balance_ngn NUMERIC(8,2) DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE whatsapp_review_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID REFERENCES voice_alert_sessions(id),
    clip_id         UUID REFERENCES voice_clips(id),
    reviewer_id     INTEGER REFERENCES whatsapp_reviewers(id),
    sent_at         TIMESTAMPTZ,
    response        VARCHAR(8) CHECK (response IN ('APPROVED', 'REJECTED', NULL)),
    correction_text TEXT,
    responded_at    TIMESTAMPTZ,
    redis_ttl_key   TEXT,                                    -- 24h TTL tracking
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TRIGGER: update voice_alert_sessions.updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_voice_session_updated
    BEFORE UPDATE ON voice_alert_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_voice_clip_updated
    BEFORE UPDATE ON voice_clips
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- VIEW: pipeline progress summary
-- ============================================================

CREATE VIEW v_voice_pipeline_summary AS
SELECT
    s.id,
    s.alert_id,
    s.status,
    s.source_text_en,
    a.severity AS alert_severity,
    COUNT(c.id)                                              AS total_clips,
    COUNT(c.id) FILTER (WHERE c.audio_url IS NOT NULL)      AS clips_synthesised,
    COUNT(c.id) FILTER (WHERE c.review_complete)            AS clips_reviewed,
    COUNT(c.id) FILTER (WHERE c.translation_flagged)        AS clips_flagged,
    BOOL_AND(
        c.review_complete OR c.waived OR c.tts_disabled
    )                                                        AS all_clips_ready,
    s.primary_approved_at,
    s.secondary_approved_at,
    EXTRACT(EPOCH FROM (s.synthesis_completed_at - s.translation_at))
                                                             AS synthesis_latency_s,
    s.created_at
FROM voice_alert_sessions s
LEFT JOIN alerts a ON a.id = s.alert_id
LEFT JOIN voice_clips c ON c.session_id = s.id
GROUP BY s.id, a.severity;
