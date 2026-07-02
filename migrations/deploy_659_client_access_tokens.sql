-- deploy_NN: client_access_tokens — the external, per-client entry credential.
--
-- One row per issued magic-link. The plaintext token is shown to Jonathan ONCE
-- at mint time (returned by client_access.mint_token) and NEVER stored — only
-- its SHA-256 hash lives here, so a DB read cannot recover a live link. The
-- /client/<token> route hashes the presented token and looks it up here,
-- constant-time, resolving to EXACTLY ONE client_code.
--
-- Separation invariant: a token maps to one client_code (FK to clients). There
-- is no client_code in the URL, so a token holder cannot pivot to another
-- client. Revocation is a soft flag (revoked_at) so we keep an audit trail.

CREATE TABLE IF NOT EXISTS client_access_tokens (
    id           BIGSERIAL PRIMARY KEY,
    token_hash   TEXT        NOT NULL UNIQUE,          -- sha256 hex of the opaque token
    client_code  TEXT        NOT NULL REFERENCES clients(client_code),
    label        TEXT,                                 -- e.g. "MWK link handed 2026-07-02"
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ,                          -- NULL = live; set = dead
    last_seen_at TIMESTAMPTZ                           -- updated on each valid hit (light audit)
);

CREATE INDEX IF NOT EXISTS idx_client_access_tokens_client
    ON client_access_tokens (client_code);

-- Lookup is by token_hash (already UNIQUE-indexed). A partial index on live
-- tokens keeps the hot path tight.
CREATE INDEX IF NOT EXISTS idx_client_access_tokens_live
    ON client_access_tokens (token_hash) WHERE revoked_at IS NULL;
