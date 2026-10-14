BEGIN;
CREATE TABLE IF NOT EXISTS document_grants (
 agency_id uuid NOT NULL,
 document_id text NOT NULL,
 user_id uuid NOT NULL,
 PRIMARY KEY(agency_id,document_id,user_id),
 FOREIGN KEY(agency_id,document_id) REFERENCES documents(agency_id,id) ON DELETE CASCADE,
 FOREIGN KEY(agency_id,user_id) REFERENCES agency_memberships(agency_id,user_id) ON DELETE CASCADE
);
ALTER TABLE document_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_grants FORCE ROW LEVEL SECURITY;
CREATE POLICY document_grants_scope ON document_grants
 USING (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid);
COMMIT;
