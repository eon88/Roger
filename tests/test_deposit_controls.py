"""Holding and protected tenancy deposit constraints, human evidence and permissions."""
from datetime import date
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
import copy,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import serve
import deposit_controls as dc
import agent_briefing


class DepositRulesTests(TestCase):
    def setUp(self):
        self.tenancy={"id":"t-1","property_id":"flat-1","start_date":"2026-09-01",
                      "rent_amount_pence":120000,"rent_frequency":"monthly",
                      "status":"active","agreement_status":"draft"}
        self.stage={"deposit_records":[],"documents":[
            {"id":"doc-1","property_id":"flat-1","tenancy_id":"t-1","status":"verified",
             "access_roles":["agent","tenant"]},
            {"id":"doc-2","property_id":"flat-2","status":"verified","access_roles":["agent"]}],
            "tenancies":[self.tenancy],"audit_log":[]}
        self.today=date(2026,11,8)

    def create(self,kind,amount,received="2026-11-01"):
        item=dc.create_record(self.stage,self.tenancy,{
            "kind":kind,"amount_pence":amount,"received_date":received
        },"office","2026-11-08T10:00:00Z",self.today)
        self.stage["deposit_records"].append(item)
        return item

    def test_holding_and_tenancy_deposits_are_distinct(self):
        self.assertEqual(dc.cap_pence(self.tenancy,"holding"),27692)
        self.assertEqual(dc.cap_pence(self.tenancy,"tenancy"),138461)
        with self.assertRaises(ValueError):
            self.create("holding",27693)
        holding=self.create("holding",25000)
        self.assertEqual(holding["decision_deadline"],"2026-11-16")
        self.assertIsNone(holding["protection_deadline"])
        deposit=self.create("tenancy",120000)
        self.assertEqual(deposit["protection_deadline"],"2026-12-01")
        self.assertIsNone(deposit["decision_deadline"])

    def test_duplicate_protection_and_evidence(self):
        record=self.create("tenancy",120000)
        data={"scheme":"Deposit Protection Service","scheme_reference":"DPS-001",
              "protected_on":"2026-11-03","prescribed_info_provided_on":"2026-11-04",
              "evidence_document_id":"doc-1"}
        result=dc.protect(self.stage,record,data,"office","2026-11-08",self.today)
        self.assertEqual(result["status"],"protection_recorded")
        self.assertEqual(result["protection_late"],False)
        with self.assertRaises(ValueError):
            dc.protect(self.stage,record,data,"office","2026-11-08",self.today)
        self.assertEqual(record["evidence_document_ids"],["doc-1"])
        self.assertNotIn("evidence_document_ids",dc.tenant_view(record))

    def test_refuses_false_or_foreign_document(self):
        record=self.create("tenancy",120000)
        base={"scheme":"MyDeposits","scheme_reference":"MD-001","protected_on":"2026-11-03",
              "prescribed_info_provided_on":"2026-11-03"}
        with self.assertRaises(ValueError):
            dc.protect(self.stage,record,{**base,"evidence_document_id":"doc-2"},"office","2026-11-08",self.today)
        with self.assertRaises(ValueError):
            dc.protect(self.stage,record,{**base,"evidence_document_id":"not-present"},"office","2026-11-08",self.today)
        self.assertEqual(record["status"],"received_unverified")

    def test_refund_and_forfeit_need_justification(self):
        record=self.create("holding",20000)
        with self.assertRaises(ValueError):
            dc.holding_outcome(self.stage,record,{
                "decision":"applied_to_tenancy","reason":"Recorded tenant consent",
                "evidence_document_id":"doc-1","tenant_consented":False,"agreement_signed":True
            },"office","2026-11-08",self.today)
        result=dc.holding_outcome(self.stage,record,{
            "decision":"refunded","reason":"Application did not proceed",
            "evidence_document_id":"doc-1"
        },"office","2026-11-08",self.today)
        self.assertEqual(result["status"],"refunded")
        with self.assertRaises(ValueError):
            dc.holding_outcome(self.stage,record,{
                "decision":"forfeiture_recorded","reason":"Ignored offer","evidence_document_id":"doc-1"
            },"office","2026-11-08",self.today)

    def test_due_and_late_protection_flags(self):
        record=self.create("tenancy",120000,received="2026-09-01")
        x=dc.due_for_review(record,self.today)
        self.assertEqual(x[0],"high")
        self.assertIn("overdue",x[1])
        dc.protect(self.stage,record,{
            "scheme":"Tenancy Deposit Scheme","scheme_reference":"TDS-2",
            "protected_on":"2026-11-03","prescribed_info_provided_on":"2026-11-04",
            "evidence_document_id":"doc-1"
        },"office","2026-11-08",self.today)
        self.assertTrue(record["protection_late"])
        self.assertEqual(dc.due_for_review(record,self.today)[0],"high")

    def test_deadlines_enter_agent_briefing(self):
        record=self.create("holding",25000,received="2026-10-10")
        result=agent_briefing.make_briefing(self.stage,self.today)
        self.assertIn("deposit:"+record["id"],[c["key"] for c in result["cards"]])


class DepositHandlerTests(TestCase):
    def setUp(self):
        self.stage={"tenancies":[
            {"id":"t-1","property_id":"flat-1","tenant_party_ids":["tenant-1"],
             "rent_amount_pence":120000,"rent_frequency":"monthly",
             "agreement_status":"draft"},
            {"id":"t-2","property_id":"flat-2","tenant_party_ids":["tenant-2"],
             "rent_amount_pence":130000,"rent_frequency":"monthly",
             "agreement_status":"draft"}],
            "parties":[
                {"id":"tenant-1","roles":["tenant"],"status":"active","account_id":"acc-1"},
                {"id":"tenant-2","roles":["tenant"],"status":"active","account_id":"acc-2"}],
            "properties":[{"id":"flat-1","tenant_party_id":"tenant-1"},
                          {"id":"flat-2","tenant_party_id":"tenant-2"}],
            "deposit_records":[],"documents":[],"audit_log":[]}
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"office"}
        self.out=[];self.h._json=lambda data,code=200:self.out.append((data,code))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-08T11:00:00Z")
        for p in (a,b,c):p.start();self.addCleanup(p.stop)

    def test_agent_record_and_tenant_role_scoping(self):
        self.h.handle_deposit_action({
            "action":"create","tenancy_id":"t-1","kind":"holding",
            "amount_pence":20000,"received_date":"2026-11-01"})
        self.assertEqual(self.out[-1][1],200)
        self.assertEqual(self.stage["deposit_records"][0]["status"],"received_unverified")
        self.assertEqual(self.stage["audit_log"][-1]["action"],
                         "deposit_receipt_recorded_unverified")
        t1={"role":"tenant","account_id":"acc-1"}
        t2={"role":"tenant","account_id":"acc-2"}
        ids1=self.h.account_party_ids(self.stage,t1,"tenant")
        ids2=self.h.account_party_ids(self.stage,t2,"tenant")
        self.assertEqual(ids1,{"tenant-1"})
        self.assertEqual(ids2,{"tenant-2"})
        vis1={t["id"] for t in self.stage["tenancies"]
              if ids1.intersection(t["tenant_party_ids"])}
        vis2={t["id"] for t in self.stage["tenancies"]
              if ids2.intersection(t["tenant_party_ids"])}
        self.assertEqual(
            [dc.tenant_view(r)["tenancy_id"] for r in self.stage["deposit_records"]
             if r["tenancy_id"] in vis1],["t-1"])
        self.assertEqual(
            [dc.tenant_view(r)["tenancy_id"] for r in self.stage["deposit_records"]
             if r["tenancy_id"] in vis2],[])

    def test_invalid_amount_cannot_make_record(self):
        self.h.handle_deposit_action({
            "action":"create","tenancy_id":"t-1","kind":"tenancy",
            "amount_pence":200000,"received_date":"2026-11-01"})
        self.assertEqual(self.out[-1][1],400)
        self.assertEqual(self.stage["deposit_records"],[])


if __name__=="__main__":
    main()
