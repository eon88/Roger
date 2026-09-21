# Data Model — Shared JSON Schemas for Missing Primitives

These are the exact JSON shapes referenced in the four lifecycle docs (agent, tenant, landlord, trades) as `NEEDS`. Implementing these endpoints / objects will make the workflows fully buildable.

## 1. Appointment Object

Used for viewings, inspections, key handovers, final inspections.

```json
{
  "id": "string (uuid)",
  "case_id": "string (uuid) optional – links to tenant case if any",
  "property_id": "string (uuid) required",
  "title": "string (e.g., 'Viewing', 'Key Handover', 'Final Inspection')",
  "description": "string optional",
  "start_time": "string (ISO 8601 datetime)",
  "end_time": "string (ISO 8601 datetime)",
  "location": "string optional (address or 'At property')",
  "status": "enum [proposed, confirmed, declined, completed, missed, cancelled]",
  "created_by": "string (agent user_id)",
  "created_at": "string (ISO 8601)",
  "updated_at": "string (ISO 8601)",
  "notes": "string optional (agent notes after completion)",
  "outcome": "string optional (e.g., 'Keys handed', 'Access granted', 'Issues noted')"
}
```

### Endpoints
- `POST /api/appointment` – create (agent)
- `PATCH /api/appointment/:id` – confirm/decline/complete (agent or prospect/tenant as appropriate)
- `GET /api/appointment?property_id=…` – list for a property
- `GET /api/appointment/:id` – get details

---

## 2. Invitation Token

Used by agent to invite a prospect to create a portal account (tenant role).

```json
{
  "id": "string (uuid)",
  "prospect_id": "string (uuid) optional – links to prospect/registration record",
  "property_id": "string (uuid) required – the property they are being invited for",
  "role": "enum [tenant, landlord, trades] – typically tenant",
  "token": "string (cryptographically random, URL-safe)",
  "expires_at": "string (ISO 8601 datetime)",
  "used_at": "string (ISO 8601 datetime) optional",
  "created_by": "string (agent user_id)",
  "created_at": "string (ISO 8601)",
  "invited_email": "string (prospect email)",
  "invited_name": "string optional"
}
```

### Endpoints
- `POST /api/invitation` – agent creates token (returns token + link)
- `GET /api/invitation/validate/:token` – validate token (used by login page)
- `POST /api/invitation/use/:token` – mark as used (on successful account creation)

---

## 3. Agreement / Document Upload

For tenancy agreement, deposit receipt, inspection reports, etc.

```json
{
  "id": "string (uuid)",
  "case_id": "string (uuid) required – links to tenant case",
  "property_id": "string (uuid) required",
  "uploaded_by": "string (agent user_id)",
  "document_type": "enum [tenancy_agreement, deposit_receipt, inspection_report, id_proof, other]",
  "title": "string (human readable)",
  "description": "string optional",
  "file_name": "string (original filename)",
  "file_url": "string (URL to stored file – could be local upload path or external storage)",
  "file_size": "integer (bytes)",
  "uploaded_at": "string (ISO 8601)",
  "verified_by": "string (agent user_id) optional – who confirmed it's correct",
  "verified_at": "string (ISO 8601) optional",
  "status": "enum [pending, verified, rejected]",
  "notes": "string optional"
}
```

### Endpoints
- `POST /api/documents` – upload (multipart/form-data) → returns document object
- `PATCH /api/documents/:id` – verify/reject, update notes
- `GET /api/documents?case_id=…` – list documents for a case
- `GET /api/documents/:id` – get document metadata (not file; file served via `/files/:id` static)

---

## 4. Termination Event

Records the end of a tenancy, reason, and key return confirmation.

```json
{
  "id": "string (uuid)",
  "case_id": "string (uuid) required",
  "property_id": "string (uuid) required",
  "terminated_by": "string (agent user_id)",
  "reason": "enum [voluntary_notice, non_payment_2months, property_damage, landlord_sale, landlord_move_in, mutual_agreement, other]",
  "notice_start_date": "string (ISO 8601 date) optional – when notice was given",
  "termination_date": "string (ISO 8601 date) – effective end date",
  "key_return_confirmed": "boolean",
  "key_return_date": "string (ISO 8601 date) optional",
  "final_inspection_passed": "boolean optional",
  "damage_notes": "string optional – if reason includes damage",
  "outstanding_balance": "number (currency) optional – rent/fees owed",
  "deposit_due_return": "number (currency) optional – amount to return to tenant",
  "created_at": "string (ISO 8601)",
  "notes": "string optional"
}
```

### Endpoints
- `POST /api/termination` – agent creates termination event
- `PATCH /api/termination/:id` – update (e.g., confirm key return)
- `GET /api/termination?case_id=…` – get termination for a case
- `GET /api/termination/:id` – get details

---

## 5. Job-Status Enum (on Case / Job Object)

Used by trades workflow to track repair/maintenance job progress.

Add to existing `case` or a separate `job` object; here as enum values:

```json
"job_status": "enum [pending_quote, quote_approved, scheduled, in_progress, awaiting_payment, completed, cancelled]"
```

If a dedicated `job` object is preferred:

```json
{
  "id": "string (uuid)",
  "case_id": "string (uuid) required",
  "property_id": "string (uuid) required",
  "tradesperson_id": "string (uuid) optional",
  "title": "string (short description)",
  "description": "string optional",
  "job_type": "string (e.g., 'plumbing', 'electrical', 'painting')",
  "status": "enum [pending_quote, quote_approved, scheduled, in_progress, awaiting_payment, completed, cancelled]",
  "quote_amount": "number optional",
  "final_amount": "number optional",
  "assigned_at": "string (ISO 8601)",
  "started_at": "string (ISO 8601) optional",
  "completed_at": "string (ISO 8601) optional",
  "created_at": "string (ISO 8601)",
  "updated_at": "string (ISO 8601)"
}
```

### Endpoints (if using job object)
- `POST /api/job` – create (agent)
- `PATCH /api/job/:id` – update status, add notes
- `GET /api/job?case_id=…` – list jobs for a case
- `GET /api/job/:id` – get details

---

## 6. Prospect Record (optional alternative to extending registration)

If you prefer a separate prospect entity instead of overloading `registration`.

```json
{
  "id": "string (uuid)",
  "property_id": "string (uuid) required – which property they enquired about",
  "full_name": "string",
  "phone": "string",
  "email": "string",
  "status": "enum [enquired, vetted_approved, vetted_rejected, invited, visited, agreed, paid, moved_in, rejected]",
  "veted_by": "string (agent user_id) optional",
  "invited_by": "string (agent user_id) optional",
  "invitation_token_id": "string (uuid) optional – links to invitation record",
  "created_at": "string (ISO 8601)",
  "updated_at": "string (ISO 8601)",
  "notes": "string optional"
}
```

### Endpoints
- `GET /api/prospects` – agent list (filter by status/property)
- `PATCH /api/prospects/:id` – update status, add notes
- `POST /api/prospects` – create from registration (agent after vetting)

---

## How to Use

Each lifecycle doc references these objects by name. When you see `NEEDS appointment object`, implement the schema and endpoints above. Once these six primitives are in place, all four lifecycle documents become directly actionable — no further invention required.