-- Explicit property access grants. No name/email matching against user-controlled payloads.
BEGIN;
CREATE TABLE IF NOT EXISTS property_access (
 agency_id uuid NOT NULL,
 property_id text NOT NULL,
 user_id uuid NOT NULL,
 access_role text NOT NULL CHECK (access_role IN ('landlord','tenant','trades')),
 PRIMARY KEY (agency_id,property_id,user_id,access_role),
 FOREIGN KEY (agency_id,property_id) REFERENCES properties(agency_id,id) ON DELETE CASCADE,
 FOREIGN KEY (agency_id,user_id) REFERENCES agency_memberships(agency_id,user_id) ON DELETE CASCADE
);
ALTER TABLE property_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE property_access FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS property_access_isolation ON property_access;
CREATE POLICY property_access_isolation ON property_access
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
CREATE INDEX IF NOT EXISTS property_access_user_idx ON property_access(agency_id,user_id,access_role);
COMMIT;
