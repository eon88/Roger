# Roger public acquisition — illustrated properties, leads and newsletters

**Status:** Built and tested as an isolated draft on `feature/roger-public-lettings-redesign-20261012`. Not published to Hostinger by this work.

## 1. Fictional examples — NEVER live rental inventory

The homepage shows six hard-coded *fictional example property styles* in a separate section. Every card is marked **FICTIONAL EXAMPLE** and states the indicative price and city are not real availability. This is marketing inspiration, not an offer or a viewable home.

- Two-bed flat — Leeds, example £1,250 pcm
- Studio — Bristol, example £820 pcm
- Family home — Sheffield, example £1,450 pcm
- Garden flat — Nottingham, example £925 pcm
- Terrace — York, example £1,180 pcm
- Room in a shared house — Manchester, example £650 pcm **per room**

They are deliberately **not** written into the live `properties`, `tenancies` or `public_listing` database, and they cannot be booked. They use CSS artwork, not invented photographs. Only genuinely authorised, unoccupied, advertised properties from `GET /api/public` can appear in the *Available properties* section.

Before public launch: verify actual agency and contact details, real professional memberships, terms, correct photo permissions and real property availability.

## 2. One prospect enquiry form → three human-reviewed pipelines

`POST /api/prospect-intake` validates name/email, a role, explicit enquiry contact consent, and some actual requirements. It stores `lead_source: public-homepage`, the role-specific requirements, and the recorded consent time.

| Visitor | Existing Roger storage | First stage | Human conversion |
|---|---|---|---|
| Home hunter | `cases` with `type=enquiry` and `role=renter` | `enquiry` | Agent progresses viewing/application/referencing/offer and links tenant correctly |
| Landlord | `registrations` with `role=landlord` | `lead`, `status=pending` | Agent reviews registration, evidence, agreement and property |
| Tradesperson | `registrations` with `role=trades` | `applicant`, `status=pending` | Agent verifies qualifications, insurance, coverage and links a role-scoped account |

**Submitting the public form never creates an active tenancy, agency instruction, verified contractor or portal login.** Existing protected `/api/prospect-action` remains the only tool for authorised agent progression and its lifecycle/approval guards continue to apply.

The older dedicated landlord and trades registration pages remain accessible for longer forms.

## 3. Consent-separated newsletters

The `POST /api/newsletter` interest form supports four audience categories:

- `prospective_tenant` → Renter Update
- `tenant` → Tenant Update
- `landlord` → Landlord Brief
- `trades` → Contractor Bulletin

It stores the explicit and separate `marketing_consent` decision, audience, time, source and consent-text version in `newsletter_subscriptions`. The same email can choose different categories; an exact email+audience pair deduplicates.

**No marketing emails or confirmation emails are sent.** Every new entry stays `pending_confirmation`. No entry should be exported as a confirmed subscription. An agent may suppress it using `POST /api/newsletter-action` with `action=unsubscribe`, audited. Only agents can read `/api/newsletter-subscriptions` or see the list in Agent → Prospects. No tenant/landlord/trade portal may access these contacts.

Still necessary before newsletter *sending*: a checked privacy notice and retention policy; mail provider/worker; confirmed opt-in link flow; verified sender/from address; correct UK marketing rules (including PECR), working recipient unsubscribe link, suppression list, bounce handling, sending preferences and proof of consent. Do not automatically enrol existing portal accounts.

## 4. Testing

- `tests/test_public_acquisition.py`: synthetic backend tests for routes, statuses, validation, deduplication, opt-out.
- `tests/public_homepage_browser.cjs`: Chrome checks separate mock vs live listings; genuine prospect form submissions; newsletter consent; mobile layout; anonymous subscription-list denial; agent visibility and suppression.
- CI runs all original repair and four-role browser acceptance tests.

No live website or genuine client record was touched by the development tests.
