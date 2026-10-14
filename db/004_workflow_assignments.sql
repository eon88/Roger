-- Explicit repair-job and approval assignees, all agency scoped.
BEGIN;
CREATE TABLE IF NOT EXISTS job_assignments (
 agency_id uuid NOT NULL,
 job_id text NOT NULL,
 user_id uuid NOT NULL,
 PRIMARY KEY(agency_id,job_id,user_id),
 FOREIGN KEY(agency_id,job_id) REFERENCES jobs(agency_id,id) ON DELETE CASCADE,
 FOREIGN KEY(agency_id,user_id) REFERENCES agency_memberships(agency_id,user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS approval_recipients (
 agency_id uuid NOT NULL,
 approval_id text NOT NULL,
 user_id uuid NOT NULL,
 PRIMARY KEY(agency_id,approval_id,user_id),
 FOREIGN KEY(agency_id,approval_id) REFERENCES approvals(agency_id,id) ON DELETE CASCADE,
 FOREIGN KEY(agency_id,user_id) REFERENCES agency_memberships(agency_id,user_id) ON DELETE CASCADE
);
ALTER TABLE job_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_assignments FORCE ROW LEVEL SECURITY;
ALTER TABLE approval_recipients ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_recipients FORCE ROW LEVEL SECURITY;
CREATE POLICY job_assignments_tenant ON job_assignments
 USING (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid);
CREATE POLICY approval_recipients_tenant ON approval_recipients
 USING (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id=nullif(current_setting('roger.agency_id',true),'')::uuid);
COMMIT;
