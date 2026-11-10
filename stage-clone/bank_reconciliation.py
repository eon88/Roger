"""Agent-reviewed bank statement matching. No bank integration or money movement.

A match is based on a statement supplied by a human, not a bank API receipt.
Nothing is marked bank-verified automatically; identity and completeness of a
statement need an independent manual check.
"""
import csv
import io
from datetime import date


def _iso_day(s):
    if not isinstance(s,str) or len(s)!=10:
        raise ValueError("Date must use YYYY-MM-DD")
    try:
        d=date.fromisoformat(s)
    except ValueError:
        raise ValueError("Invalid bank statement date") from None
    if d.isoformat()!=s:
        raise ValueError("Date must use YYYY-MM-DD")
    return d


def _positive_amount(v):
    if isinstance(v,bool):
        raise ValueError("Amount must be integer pence")
    if isinstance(v,str):
        if not v.isdigit() or len(v)>12:
            raise ValueError("Amount must be integer pence")
        v=int(v)
    if not isinstance(v,int) or not 0<v<=1_000_000_000:
        raise ValueError("Amount must be positive integer pence")
    return v


def _ref(s):
    if not isinstance(s,str):
        raise ValueError("Bank transaction reference must be text")
    s=s.strip()
    if not 4<=len(s)<=120:
        raise ValueError("Bank transaction reference must be 4 to 120 characters")
    return s


def statement_preview(csv_text, stage):
    if not isinstance(csv_text,str) or len(csv_text)>250000:
        raise ValueError("Statement CSV is too large (250 KB maximum)")
    try:
        reader=csv.DictReader(io.StringIO(csv_text,newline=""), strict=True)
        cols=reader.fieldnames or []
        if len(cols)!=len(set(cols)) or not {"transaction_id","date","amount_pence"}.issubset(cols):
            raise ValueError("Statement must include transaction_id,date,amount_pence")
        rows=list(reader)
    except csv.Error:
        raise ValueError("Malformed statement CSV") from None
    if len(rows)>2000:
        raise ValueError("Maximum 2,000 statement rows per preview")
    ids=set()
    results=[]
    for item in rows:
        if None in item or any(v is None for v in item.values()):
            raise ValueError("Invalid CSV row structure")
        ref=_ref(item["transaction_id"])
        if ref in ids:
            raise ValueError("Statement has duplicate transaction id")
        ids.add(ref)
        received=_iso_day(item["date"])
        amount=_positive_amount(item["amount_pence"])
        possibilities=[]
        for entry in stage.get("rent_ledger_entries",[]):
            for pay in entry.get("payments",[]):
                if pay.get("reconciliation_status") in ("agent_matched","bank_verified"):
                    continue
                if not pay.get("id"):
                    continue # historic payments require a separate ID migration
                try:
                    matches=(_positive_amount(pay.get("amount_pence"))==amount
                             and abs((received-_iso_day(pay.get("received_date"))).days)<=3)
                except ValueError:
                    matches=False
                if matches:
                    possibilities.append({"rent_entry_id":entry.get("id"),
                                          "payment_id":pay.get("id")})
        results.append({
            "transaction_id":ref,"date":received.isoformat(),"amount_pence":amount,
            "candidate_count":len(possibilities),
            "candidates":possibilities[:5],
            "status":"one_possible_match" if len(possibilities)==1 else (
                "ambiguous" if possibilities else "unmatched"),
        })
    return {"source":"agent_uploaded_statement_preview", "read_only":True,
            "requires_human_review":True,"rows":results,
            "warning":"A suggested match does NOT verify receipt of money or the authenticity of a statement."}


def apply_match(stage, data, at, actor):
    entry=next((e for e in stage.get("rent_ledger_entries",[])
                if e.get("id")==data.get("entry_id")),None)
    if not entry:
        raise ValueError("Rent entry not found")
    payment=next((p for p in entry.get("payments",[])
                  if p.get("id") and p.get("id")==data.get("payment_id")),None)
    if not payment:
        raise ValueError("Payment not found or predates the supported reconciliation schema")
    if payment.get("reconciliation_status")=="agent_matched":
        raise ValueError("Payment already matched to statement evidence")
    transaction=_ref(data.get("transaction_id"))
    if any(
        p.get("bank_transaction_id")==transaction
        for e in stage.get("rent_ledger_entries",[]) for p in e.get("payments",[])
    ):
        raise ValueError("This bank transaction reference is already used")
    amount=_positive_amount(data.get("amount_pence"))
    bank_date=_iso_day(data.get("bank_date"))
    if amount!=_positive_amount(payment.get("amount_pence")):
        raise ValueError("Statement amount differs from recorded rent receipt")
    if abs((bank_date-_iso_day(payment.get("received_date"))).days)>3:
        raise ValueError("Bank date is more than three days from the recorded date")
    evidence=data.get("evidence_document_id")
    if not isinstance(evidence,str) or not evidence:
        raise ValueError("A private verified bank-statement evidence document is required")
    doc=next((d for d in stage.get("documents",[])
              if d.get("id")==evidence),None)
    if not doc or doc.get("status")!="verified":
        raise ValueError("Evidence document must exist and be verified")
    if (doc.get("access_roles") or ["agent"]) != ["agent"]:
        raise ValueError("Bank statement evidence must be restricted to agents only")
    payment["bank_transaction_id"]=transaction
    payment["bank_date"]=bank_date.isoformat()
    payment["bank_evidence_document_id"]=evidence
    payment["reconciliation_status"]="agent_matched"
    payment["reconciled_at"]=at
    payment["reconciled_by"]=actor
    stage.setdefault("bank_reconciliation_history",[]).append({
        "event":"manual_evidence_match","entry_id":entry["id"],
        "payment_id":payment["id"],"bank_transaction_id":transaction,
        "evidence_document_id":evidence,"at":at,"by":actor,
    })
    return {"entry_id":entry["id"],"payment_id":payment["id"],
            "reconciliation_status":"agent_matched",
            "warning":"Human-matched statement evidence; not independently bank-verified"}
