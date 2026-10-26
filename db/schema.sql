-- GateSense schema v1.1
-- Rules:
--   * Every table carries site_id (multi-tenant). Cross-table references that
--     involve a site use composite FKs so rows can never point at another site's data.
--   * Plates are normalized by the backend (uppercase, no spaces/hyphens) BEFORE insert.
--     The DB enforces a loose shape only; strict Indian format checks live in the CV pipeline.
--   * The DB enforces invariants. The entry/exit WORKFLOW runs in FastAPI inside a
--     transaction that first takes a per-plate lock, e.g.:
--       SELECT pg_advisory_xact_lock(hashtextextended(site_id::text || ':' || plate, 0));
--   * Visitor pass expiry is decided at query time from valid_from/valid_until.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE DOMAIN plate_text AS TEXT
    CHECK (VALUE ~ '^[A-Z0-9]{4,12}$');

CREATE TABLE sites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('apartment', 'campus', 'office')),
    timezone    TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('entry', 'exit', 'both')),
    camera_source   TEXT,  -- video file path, webcam index, or RTSP url
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id, site_id)   -- target for composite FKs
);

-- Registered vehicles (residents, staff) and blacklisted plates
CREATE TABLE vehicles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    plate       plate_text NOT NULL,
    owner_name  TEXT,
    role        TEXT NOT NULL CHECK (role IN ('resident', 'staff', 'blacklisted')),
    unit        TEXT,  -- flat number or department
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (site_id, plate)
);

-- Visitor pre-approval: gate opens only inside the time window.
-- "Expired" is NOT a stored status: a pass is valid when
--   status = 'active' AND now() BETWEEN valid_from AND valid_until
CREATE TABLE visitor_passes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id      UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    plate        plate_text NOT NULL,
    visitor_name TEXT,
    host_name    TEXT,
    host_unit    TEXT,
    valid_from   TIMESTAMPTZ NOT NULL,
    valid_until  TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_until > valid_from)
);

CREATE INDEX idx_passes_lookup
    ON visitor_passes (site_id, plate, valid_from, valid_until)
    WHERE status = 'active';

-- One row per vehicle visit: plate + entry timestamp + exit timestamp (date included)
-- open        -> vehicle is inside, exit_time IS NULL
-- closed      -> normal exit, exit_time set
-- auto_closed -> a second entry arrived with no exit; exit_time stays NULL (unknown)
CREATE TABLE visits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id         UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    plate           plate_text NOT NULL,
    access_category TEXT NOT NULL
                    CHECK (access_category IN ('resident', 'staff', 'visitor', 'unknown')),
    entry_time      TIMESTAMPTZ NOT NULL,   -- camera capture time, not server time
    exit_time       TIMESTAMPTZ,
    entry_gate_id   UUID,
    exit_gate_id    UUID,
    entry_image     TEXT,                   -- path to cropped plate image
    exit_image      TEXT,
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'closed', 'auto_closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (exit_time IS NULL OR exit_time >= entry_time),
    CHECK (
        (status = 'open'        AND exit_time IS NULL) OR
        (status = 'closed'      AND exit_time IS NOT NULL) OR
        (status = 'auto_closed')
    ),
    FOREIGN KEY (entry_gate_id, site_id) REFERENCES gates (id, site_id),
    FOREIGN KEY (exit_gate_id,  site_id) REFERENCES gates (id, site_id),
    UNIQUE (id, site_id)   -- target for composite FKs
);

-- A plate can have only one open visit per site
CREATE UNIQUE INDEX uniq_open_visit
    ON visits (site_id, plate)
    WHERE status = 'open';

CREATE INDEX idx_visits_plate_time ON visits (site_id, plate, entry_time DESC);
CREATE INDEX idx_visits_time       ON visits (site_id, entry_time DESC);

CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    plate       plate_text NOT NULL,
    type        TEXT NOT NULL
                CHECK (type IN ('unknown_plate', 'blacklisted', 'double_entry',
                                'exit_without_entry', 'overstay')),
    visit_id    UUID,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (visit_id, site_id) REFERENCES visits (id, site_id)
);

CREATE INDEX idx_alerts_open ON alerts (site_id, resolved, created_at DESC);

-- Audit trail: one row per access decision, with the reason
CREATE TABLE access_logs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id      UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    gate_id      UUID NOT NULL,
    plate        plate_text NOT NULL,
    direction    TEXT NOT NULL CHECK (direction IN ('entry', 'exit')),
    decision     TEXT NOT NULL CHECK (decision IN ('allow', 'deny', 'flag')),
    reason       TEXT NOT NULL
                 CHECK (reason IN ('resident', 'staff', 'valid_pass', 'no_pass',
                                   'expired_pass', 'blacklisted', 'unknown_plate',
                                   'double_entry', 'exit_without_entry')),
    confidence   NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),  -- OCR confidence
    visit_id     UUID,
    captured_at  TIMESTAMPTZ NOT NULL,   -- camera capture time
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (gate_id,  site_id) REFERENCES gates  (id, site_id),
    FOREIGN KEY (visit_id, site_id) REFERENCES visits (id, site_id)
);

CREATE INDEX idx_access_logs_time  ON access_logs (site_id, captured_at DESC);
CREATE INDEX idx_access_logs_plate ON access_logs (site_id, plate, captured_at DESC);