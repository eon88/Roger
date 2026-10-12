# Roger homepage improvements — October 2026

**Status:** Draft PR #7. Not automatically published to agency.lifecompass.shop.

## User-visible fixes
1. When /api/public returns no matching listings or zero active listings, **Register your requirements** appears. The existing location, minimum bedrooms and maximum rent filters carry over into the tenant intake form as an **enquiry only**. It is not a property alert subscription.
2. Switching tenant/landlord/trades journeys clears previous location, message and incompatible requirements, while retaining contact identity fields.
3. One clearly marked *Demo — not a real listing* illustration replaces the six examples. It never goes into /api/public and cannot be booked.
4. General newsletter interest is a secondary section close to the footer, explicitly marked as not sending any emails.
5. The footer has explicit slots for contact email, phone, areas served, and privacy link, initially marked not yet published.
6. The separate **/for-agents** page explains the agent platform and accepts demo requests. Requests are kept in `agency_demo_requests`, visible to **Agent → Prospects**, not exposed to tenant/landlord/trades portals.

## Configure real footer details
After **verifying** the business contact details, areas served and the actual privacy notice URL, edit a single file:

`stage-clone/public-site.json`

Example structure (**these values are examples, do NOT publish as real**):

```json
{
  "contact_email": null,
  "contact_phone": null,
  "areas_served": [],
  "privacy_url": null
}
```

Once the values are confirmed and genuinely usable, enter them, commit the file and deploy the updated application. The server exposes only those four explicitly allowlisted fields via `GET /api/public-site`. Unknown or invalid contact/link values are never published; internal office, credential, client and agent details stay private.

Do **not** fill with fake contact numbers, an invented address, false regulatory affiliations or a placeholder privacy URL. Link a real privacy notice before treating the site as a fully operational public acquisition system.

## Safety and testing
- Test suite `tests/test_homepage_fixes.py` validates the separate letting-agent lead type, consent, public configuration and rejection of unsafe contact values.
- `tests/public_homepage_browser.cjs` verifies search-to-intake carryover, tenant→landlord clearing, one demo card, empty public footer slots, letting-agent demo submission, Agent dashboard visibility, and mobile navigation.
- The existing workflows for viewing, repairs and roles must also continue to pass.
- Nothing in this branch sends real emails or starts newsletter delivery.
- No page changes live Roger without an explicitly triggered deploy.
