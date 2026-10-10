-- DEV ONLY. This is NOT a production migration.
-- All tables use the mvp_ prefix and coexist with the legacy JSONB bridge.
-- PostgreSQL 16. Idempotent for a first-time empty DEV database.
BEGIN;

CREATE TABLE IF NOT EXISTS mvp_parties (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
  kind TEXT NOT NULL DEFAULT 'person' CHECK (kind IN ('person', 'organisation')),
  account_id TEXT UNIQUE,
  email TEXT,
  phone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mvp_properties (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  address_line TEXT NOT NULL,
  postcode TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','submitted','changes_requested','approved','declined','advertised','occupied','archived')),
  created_by_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mvp_property_people (
  property_id TEXT NOT NULL REFERENCES mvp_properties(id) ON DELETE CASCADE,
  party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  role TEXT NOT NULL CHECK (role IN ('landlord','tenant','agent')),
  PRIMARY KEY (property_id, party_id, role)
);
CREATE INDEX IF NOT EXISTS mvp_property_people_party_idx ON mvp_property_people(party_id);

CREATE TABLE IF NOT EXISTS mvp_property_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id TEXT NOT NULL REFERENCES mvp_properties(id) ON DELETE RESTRICT,
  submitted_by_party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'submitted'
    CHECK (status IN ('draft','submitted','changes_requested','approved','declined')),
  decision_note TEXT,
  decided_by_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mvp_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id TEXT REFERENCES mvp_properties(id) ON DELETE RESTRICT,
  uploaded_by_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  category TEXT NOT NULL,
  storage_key TEXT NOT NULL UNIQUE,
  original_filename TEXT NOT NULL,
  sha256_hex CHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- File bytes live in private object/file storage, not in this table.

CREATE TABLE IF NOT EXISTS mvp_property_compliance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id TEXT NOT NULL REFERENCES mvp_properties(id) ON DELETE RESTRICT,
  requirement_code TEXT NOT NULL,
  applicability TEXT NOT NULL DEFAULT 'review'
    CHECK (applicability IN ('required','not_applicable','review')),
  status TEXT NOT NULL DEFAULT 'missing'
    CHECK (status IN ('missing','uploaded','verified','rejected','expired')),
  document_id UUID REFERENCES mvp_documents(id) ON DELETE RESTRICT,
  expires_on DATE,
  verified_by_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  verified_at TIMESTAMPTZ,
  UNIQUE (property_id, requirement_code)
);
CREATE INDEX IF NOT EXISTS mvp_property_compliance_expiry_idx
  ON mvp_property_compliance(expires_on) WHERE expires_on IS NOT NULL;

CREATE TABLE IF NOT EXISTS mvp_contractor_profiles (
  party_id TEXT PRIMARY KEY REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  verification_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (verification_status IN ('pending','in_review','approved','suspended','declined')),
  service_area TEXT,
  insured_until DATE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mvp_contractor_skills (
  party_id TEXT NOT NULL REFERENCES mvp_contractor_profiles(party_id) ON DELETE CASCADE,
  trade_code TEXT NOT NULL,
  PRIMARY KEY (party_id, trade_code)
);
CREATE INDEX IF NOT EXISTS mvp_contractor_skills_trade_idx ON mvp_contractor_skills(trade_code);

CREATE TABLE IF NOT EXISTS mvp_contractor_credentials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id TEXT NOT NULL REFERENCES mvp_contractor_profiles(party_id) ON DELETE RESTRICT,
  credential_type TEXT NOT NULL,
  registration_number TEXT,
  document_id UUID REFERENCES mvp_documents(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','verified','rejected','expired')),
  expires_on DATE,
  checked_by_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  checked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS mvp_contractor_credentials_party_idx ON mvp_contractor_credentials(party_id);
CREATE INDEX IF NOT EXISTS mvp_contractor_credentials_expiry_idx
  ON mvp_contractor_credentials(expires_on) WHERE expires_on IS NOT NULL;

CREATE TABLE IF NOT EXISTS mvp_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id TEXT NOT NULL REFERENCES mvp_properties(id) ON DELETE RESTRICT,
  reported_by_party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'normal'
    CHECK (priority IN ('emergency','urgent','normal','low')),
  status TEXT NOT NULL DEFAULT 'reported'
    CHECK (status IN ('reported','triaged','assigned','in_progress','awaiting_confirmation','resolved','reopened','cancelled')),
  response_due_at TIMESTAMPTZ,
  assigned_agent_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS mvp_cases_property_idx ON mvp_cases(property_id);
CREATE INDEX IF NOT EXISTS mvp_cases_status_due_idx ON mvp_cases(status,response_due_at);

CREATE TABLE IF NOT EXISTS mvp_work_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES mvp_cases(id) ON DELETE RESTRICT,
  contractor_party_id TEXT REFERENCES mvp_contractor_profiles(party_id) ON DELETE RESTRICT,
  required_trade TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed','offered','accepted','declined','in_progress','evidence_submitted','completed','cancelled')),
  offered_at TIMESTAMPTZ,
  accepted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS mvp_work_orders_case_idx ON mvp_work_orders(case_id);
CREATE INDEX IF NOT EXISTS mvp_work_orders_contractor_idx ON mvp_work_orders(contractor_party_id);

CREATE TABLE IF NOT EXISTS mvp_case_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID NOT NULL REFERENCES mvp_cases(id) ON DELETE RESTRICT,
  work_order_id UUID REFERENCES mvp_work_orders(id) ON DELETE RESTRICT,
  author_party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  channel TEXT NOT NULL
    CHECK (channel IN ('tenant_agent','agent_private','work_order')),
  body TEXT NOT NULL CHECK (length(trim(body)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((channel = 'work_order') = (work_order_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS mvp_case_messages_case_time_idx ON mvp_case_messages(case_id,created_at);

CREATE TABLE IF NOT EXISTS mvp_invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  work_order_id UUID NOT NULL REFERENCES mvp_work_orders(id) ON DELETE RESTRICT,
  contractor_party_id TEXT NOT NULL REFERENCES mvp_contractor_profiles(party_id) ON DELETE RESTRICT,
  invoice_number TEXT NOT NULL,
  amount_pence BIGINT NOT NULL CHECK (amount_pence >= 0),
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft','submitted','queried','approved','rejected','paid')),
  submitted_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  UNIQUE (contractor_party_id,invoice_number)
);
CREATE INDEX IF NOT EXISTS mvp_invoices_status_idx ON mvp_invoices(status);

CREATE TABLE IF NOT EXISTS mvp_rent_charges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id TEXT NOT NULL REFERENCES mvp_properties(id) ON DELETE RESTRICT,
  tenant_party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  period_start DATE NOT NULL,
  due_on DATE NOT NULL,
  amount_pence BIGINT NOT NULL CHECK (amount_pence > 0),
  UNIQUE (property_id,tenant_party_id,period_start)
);
CREATE INDEX IF NOT EXISTS mvp_rent_charges_due_idx ON mvp_rent_charges(due_on);

CREATE TABLE IF NOT EXISTS mvp_rent_payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rent_charge_id UUID NOT NULL REFERENCES mvp_rent_charges(id) ON DELETE RESTRICT,
  amount_pence BIGINT NOT NULL CHECK (amount_pence > 0),
  received_on DATE NOT NULL,
  recorded_by_party_id TEXT NOT NULL REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  external_reference TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mvp_rent_payments_charge_idx ON mvp_rent_payments(rent_charge_id);

CREATE TABLE IF NOT EXISTS mvp_agent_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id UUID REFERENCES mvp_cases(id) ON DELETE RESTRICT,
  property_submission_id UUID REFERENCES mvp_property_submissions(id) ON DELETE RESTRICT,
  invoice_id UUID REFERENCES mvp_invoices(id) ON DELETE RESTRICT,
  action_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','cancelled')),
  due_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((case_id IS NOT NULL)::int + (property_submission_id IS NOT NULL)::int + (invoice_id IS NOT NULL)::int = 1)
);
CREATE INDEX IF NOT EXISTS mvp_agent_tasks_open_idx ON mvp_agent_tasks(status,due_at);

CREATE TABLE IF NOT EXISTS mvp_audit_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  actor_party_id TEXT REFERENCES mvp_parties(id) ON DELETE RESTRICT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS mvp_audit_events_entity_idx
  ON mvp_audit_events(entity_type,entity_id,occurred_at);

-- Useful even in development; true tamper resistance additionally requires
-- least-privilege app roles, external backups and monitored audit export.
CREATE OR REPLACE FUNCTION mvp_block_audit_modification()
RETURNS TRIGGER LANGUAGE plpgsql AS $mvp$
BEGIN
  RAISE EXCEPTION 'Audit events are append-only';
END;
$mvp$;
DROP TRIGGER IF EXISTS mvp_audit_append_only ON mvp_audit_events;
CREATE TRIGGER mvp_audit_append_only
  BEFORE UPDATE OR DELETE ON mvp_audit_events
  FOR EACH ROW EXECUTE FUNCTION mvp_block_audit_modification();

CREATE TABLE IF NOT EXISTS mvp_event_outbox (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS mvp_event_outbox_pending_idx
  ON mvp_event_outbox(created_at) WHERE delivered_at IS NULL;

COMMIT;
