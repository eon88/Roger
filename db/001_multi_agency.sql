-- Roger HQ multi-agency foundation (development only)
-- Run against a fresh PostgreSQL database. Does not migrate live JSON data.
BEGIN;
CREATE TABLE agencies (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL CHECK (length(trim(name)) > 0),
 slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
 status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','closed')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE app_users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 username text NOT NULL UNIQUE,
 password_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE agency_memberships (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 user_id uuid NOT NULL REFERENCES app_users(id),
 role text NOT NULL CHECK (role IN ('agent','landlord','tenant','trades')),
 PRIMARY KEY (agency_id,user_id)
);
CREATE TABLE platform_owners (
 user_id uuid PRIMARY KEY REFERENCES app_users(id)
);
CREATE TABLE properties (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 id text NOT NULL,
 title text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id)
);
CREATE TABLE cases (
 agency_id uuid NOT NULL,
 id text NOT NULL,
 property_id text,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id),
 FOREIGN KEY (agency_id,property_id) REFERENCES properties(agency_id,id)
);
CREATE TABLE jobs (
 agency_id uuid NOT NULL,
 id text NOT NULL,
 case_id text,
 property_id text,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id),
 FOREIGN KEY (agency_id,case_id) REFERENCES cases(agency_id,id),
 FOREIGN KEY (agency_id,property_id) REFERENCES properties(agency_id,id)
);
CREATE TABLE approvals (
 agency_id uuid NOT NULL,
 id text NOT NULL,
 job_id text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id),
 FOREIGN KEY (agency_id,job_id) REFERENCES jobs(agency_id,id)
);
CREATE TABLE appointments (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 id text NOT NULL,
 property_id text,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id),
 FOREIGN KEY (agency_id,property_id) REFERENCES properties(agency_id,id)
);
CREATE TABLE documents (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 id text NOT NULL,
 property_id text,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id),
 FOREIGN KEY (agency_id,property_id) REFERENCES properties(agency_id,id)
);
CREATE TABLE registrations (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 id text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id)
);
CREATE TABLE invitations (
 agency_id uuid NOT NULL REFERENCES agencies(id),
 id text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY (agency_id,id)
);
CREATE TABLE subscriptions (
 agency_id uuid PRIMARY KEY REFERENCES agencies(id),
 status text NOT NULL CHECK (status IN ('trial','active','past_due','cancelled')),
 plan text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_logs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 agency_id uuid REFERENCES agencies(id),
 actor_id uuid REFERENCES app_users(id),
 action text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
-- Tenant-aware reads and writes must be enforced by database policies.
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties FORCE ROW LEVEL SECURITY;
CREATE POLICY properties_agency_isolation ON properties
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE cases FORCE ROW LEVEL SECURITY;
CREATE POLICY cases_agency_isolation ON cases
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY jobs_agency_isolation ON jobs
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals FORCE ROW LEVEL SECURITY;
CREATE POLICY approvals_agency_isolation ON approvals
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments FORCE ROW LEVEL SECURITY;
CREATE POLICY appointments_agency_isolation ON appointments
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY documents_agency_isolation ON documents
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE registrations FORCE ROW LEVEL SECURITY;
CREATE POLICY registrations_agency_isolation ON registrations
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations FORCE ROW LEVEL SECURITY;
CREATE POLICY invitations_agency_isolation ON invitations
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE agency_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE agency_memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY agency_memberships_agency_isolation ON agency_memberships
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY subscriptions_agency_isolation ON subscriptions
 USING (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid)
 WITH CHECK (agency_id = nullif(current_setting('roger.agency_id',true),'')::uuid);
COMMIT;
