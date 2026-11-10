"""England tenancy and holding deposit records, strict human-evidence workflow.

No bank transfers, safeguarding certificate, deposit-scheme API, automatic
forfeiture or legal advice. Recording a receipt does not verify received funds.
"""
from datetime import date, timedelta
from fractions import Fraction
from tenancy_2026 import parse_date


SCHEMES = {"Deposit Protection Service", "MyDeposits", "Tenancy Deposit Scheme"}
TYPES = {"holding", "tenancy"}


def annual_rent(tenancy):
    money=tenancy.get("rent_amount_pence")
    freq=tenancy.get("rent_frequency")
    if not isinstance(money,int) or isinstance(money,bool) or money<=0:
        raise ValueError("Tenancy must have positive rent in integer pence")
    if freq not in ("weekly","fortnightly","monthly"):
        raise ValueError("Unknown rent frequency for deposit calculation")
    multiplier={"weekly":52,"fortnightly":26,"monthly":12}[freq]
    return money*multiplier


def cap_pence(tenancy, kind):
    annual=annual_rent(tenancy)
    weeks = 1 if kind=="holding" else (6 if annual>=5_000_000 else 5)
    if kind not in TYPES:
        raise ValueError("Deposit must be holding or tenancy")
    return (annual*weeks)//52


def create_record(stage, tenancy, data, actor, timestamp, today=None):
    today=today or date.today()
    kind=data.get("kind")
    if kind not in TYPES:
        raise ValueError("Deposit must be holding or tenancy")
    amount=data.get("amount_pence")
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0:
        raise ValueError("Amount must be positive integer pence")
    if amount>cap_pence(tenancy,kind):
        raise ValueError("Deposit exceeds the Tenant Fees Act limit")
    received=parse_date(data.get("received_date"),"received_date")
    if received>today:
        raise ValueError("Deposit cannot be recorded as received in the future")
    if kind=="holding" and tenancy.get("agreement_status")=="signed":
        raise ValueError("Holding deposits belong to the pre-agreement stage")
    for past in stage.get("deposit_records",[]):
        if past.get("tenancy_id")==tenancy["id"] and past.get("kind")==kind:
            if past.get("status") not in ("refunded","fully_returned","forfeiture_recorded"):
                raise ValueError("Active deposit record already exists for this tenancy")
    number=int(stage.get("next_deposit_id",1))
    status="received_unverified"
    deadline=received+timedelta(days=15 if kind=="holding" else 30)
    record={
        "id":"deposit-"+str(number),"model_version":1,"kind":kind,
        "property_id":tenancy["property_id"],"tenancy_id":tenancy["id"],
        "amount_pence":amount,"received_date":received.isoformat(),
        "status":status,
        "decision_deadline":deadline.isoformat() if kind=="holding" else None,
        "protection_deadline":deadline.isoformat() if kind=="tenancy" else None,
        "scheme":None,"scheme_reference":None,
        "protected_on":None,"prescribed_info_provided_on":None,
        "created_by":actor,"created_at":timestamp,
        "evidence_document_ids":[],"history":[{
            "event":"receipt_recorded_unverified","by":actor,"at":timestamp
        }],
    }
    return record


def _evidence(stage, record, identifier):
    if not isinstance(identifier,str) or not identifier:
        raise ValueError("Verified evidence document is required")
    document=next((d for d in stage.get("documents",[])
                   if d.get("id")==identifier),None)
    if not document or document.get("status")!="verified":
        raise ValueError("Evidence document is not verified")
    if document.get("property_id")!=record["property_id"]:
        raise ValueError("Evidence document belongs to another property")
    if document.get("tenancy_id") not in (None,"",record["tenancy_id"]):
        raise ValueError("Evidence document belongs to another tenancy")
    return identifier


def protect(stage, record, data, actor, timestamp, today=None):
    today=today or date.today()
    if record.get("kind")!="tenancy" or record.get("status")!="received_unverified":
        raise ValueError("Only a recorded tenancy deposit can be marked protected")
    scheme=data.get("scheme")
    if scheme not in SCHEMES:
        raise ValueError("Select an approved deposit scheme")
    ref=data.get("scheme_reference")
    if not isinstance(ref,str) or not 3<=len(ref.strip())<=120:
        raise ValueError("Provide scheme reference")
    registered=parse_date(data.get("protected_on"),"protected_on")
    informed=parse_date(data.get("prescribed_info_provided_on"),"prescribed_info_provided_on")
    if registered>today or informed>today:
        raise ValueError("Evidence dates cannot be in the future")
    if registered<parse_date(record["received_date"],"received_date"):
        raise ValueError("Protection cannot predate recorded receipt")
    evidence=_evidence(stage,record,data.get("evidence_document_id"))
    deadline=parse_date(record["protection_deadline"],"protection_deadline")
    record.update({
        "scheme":scheme,"scheme_reference":ref.strip(),
        "protected_on":registered.isoformat(),
        "prescribed_info_provided_on":informed.isoformat(),
        "status":"protection_recorded",
        "protection_late":registered>deadline or informed>deadline,
    })
    record["evidence_document_ids"].append(evidence)
    record["history"].append({"event":"protection_recorded_by_agent",
        "by":actor,"at":timestamp,"protection_late":record["protection_late"]})
    return record


def holding_outcome(stage, record, data, actor, timestamp, today=None):
    today=today or date.today()
    if record.get("kind")!="holding" or record.get("status")!="received_unverified":
        raise ValueError("Only a pending holding deposit can be decided")
    decision=data.get("decision")
    if decision not in ("refunded","applied_to_tenancy","forfeiture_recorded"):
        raise ValueError("Unknown holding-deposit decision")
    reason=data.get("reason")
    if not isinstance(reason,str) or not 10<=len(reason.strip())<=1000:
        raise ValueError("Human reason is required")
    evidence=_evidence(stage,record,data.get("evidence_document_id"))
    if decision=="applied_to_tenancy" and not data.get("tenant_consented"):
        raise ValueError("Applying holding deposit requires tenant's documented consent")
    if decision=="applied_to_tenancy" and not data.get("agreement_signed"):
        raise ValueError("Holding deposit cannot be applied before tenancy signature")
    record["status"]=decision
    record["outcome_reason"]=reason.strip()
    record["outcome_at"]=timestamp
    record["evidence_document_ids"].append(evidence)
    record["history"].append({"event":decision,"by":actor,"at":timestamp})
    return record


def due_for_review(record, today=None):
    today=today or date.today()
    if record.get("kind")=="tenancy" and record.get("status")=="received_unverified":
        deadline=parse_date(record["protection_deadline"],"protection_deadline")
        if deadline<today:
            return "high","Tenancy deposit protection / prescribed information overdue",deadline
        if (deadline-today).days<=7:
            return "normal","Tenancy deposit protection / prescribed information due",deadline
    if record.get("kind")=="tenancy" and record.get("protection_late"):
        return "high","Late deposit evidence requires legal review",None
    if record.get("kind")=="holding" and record.get("status")=="received_unverified":
        deadline=parse_date(record["decision_deadline"],"decision_deadline")
        if deadline<today:
            return "high","Holding deposit decision deadline passed; verify refund obligations",deadline
        if (deadline-today).days<=5:
            return "normal","Holding deposit deadline approaching",deadline
    return None


def tenant_view(record):
    fields=("id","tenancy_id","property_id","kind","amount_pence",
            "received_date","status","decision_deadline","protection_deadline",
            "scheme","scheme_reference","protected_on","prescribed_info_provided_on",
            "protection_late")
    return {k:record.get(k) for k in fields}
