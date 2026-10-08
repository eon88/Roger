CREATE TABLE IF NOT EXISTS roger_stage_snapshot (
    singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
    payload JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS roger_users_snapshot (
    singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
    payload JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS roger_parties (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS roger_properties (
    id TEXT PRIMARY KEY,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS roger_tenancies (
    id TEXT PRIMARY KEY,
    property_id TEXT,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS roger_tenancies_property_idx ON roger_tenancies(property_id);
CREATE TABLE IF NOT EXISTS roger_cases (
    id TEXT PRIMARY KEY,
    property_id TEXT,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS roger_cases_property_idx ON roger_cases(property_id);
CREATE TABLE IF NOT EXISTS roger_jobs (
    id TEXT PRIMARY KEY,
    case_id TEXT,
    property_id TEXT,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS roger_jobs_case_idx ON roger_jobs(case_id);
CREATE INDEX IF NOT EXISTS roger_jobs_property_idx ON roger_jobs(property_id);
CREATE TABLE IF NOT EXISTS roger_documents (
    id TEXT PRIMARY KEY,
    case_id TEXT,
    property_id TEXT,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS roger_documents_property_idx ON roger_documents(property_id);
