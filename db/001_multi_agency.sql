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
COMMIT;
