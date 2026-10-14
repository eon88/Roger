-- Private, agency-isolated messages between agency members.
BEGIN;
CREATE TABLE IF NOT EXISTS agency_messages (
 agency_id uuid NOT NULL,
 id uuid NOT NULL DEFAULT gen_random_uuid(),
 sender_id uuid NOT NULL,
 recipient_id uuid NOT NULL,
 body text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(agency_id,id),
 FOREIGN KEY(agency_id,sender_id) REFERENCES agency_memberships(agency_id,user_id),
 FOREIGN KEY(agency_id,recipient_id) REFERENCES agency_memberships(agency_id,user_id)
);
ALTER TABLE agency_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agency_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY agency_messages_tenant ON agency_messages
 USING (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid);
CREATE INDEX IF NOT EXISTS agency_messages_recipient_idx
 ON agency_messages(agency_id,recipient_id,created_at);
COMMIT;
