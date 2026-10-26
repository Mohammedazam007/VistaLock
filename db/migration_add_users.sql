-- Add dashboard users to the existing VistaLock database.
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    email         TEXT NOT NULL UNIQUE CHECK (email = lower(email)),
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'security', 'resident')),
    unit          TEXT,
    full_name     TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (role <> 'resident' OR unit IS NOT NULL)
);
