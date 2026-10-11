"""Task 03: itemised VAT, quote versions, variations and external settlement controls.

All synthetic; inherits the proven four-role prework fixture. No live bank integration.
"""
from datetime import datetime, timezone
from test_prework_spend_control import PreworkCostApprovalTests


class FinanceControlsTests(PreworkCostApprovalTests):
    def approved_job(self, amount=12000):
        self.assertEqual(self.request_quote(), 200)
        self.assertEqual(self.submit(amount), 200)
        self.assertEqual(self.approve_quote(), 200)
        if self.stage["jobs"][0]["status"] == "awaiting_prework_approval":
            self.assertEqual(self.landlord_decides(), 200)
        return self.stage["jobs"][0]

    def test_itemised_quote_exact_vat_and_frozen_landlord_snapshot(self):
        self.assertEqual(self.request_quote(), 200)
        lines = [
            {"description": "Replace section of pipe", "net_pence": 10000, "vat_rate_bps": 2000},
            {"description": "Non VAT item", "net_pence": 5000, "vat_rate_bps": 0},
        ]
        self.assertEqual(self.job_action("trade", "submit_quote",
                       quote_pence=17000, line_items=lines, note="Pipe and fittings"), 200)
        quote = self.stage["jobs"][0]["quotes"][0]
        self.assertEqual(quote["version"], 1)
        self.assertEqual(quote["vat_pence"], 2000)
        self.assertEqual(quote["net_pence"], 15000)
        self.assertEqual(quote["line_items"][0]["gross_pence"], 12000)
        self.assertEqual(quote["pricing_format"], "itemised")
        self.assertEqual(self.approve_quote(), 200)
        approval = self.stage["approvals"][0]
        self.assertEqual(approval["quote_version"], 1)
        self.assertEqual(approval["quote_vat_pence"], 2000)
        self.assertEqual(approval["quote_lines"], quote["line_items"])
        self.assertEqual(self.landlord_decides(), 200)
        self.assertEqual(self.stage["jobs"][0]["approved_quote_version"], 1)

    def test_unsupported_vat_or_inconsistent_quote_is_rejected(self):
        self.assertEqual(self.request_quote(), 200)
        bad = [{"description": "Repair pipe", "net_pence": 10000, "vat_rate_bps": 1700}]
        self.assertEqual(self.job_action("trade", "submit_quote",
                                        quote_pence=10000, line_items=bad), 400)
        good = [{"description": "Repair pipe", "net_pence": 10000, "vat_rate_bps": 2000}]
        self.assertEqual(self.job_action("trade", "submit_quote",
                                        quote_pence=10000, line_items=good), 409)
        self.assertEqual(self.stage["jobs"][0]["status"], "quote_requested")
        self.assertEqual(self.stage["jobs"][0].get("quotes", []), [])

    def test_quote_version_increases_on_requote(self):
        self.assertEqual(self.request_quote(), 200)
        self.assertEqual(self.submit(13000), 200)
        self.assertEqual(self.job_action("agent", "decline_quote", reason="Get more detail"), 200)
        self.assertEqual(self.submit(12000), 200)
        self.assertEqual([q["version"] for q in self.stage["jobs"][0]["quotes"]], [1, 2])
        self.assertEqual(self.approve_quote(), 200)
        self.assertEqual(self.stage["jobs"][0]["approved_quote_version"], 2)

    def test_variation_over_authority_requires_landlord_before_invoice(self):
        job = self.approved_job(12000)
        self.assertEqual(self.job_action("trade", "start"), 200)
        lines = [{"description": "Additional valve", "net_pence": 5000, "vat_rate_bps": 0}]
        self.assertEqual(self.job_action("trade", "submit_variation", extra_pence=5000,
                                        note="New valve", line_items=lines), 200)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=17000), 409)
        self.assertEqual(self.job_action("agent", "approve_variation"), 200)
        self.assertEqual(job["approved_quote_pence"], 12000)
        self.assertEqual(job["pending_variation"]["status"], "pending_landlord")
        self.assertEqual(self.stage["approvals"][-1]["approval_type"], "variation_quote")
        approval_id = self.stage["approvals"][-1]["id"]
        self.handler.user = self.users["owner"]
        self.handler.handle_landlord_action({"id": approval_id, "action": "approve"})
        self.assertEqual(self.responses[-1][1], 200)
        self.assertEqual(job["approved_quote_pence"], 17000)
        self.assertNotIn("pending_variation", job)
        self.assertEqual(job["approved_variations"][0]["extra_pence"], 5000)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=17000,
                                        invoice_number="PLUMB-001",
                                        line_items=[{"description":"All approved work",
                                                     "net_pence":17000,"vat_rate_bps":0}]), 200)
        self.assertEqual(job["invoice_number"], "PLUMB-001")
        self.assertEqual(job["invoice_approved_gross_limit_pence"], 17000)
        self.assertEqual(self.job_action("agent", "approve_invoice"), 200)

    def test_variation_cannot_auto_authorise_when_landlord_declines(self):
        job = self.approved_job(12000)
        self.assertEqual(self.job_action("trade", "submit_variation",
                                        extra_pence=5000, note="Extra work"), 200)
        self.assertEqual(self.job_action("agent", "approve_variation"), 200)
        approval_id = self.stage["approvals"][-1]["id"]
        self.handler.user = self.users["owner"]
        self.handler.handle_landlord_action({"id": approval_id, "action": "reject",
                                             "reason": "Not needed"})
        self.assertEqual(self.responses[-1][1], 200)
        self.assertEqual(job["approved_quote_pence"], 12000)
        self.assertNotIn("pending_variation", job)
        self.assertEqual(job["variation_history"][0]["status"], "declined")

    def test_agent_variation_within_mandate_needs_no_landlord(self):
        job = self.approved_job(10000)
        self.assertEqual(self.job_action("trade", "submit_variation",
                                        extra_pence=3000, note="Extra connector"), 200)
        self.assertEqual(self.job_action("agent", "approve_variation"), 200)
        self.assertEqual(job["approved_quote_pence"], 13000)
        self.assertEqual(self.stage["approvals"], [])
        self.assertEqual(job["approved_variations"][0]["status"], "approved")

    def test_itemised_invoice_total_and_supplier_invoice_id(self):
        job = self.approved_job(12000)
        self.assertEqual(self.job_action("trade", "start"), 200)
        lines = [{"description":"Repair labour", "net_pence":10000, "vat_rate_bps":2000}]
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=10000,
                                        invoice_number="INV-01", line_items=lines), 409)
        self.assertEqual(job["status"], "in_progress")
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=12000,
                                        invoice_number="INV-01", line_items=lines), 200)
        self.assertEqual(job["invoice_number"], "INV-01")
        self.assertEqual(job["invoice_net_pence"], 10000)
        self.assertEqual(job["invoice_vat_pence"], 2000)
        self.assertEqual(self.job_action("agent", "approve_invoice"), 200)
        second = dict(job, id="job-2", status="in_progress", case_id=10,
                      invoice_pence=None, invoice_number=None)
        self.stage["jobs"].append(second)
        self.handler.user = self.users["trade"]
        self.handler.handle_job_action({
            "id": "job-2", "action": "complete", "invoice_pence": 12000,
            "invoice_number": "INV-01",
        })
        self.assertEqual(self.responses[-1][1], 409)
        self.assertIn("duplicate", self.responses[-1][0]["error"])
        self.assertEqual(second["status"], "in_progress")

    def test_partial_payment_and_credit_do_not_pretend_money_was_sent(self):
        job = self.approved_job(12000)
        self.assertEqual(self.job_action("trade", "start"), 200)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=12000,
                                        invoice_number="INV-07"), 200)
        self.assertEqual(self.job_action("agent", "approve_invoice"), 200)
        date = datetime.now(timezone.utc).date().isoformat()
        self.assertEqual(self.job_action("agent", "record_payment",
                                        payment_reference="BANK-1", payment_date=date,
                                        payment_amount_pence=4000), 200)
        self.assertEqual(job["status"], "partially_paid")
        self.assertEqual(job["balance_due_pence"], 8000)
        self.assertEqual(self.job_action("agent", "record_payment",
                                        payment_reference="BANK-1", payment_date=date,
                                        payment_amount_pence=1000), 409)
        self.assertEqual(self.job_action("agent", "record_credit",
                                        credit_note_number="CR-07", credit_reason="Price reduction",
                                        credit_amount_pence=2000), 200)
        self.assertEqual(job["balance_due_pence"], 6000)
        self.assertEqual(self.job_action("agent", "record_payment",
                                        payment_reference="BANK-2", payment_date=date,
                                        payment_amount_pence=6000), 200)
        self.assertEqual(job["status"], "paid")
        self.assertEqual(job["payment_amount_pence"], 10000)
        self.assertEqual(job["balance_due_pence"], 0)
        self.assertEqual(self.job_action("agent", "record_credit",
                                        credit_note_number="CR-08",credit_reason="No",
                                        credit_amount_pence=100), 409)

    def test_credit_alone_is_not_labelled_a_bank_payment(self):
        job=self.approved_job(10000)
        self.assertEqual(self.job_action("trade", "start"), 200)
        self.assertEqual(self.job_action("trade", "complete", invoice_pence=10000), 200)
        self.assertEqual(self.job_action("agent", "approve_invoice"), 200)
        self.assertEqual(self.job_action("agent", "record_credit",
                                        credit_note_number="CR-FULL", credit_reason="Cancel charge",
                                        credit_amount_pence=10000), 200)
        self.assertEqual(job["status"], "credited")
        self.assertNotIn("paid_at",job)
        self.assertEqual(job.get("payments",[]),[])

