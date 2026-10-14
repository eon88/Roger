-- Development-only session store. Apply after 001_multi_agency.sql.
BEGIN;
CREATE TABLE IF NOT EXISTS agency_sessions (
 token_hash text PRIMARY KEY,
 user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 agency_id uuid NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (agency_id,user_id) REFERENCES agency_memberships(agency_id,user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS agency_sessions_expiry_idx ON agency_sessions(expires_at);
ALTER TABLE agency_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agency_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS agency_sessions_isolation ON agency_sessions;
CREATE POLICY agency_sessions_isolation ON agency_sessions
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
COMMIT;
