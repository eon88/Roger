# Roger core relationships — 1D design

This document connects the People model (Party) to Property and Tenancy without using names or email strings as keys.

## Canonical relationships

| Relationship | From → To | Required data | What it means |
|---|---|---|---|
| Ownership | Party → Property | share/percentage if known, valid dates, status, source | Legal or recorded beneficial ownership; may be joint |
| Management authority | Party → Property | authority type, start/end, evidence/document, status | Agency permission to act; separate from ownership |
| Tenancy participation | Party → Tenancy | role (landlord/tenant/guarantor), valid dates, status | Person or organisation's position in that tenancy |
| Tenancy occupancy | Tenancy → Property | tenancy ID, dates, status | A particular letting of the property |
| Account identity | Account → Party | linked date, linked-by, verification state | Sign-in identity; never itself proves property access |
| Prospect conversion | Prospect → Party | linked date, agent, decision/audit ref | Reviewed link from a submitted enquiry/application to an identity |
| Operational involvement | Case/Job/Appointment/Document → Party, Property, optional Tenancy | stable IDs, involvement role | Who/property/tenancy the activity concerns |

A relational implementation should use join tables for many-to-many relationships, with unique IDs and validity dates. The illustrative JSON can carry arrays for the prototype but must preserve the same meanings.

## Permission rule

Access is calculated from authenticated Account → Party, role assignment, current Party-to-Property or Party-to-Tenancy relationship, resource-specific rules and the requested action. Never grant access by matching `display_name`, email, phone, or a client-supplied role. Agent access is a distinct agency permission. Trades access is limited to assigned/open work and its minimum associated property/case data.

Historical participants can remain attached to records after a relationship ends; that history does not imply current access. Each endpoint returns only fields required by that role. Changes to accounts, links, ownership, authority, roles and access status are audited.

## Relationship integrity

- An owner and management agent can be different Parties.
- A property can have multiple owners, each with their own share and dates.
- A property can have successive tenancies and joint tenants.
- A company can own or manage a property; its human contacts link through explicit Party-to-Party relations.
- Tenant, landlord or trades role assignments alone do not grant access to every property.
- Prospects are not active parties to a property/tenancy until an agent-approved relationship is created.
- Deactivation closes current relationships where appropriate but does not erase historical links.
- Merge is an explicit, audited agent action with a preview of all affected relations; no automatic merge by email.
- Invalid or overlapping ownership/tenancy dates are surfaced for agent review, not silently repaired.

## Transition strategy

1. Add Party and relationship IDs beside the existing string fields.
2. Introduce read-only compatibility projections (e.g. landlord display names) for existing screens.
3. Backfill and validate all relationships; unresolved matches remain unresolved and cannot grant portal access.
4. Move authorization checks to IDs, with role-by-role regression tests.
5. Remove string-based authorization and duplicate fields in a separate change after validation.
