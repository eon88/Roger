# Offline agency migration — Roger v1

This tool is for importing a letting agency's existing records into an **isolated, stopped** Roger agency instance. **No property sales. No tenant portal accounts are created. No rental listings are published.**

The importer has three CSV inputs, all UTF-8. Stable `external_id` values from the original agency system are used for idempotence. It will **not** merge people merely because an email matches. Check the mapping report before accepting any data.

## Files

`people.csv`

```csv
external_id,display_name,role,email,phone
owner-101,Sample Landlord,landlord,sample-landlord@example.invalid,00000000001
tenant-501,Sample Tenant,tenant,sample-tenant@example.invalid,00000000002
```

Permitted `role`: landlord, tenant, guarantor, trades. To represent multiple roles for the same real person, import separate records and verify/merge them manually using the agency's audited Party process.

`properties.csv`

```csv
external_id,title,area,landlord_external_id,address,postcode
flat-300,Sample Flat,Leeds,owner-101,17 Sample Road,LS1 1AA
```

`tenancies.csv`

```csv
external_id,property_external_id,tenant_external_id,landlord_external_id,start_date,rent_amount_pence,rent_frequency,deposit_amount_pence
lease-333,flat-300,tenant-501,owner-101,2026-08-01,110000,monthly,110000
```

Dates must be ISO YYYY-MM-DD. Money is in **integer pence**. Standard assured periodic rent periods are weekly, fortnightly or monthly. The Tenant Fees Act deposit cap is checked, but the tool is **not** a deposit-compliance certification.

## Run without modifying any data

```bash
python3 ops/migration/agency_import.py \
  --data-dir /srv/offline-agency-copy \
  --people people.csv --properties properties.csv --tenancies tenancies.csv
```

The tool validates the entire input set, references and linked identities, reports created/already-present record counts, and exits **without writing**. Fix every error in the source CSVs before applying.

## Optional apply — only to a verified stopped offline instance

```bash
ROGER_ENV=test ROGER_MIGRATION_OFFLINE=1 \
python3 ops/migration/agency_import.py \
  --data-dir /srv/offline-agency-copy \
  --people people.csv --properties properties.csv --tenancies tenancies.csv \
  --apply --confirm OFFLINE-IMPORT
```

The original `stage.json` is saved with mode 0600 under `backups/before-agency-import-TIMESTAMP.json`. The new snapshot is written via atomic replace. The program refuses `--apply` in `ROGER_ENV=production` or `staging`. **The operator must stop the agency app** before applying, then verify records, source documents and money totals on the isolated clone. These backups remain local and are **not** a substitute for the encrypted off-site operational backup and restore plan.

## Post-import acceptance

- Verify unique owners, tenants, properties and tenancy links; no agency ID crossover.
- Verify statutory documents, rent balances, deposits, dates and consent against original source records.
- Imported people have **no portal credentials**. Invite only after identity and property relationship checks.
- Imported properties remain **onboarding**, never publicly advertised until reviewed.
- Imported tenancies remain **application/draft**, even if the old platform called them active. Advance them only after agent review and proper agreement evidence.
- Run both import previews and reconciliation reports. Back up and test an isolated restore before any actual production migration.

This limited importer covers *people, properties and initial tenancy data*. Work orders, historic repairs, documents and ledger transaction migration are **not yet included**. Do not call agency migration fully accepted until those are covered or documented for manual reconciliation.
