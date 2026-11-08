"""Real-money safety: imported statement matching never moves funds or trusts amounts."""
from datetime import datetime
from pathlib import Path
from unittest import TestCase,main
from unittest.mock import patch
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import bank_reconciliation as br
import serve


class BankReconciliationTests(TestCase):
    def setUp(self):
        self.stage={
            "rent_ledger_entries":[
                {"id":"rent-1","property_id":"flat-1","tenancy_id":"t-1",
                 "due_date":"2026-11-01","amount_due_pence":120000,
                 "payments":[{"id":"rentpayment-1","amount_pence":90000,
                              "received_date":"2026-11-02",
                              "reconciliation_status":"recorded_unverified"}],
                 "adjustments":[]},
                {"id":"rent-2","property_id":"flat-2","tenancy_id":"t-2",
                 "due_date":"2026-11-01","amount_due_pence":140000,
                 "payments":[{"id":"rentpayment-2","amount_pence":90000,
                              "received_date":"2026-11-02",
                              "reconciliation_status":"recorded_unverified"}],
                 "adjustments":[]},
            ],
            "documents":[{"id":"bank-1","status":"verified","access_roles":["agent"]},
                         {"id":"tenant-shared","status":"verified","access_roles":["agent","tenant"]}],
            "bank_reconciliation_history":[],"audit_log":[]
        }
        self.h=serve.H.__new__(serve.H)
        self.h.user={"role":"agent","username":"agent"}
        self.answers=[]
        self.h._json=lambda obj,code=200:self.answers.append((obj,code))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-08T11:30:00Z")
        for x in (a,b,c):x.start();self.addCleanup(x.stop)

    def test_statement_preview_is_read_only_and_detects_ambiguous_matches(self):
        csv="transaction_id,date,amount_pence\nBANK-001,2026-11-02,90000\n"
        p=br.statement_preview(csv,self.stage)
        self.assertEqual(p["rows"][0]["status"],"ambiguous")
        self.assertEqual(p["rows"][0]["candidate_count"],2)
        self.assertTrue(p["read_only"])
        self.assertFalse(self.stage["bank_reconciliation_history"])

    def test_agent_match_requires_unique_reference_and_private_evidence(self):
        body={"action":"match_receipt","entry_id":"rent-1",
              "payment_id":"rentpayment-1","transaction_id":"BANK-001",
              "amount_pence":90000,"bank_date":"2026-11-02",
              "evidence_document_id":"bank-1"}
        self.h.handle_bank_reconciliation_action(body)
        data,code=self.answers[-1]
        self.assertEqual(code,200,data)
        self.assertEqual(data["reconciliation_status"],"agent_matched")
        receipt=self.stage["rent_ledger_entries"][0]["payments"][0]
        self.assertEqual(receipt["bank_evidence_document_id"],"bank-1")
        self.assertEqual(self.h.safe_rent_entry(self.stage["rent_ledger_entries"][0])["reconciled_pence"],90000)
        self.h.handle_bank_reconciliation_action({**body,"entry_id":"rent-2","payment_id":"rentpayment-2"})
        self.assertEqual(self.answers[-1][1],400)
        self.assertEqual(len(self.stage["bank_reconciliation_history"]),1)

    def test_reject_wrong_amount_and_reused_reference(self):
        bad={"entry_id":"rent-1","payment_id":"rentpayment-1",
             "transaction_id":"BANK-004","bank_date":"2026-11-02",
             "amount_pence":90001,"evidence_document_id":"bank-1"}
        with self.assertRaises(ValueError):
            br.apply_match(self.stage,bad,"2026-11-08","agent")
        self.assertFalse(self.stage["bank_reconciliation_history"])

    def test_reject_shared_evidence_and_large_date_discrepancy(self):
        base={"entry_id":"rent-1","payment_id":"rentpayment-1",
              "transaction_id":"BANK-002","amount_pence":90000,
              "bank_date":"2026-11-02","evidence_document_id":"tenant-shared"}
        with self.assertRaises(ValueError):
            br.apply_match(self.stage,base,"2026-11-08","agent")
        with self.assertRaises(ValueError):
            br.apply_match(self.stage,{**base,"evidence_document_id":"bank-1",
                                      "bank_date":"2026-10-01"},"2026-11-08","agent")

    def test_invalid_csv_cannot_crash_or_mutate_stage(self):
        examples=[
            "date,amount_pence\n2026-11-01,20000\n",
            "transaction_id,date,amount_pence\nBANK-1,2026-11-01,-500\n",
            "transaction_id,date,amount_pence\nBANK-1,2026-11-01,90000\nBANK-1,2026-11-01,90000\n",
            "transaction_id,date,amount_pence\nBANK-1,2026-02-30,500\n",
        ]
        for x in examples:
            with self.subTest(x=x[:30]),self.assertRaises(ValueError):
                br.statement_preview(x,self.stage)
        self.assertEqual(self.stage["bank_reconciliation_history"],[])

    def test_existing_unverified_receipt_not_mislabelled_reconciled(self):
        summary=self.h.safe_rent_entry(self.stage["rent_ledger_entries"][0])
        self.assertEqual(summary["unverified_receipts_pence"],90000)
        self.assertEqual(summary["reconciled_pence"],0)
        self.assertEqual(summary["amount_received_pence"],90000)


if __name__=="__main__":
    main()
