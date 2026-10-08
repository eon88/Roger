# Roger Property model — 1B design

**Status:** target model and lifecycle decision. This document does not change live property records.

## Purpose

A Property is the long-lived physical dwelling record. It remains the same property through marketing, tenancy changes, void periods and management changes. Listings, ownership, management authority, tenancies, jobs, documents, compliance and financial activity link to its stable `property_id`.

## Target record

Illustrative JSON for the current prototype; the eventual relational schema can normalize address, marketing, status history and relationships into separate tables.

```json
{
  "id": "property_...",
  "address": {
    "building_name": null,
    "sub_building": null,
    "building_number": "12",
    "street": "Example Road",
    "locality": null,
    "town": "Exampleton",
    "region": null,
    "postcode": "AB1 2CD",
    "country": "GB"
  },
  "property_type": "flat",
  "bedrooms": 2,
  "bathrooms": null,
  "rent_amount_pence": 125000,
  "rent_frequency": "monthly",
  "marketing": {
    "public_title": "Bright two-bedroom flat",
    "description": "...",
    "cover_photo_id": null,
    "photo_ids": [],
    "available_from": null,
    "publicly_listed": false
  },
  "lifecycle_status": "onboarding",
  "management_status": "managed",
  "created_at": "...",
  "updated_at": "..."
}
```

Ownership and management are explicit, dated Party-to-Property relationships (see [1D relationships](core-relationships-1d.md)); they do not live as a landlord name on the property. Current and historical tenants are represented through Tenancies, not a mutable tenant-name string.

### Field rules

- Keep the current prototype's stable property IDs when migrating; never derive IDs from addresses.
- Store currency as integer minor units and frequency separately. A rent amount alone is not a complete rent obligation.
- Address is structured, but retain a single formatted display string for legacy/printing needs.
- Marketing data is separate from operational data. Never publish tenant, owner contact, internal notes or maintenance history.
- Photos and documents use IDs to file records; binary bodies belong in file storage later.
- Maintain separate `lifecycle_status` and `management_status`: e.g. a property can be occupied but not managed by Roger.
- An offboarded or sold record is archived, not deleted, so its historical cases, invoices and audit trail remain attributable.

## Lifecycle

`prospect → onboarding → ready_to_market → advertised → application → let_agreed → occupied → notice_given → checkout → void → remarketing → offboarded`

The lifecycle must allow valid real-world branches: onboarding may be declined/offboarded; an application may fail and return to advertised; a let agreed may fall through to void; a notice may be withdrawn; a void may be offboarded. Transitions are agent-audited and cannot silently rewrite history.

Only `lifecycle_status = advertised` plus `marketing.publicly_listed = true`, valid marketing content and a future/current availability date may appear publicly. The public API returns a safe projection. A transition away from advertised removes the listing; it does not delete it.

## Acceptance criteria

- A property retains its ID across every lifecycle state and tenancy.
- A property supports multiple owners and separately recorded management authority.
- Current tenant is derived from an active tenancy, never copied into a mutable owner/tenant field.
- Public listing visibility is state-driven and cannot expose private fields.
- Address, rent, photos, lifecycle and management state can be edited independently with audit history.
- A non-managed or offboarded property remains in internal history but is absent from public listings.

## Existing prototype mapping

Current seed records use `properties[]` objects with `id`, `title`, `area`, `beds`, `rent`, `landlord` and `tenant`. Exact mapping and ambiguity handling are in [1E](existing-data-map-1e.md).
