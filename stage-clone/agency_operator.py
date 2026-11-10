#!/usr/bin/env python3
"""B03 operator-only agency lifecycle changes inside the selected agency container.

Example (synthetic CI stack only; do NOT run on existing production):
  python /app/agency_operator.py --agency stg-oak --action set_plan \
    --reason 'Verified synthetic agency pilot agreement' \
    --plan pilot --property-limit 15 --staff-limit 3 --reviewed

This script does not take payment, manage DNS, delete files or approve a
legal obligation. Use reviewed agency-specific export/backup before cancellation.
"""
import argparse
import json
import os

import agency_admin
import serve


def execute(args):
    """Fail closed on any missing or foreign agency identity."""
    if (os.environ.get("ROGER_SAAS_MODE") != "1"
            or os.environ.get("ROGER_STORAGE_BACKEND") != "postgres"
            or not args.reviewed or not args.agency
            or args.agency != os.environ.get("ROGER_AGENCY_ID")):
        raise ValueError("dedicated PostgreSQL stack and verified agency review required")
    if args.action == "cancel" and (not args.export_reference
            or len(args.export_reference.strip()) < 12):
        raise ValueError("cancellation requires a reviewed export/retention reference")
    with serve.storage_write_lock():
        stage = serve.load_stage()
        if stage.get("agency_id") != args.agency:
            raise ValueError("agency database does not match intended customer")
        profile = stage.get("agency_profile")
        if not isinstance(profile, dict) or profile.get("agency_id") != args.agency:
            raise ValueError("agency profile does not match intended customer")
        if args.action == "activate":
            if (profile.get("plan") == "unassigned"
                    or not profile.get("legal_name")
                    or not profile.get("office_email")
                    or not profile.get("office_phone")
                    or not profile.get("office_address")):
                raise ValueError("plan and real verified agency contact details required")
        new, event = agency_admin.operator_transition(
            profile, args.action, reason=args.reason,
            evidence=args.invoice_reference, plan=args.plan,
            property_limit=args.property_limit, staff_limit=args.staff_limit)
        # Revoke sessions *before* suspension/cancellation: if the next write
        # fails, account owners may need to log in again, but access is safe.
        if args.action in ("suspend", "cancel"):
            users = serve.load_users()
            users["sessions"] = {}
            serve.save_users(users)
        stage["agency_profile"] = new
        event["actor"] = "verified-host-operator"
        if args.action == "cancel":
            event["export_retention_reference"] = args.export_reference.strip()
        stage.setdefault("agency_events", []).append(event)
        stage.setdefault("audit_log", []).append({
            "id": "agency-operation-" + str(len(stage["agency_events"])),
            "at": event["created_at"], "actor": "verified-host-operator",
            "action": "agency_" + args.action, "target": args.agency,
            "note": event["reason"],
        })
        serve.save_stage(stage)
    return {"agency_id": args.agency, "action": args.action,
            "status": new["operational_status"],
            "subscription_status": new["subscription_status"],
            "version": new["version"],
            "notice": "Manual record only; no payment, DNS or hosting action was executed."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agency", required=True)
    p.add_argument("--action", required=True, choices=[
        "set_plan", "activate", "suspend", "reactivate",
        "record_invoice", "mark_overdue", "cancel"])
    p.add_argument("--reason", required=True)
    p.add_argument("--reviewed", action="store_true",
                   help="Operator has separately verified agency identity and authority.")
    p.add_argument("--plan", choices=sorted(agency_admin.PLANS))
    p.add_argument("--property-limit", type=int)
    p.add_argument("--staff-limit", type=int)
    p.add_argument("--invoice-reference")
    p.add_argument("--export-reference",
                   help="Verified offboarding export and retention review ID; mandatory for cancellation.")
    args = p.parse_args()
    try:
        result = execute(args)
    except ValueError as error:
        p.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
