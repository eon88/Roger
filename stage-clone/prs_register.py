"""England 2026-27 private rented property registration tracker.

GOV.UK region dates checked 8 Nov 2026. This module records the agent's
evidence and deadlines; Roger does NOT submit or verify registration via API.
These rollout deadlines apply to occupied properties in the initial phase.
"""
from datetime import date

ROLLOUT = {
    "West Midlands": ("2026-12-15", "2027-03-14"),
    "East of England": ("2027-01-15", "2027-04-14"),
    "East Midlands": ("2027-02-15", "2027-05-14"),
    "South East": ("2027-03-15", "2027-06-14"),
    "Yorkshire and Humber": ("2027-04-15", "2027-07-14"),
    "North West": ("2027-05-15", "2027-08-14"),
    "North East": ("2027-06-15", "2027-09-14"),
    "London": ("2027-07-15", "2027-10-14"),
    "South West": ("2027-08-15", "2027-11-14"),
}
SOURCE="https://www.gov.uk/guidance/register-your-rental-property-service-guidance-for-landlords"
VERSION="2026-11-08"
STATES={"not_started","in_progress","registered","exempt"}


def date_text(text, label):
    if not isinstance(text,str) or len(text)!=10:
        raise ValueError(label+" must use YYYY-MM-DD")
    try:
        parsed=date.fromisoformat(text)
    except ValueError:
        raise ValueError(label+" is invalid") from None
    if parsed.isoformat()!=text:
        raise ValueError(label+" must use YYYY-MM-DD")
    return parsed


def tracked_registration(stage, prop, data, actor, now, today=None):
    """Validate and return an audit-ready record; caller commits if accepted."""
    today=today or date.today()
    region=data.get("region")
    if region not in ROLLOUT:
        raise ValueError("Select a listed England region and verify the council boundary")
    status=data.get("status")
    if status not in STATES:
        raise ValueError("Invalid registration status")
    notes=data.get("notes","")
    if not isinstance(notes,str) or len(notes)>1000:
        raise ValueError("Registration notes must be text, max 1000 characters")
    owner_number=data.get("landlord_registration_number","")
    property_number=data.get("property_registration_number","")
    if any(not isinstance(x,str) or len(x)>120 for x in (owner_number,property_number)):
        raise ValueError("Registration numbers must be text, max 120 characters")
    registered_on=data.get("registered_on") or None
    renew_on=data.get("renewal_date") or None
    if status=="registered":
        if not owner_number.strip() or not property_number.strip() or not registered_on:
            raise ValueError("Registration numbers and registration date are required")
        registered=date_text(registered_on,"registered_on")
        if registered>today:
            raise ValueError("Registration date cannot be in the future")
        if renew_on and date_text(renew_on,"renewal_date")<=registered:
            raise ValueError("Renewal date must be after registration")
        evidence=data.get("evidence_document_id")
        doc=next((x for x in stage.get("documents",[]) if x.get("id")==evidence),None)
        if not doc or doc.get("status")!="verified":
            raise ValueError("Verified evidence of registration must be attached")
        if doc.get("property_id")!=prop.get("id"):
            raise ValueError("Registration evidence belongs to another property")
    else:
        if registered_on or renew_on:
            raise ValueError("Only a registered property may have registration/renewal dates")
        evidence=None
        owner_number=property_number=""
    if status=="exempt" and len(notes.strip())<12:
        raise ValueError("Record the basis of an exemption for external review")
    start,deadline=ROLLOUT[region]
    record={
        "region":region,"status":status,
        "rollout_start":start,"rollout_deadline":deadline,
        "policy_version":VERSION,"official_source":SOURCE,
        "landlord_registration_number":owner_number.strip(),
        "property_registration_number":property_number.strip(),
        "registered_on":registered_on,"renewal_date":renew_on,
        "evidence_document_id":evidence,"notes":notes.strip(),
        "recorded_at":now,"recorded_by":actor,
        "reviewed_evidence":status=="registered",
        "government_api_verified":False,
    }
    return record


def due_for_review(prop, today=None):
    today=today or date.today()
    if prop.get("lifecycle_status") not in (
        "occupied","notice_given","let_agreed"):
        return None
    obj=prop.get("prs_registration") or {}
    if obj.get("status") in ("registered","exempt"):
        renewal=obj.get("renewal_date")
        if renewal:
            try:
                due=date_text(renewal,"renewal_date")
            except ValueError:
                return None
            if due<today:
                return ("high","PRS registration renewal overdue",due)
            if (due-today).days<=45:
                return ("normal","PRS registration renewal due",due)
        return None
    region=obj.get("region")
    if region not in ROLLOUT:
        return ("normal","Select the correct PRS region and check current registration rules",None)
    deadline=date.fromisoformat(ROLLOUT[region][1])
    if deadline<today:
        return ("high","PRS registration deadline has passed",deadline)
    if (deadline-today).days<=45:
        return ("normal","PRS registration deadline approaching",deadline)
    return None
